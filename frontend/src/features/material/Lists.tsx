import { useState } from "react";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  Button,
  DataTable,
  Field,
  formatDate,
  Modal,
  PageHeader,
  QueryBoundary,
  SearchableSelect,
  Select,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import {
  BASE,
  DeficitButton,
  errorText,
  MATERIAL,
  ModalActions,
  period,
  StockTabs,
  useLocations,
  type LocationOut,
} from "./shared";

/* --- wishlist -------------------------------------------------------------- */

const DEFICIT_STATUS = [
  { value: "open", label: "offen" },
  { value: "ordered", label: "bestellt" },
  { value: "dismissed", label: "verworfen" },
];

/** The Materialwarte's wishlist, from every "Defizit melden". */
export function Deficits() {
  const toast = useToast();
  const [status, setStatus] = useState("open");
  const query = useApiQuery(["material", "deficits", status], () =>
    unwrap(client.GET("/api/material/deficits", { params: { query: { status } } })),
  );
  const update = useApiMutation(
    ({ id, value }: { id: number; value: string }) =>
      unwrap(
        client.PATCH("/api/material/deficits/{deficit_id}", {
          params: { path: { deficit_id: id } },
          body: { status: value },
        }),
      ),
    {
      invalidate: [["material", "deficits"]],
      onSuccess: () => toast.success("Gespeichert."),
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Material", to: BASE }, { label: "Bestand", to: `${BASE}/stock` }, { label: "Wunschliste" }]}
        actions={<DeficitButton />}
      />
      <StockTabs />
      <div className="list-toolbar">
        <SearchableSelect label="Status" value={status} onChange={setStatus} options={DEFICIT_STATUS} />
      </div>
      <QueryBoundary query={query} empty="Die Wunschliste ist leer.">
        {(rows) => (
          <DataTable
            rows={rows}
            rowKey={(d) => d.id}
            columns={[
              { header: "Was", cell: (d) => d.product_type?.name ?? d.text },
              {
                header: "Gebraucht",
                cell: (d) =>
                  d.wanted_from ? period(d.wanted_from, d.wanted_to ?? d.wanted_from) : "—",
              },
              { header: "Kommentar", cell: (d) => d.comment || "—" },
              { header: "Von", cell: (d) => d.reported_by?.name ?? "—" },
              { header: "Gemeldet", cell: (d) => formatDate(d.created_at) },
              {
                header: "Status",
                cell: (d) => (
                  <Select
                    value={d.status}
                    onChange={(value) => update.mutate({ id: d.id, value })}
                    options={DEFICIT_STATUS}
                  />
                ),
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- locations ------------------------------------------------------------- */

/** Where material is kept. */
export function Locations() {
  const query = useLocations();
  const [editing, setEditing] = useState<LocationOut | "new" | null>(null);
  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Material", to: BASE }, { label: "Bestand", to: `${BASE}/stock` }, { label: "Orte" }]}
        actions={<Button onClick={() => setEditing("new")}>Neuer Ort</Button>}
      />
      <StockTabs />
      <QueryBoundary query={query} empty="Noch keine Orte.">
        {(rows) => (
          <DataTable
            rows={rows}
            rowKey={(l) => l.id}
            onRowClick={(l) => setEditing(l)}
            columns={[
              { header: "Name", cell: (l) => l.name },
              { header: "Adresse", cell: (l) => l.address || "—" },
              { header: "Öffnungszeiten", cell: (l) => l.opening_hours || "—" },
            ]}
          />
        )}
      </QueryBoundary>
      {editing && (
        <LocationModal location={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      )}
    </div>
  );
}

function LocationModal({ location, onClose }: { location: LocationOut | null; onClose: () => void }) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [form, setForm] = useState({
    name: location?.name ?? "",
    address: location?.address ?? "",
    opening_hours: location?.opening_hours ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const save = useApiMutation(
    () =>
      location
        ? unwrap(
            client.PUT("/api/material/locations/{location_id}", {
              params: { path: { location_id: location.id } },
              body: form,
            }),
          )
        : unwrap(client.POST("/api/material/locations", { body: form })),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Gespeichert.");
        onClose();
      },
      onError: (e) => {
        if (e instanceof ApiError) setErrors(e.fieldErrors);
        toast.error(errorText(e));
      },
    },
  );
  const remove = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/material/locations/{location_id}", {
          params: { path: { location_id: location!.id } },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Ort gelöscht.");
        onClose();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <Modal title={location ? location.name : "Neuer Ort"} onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          save.mutate(undefined);
        }}
      >
        <Field label="Name">
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          {errors.name && <div className="field-error">{errors.name.join(" ")}</div>}
        </Field>
        <Field label="Adresse">
          <input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
        </Field>
        <Field label="Öffnungszeiten">
          <textarea
            rows={3}
            value={form.opening_hours}
            onChange={(e) => setForm({ ...form, opening_hours: e.target.value })}
          />
        </Field>
        <ModalActions>
          <Button type="submit" busy={save.isPending}>
            Speichern
          </Button>
          {location && (
            <Button
              variant="danger"
              busy={remove.isPending}
              onClick={async () => {
                if (await confirm({ message: "Ort löschen?", danger: true, confirmLabel: "Löschen" }))
                  remove.mutate(undefined);
              }}
            >
              Löschen
            </Button>
          )}
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
}
