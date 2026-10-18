import { useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useGroups } from "../../api/queries";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  euro,
  Field,
  Menu,
  Modal,
  MultiSelect,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  useConfirmDialog,
  useToast,
  type DetailRow,
} from "../../components/ui";
import { useCart, WithCart } from "./cart";
import {
  BASE,
  DeficitModal,
  errorText,
  MATERIAL,
  mediaUrl,
  ModalActions,
  PartStatus,
  PhotoFrame,
  postMultipart,
  period,
  ReservationStatus,
  useLocations,
  useMaterialRoles,
  useTags,
  Whereabouts,
  type ProductTypeOut,
  type SizeOut,
} from "./shared";

export function TypeDetailPage() {
  const { id } = useParams();
  const typeId = Number(id);
  const cart = useCart();
  const query = useApiQuery(
    ["material", "types", typeId, cart.start, cart.end],
    () =>
      unwrap(
        client.GET("/api/material/types/{type_id}", {
          params: { path: { type_id: typeId }, query: { start: cart.start, end: cart.end } },
        }),
      ),
    // A new period keeps the page in place while its availability loads.
    { placeholderData: keepPreviousData },
  );
  return (
    <>
      {query.data === undefined && (
        <PageHeader breadcrumbs={[{ label: "Material", to: BASE }, { label: "…" }]} />
      )}
      <QueryBoundary query={query}>{(t) => <TypeDetailBody key={t.id} type={t} />}</QueryBoundary>
    </>
  );
}

type TypeForm = {
  name: string;
  manufacturer: string;
  product_group: string;
  description: string;
  is_psa: boolean;
  article_number: string;
  usage_years: string;
  inspection_interval_days: string;
  daily_rate: string;
  tags: number[];
};

function toForm(t: ProductTypeOut): TypeForm {
  return {
    name: t.name,
    manufacturer: t.manufacturer,
    product_group: t.product_group,
    description: t.description,
    is_psa: t.is_psa,
    article_number: t.article_number,
    usage_years: t.usage_years?.toString() ?? "",
    inspection_interval_days: String(t.inspection_interval_days),
    daily_rate: t.daily_rate?.toString() ?? "",
    tags: t.tags.map((tag) => tag.id),
  };
}

function fromForm(f: TypeForm) {
  return {
    ...f,
    usage_years: f.usage_years ? Number(f.usage_years) : null,
    inspection_interval_days: Number(f.inspection_interval_days) || 365,
    daily_rate: f.daily_rate || null,
  };
}

function TypeDetailBody({ type }: { type: ProductTypeOut }) {
  const roles = useMaterialRoles();
  const cart = useCart();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const navigate = useNavigate();
  const tags = useTags();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<TypeForm>(() => toForm(type));
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [manual, setManual] = useState<File | undefined>();
  const [adding, setAdding] = useState(false);
  const [deficit, setDeficit] = useState(false);
  const [sizeEditing, setSizeEditing] = useState<SizeOut | "new" | null>(null);

  // Saving sends the fields, then the manual if one was chosen in the form.
  const save = useApiMutation(
    async (body: TypeForm) => {
      await unwrap(
        client.PATCH("/api/material/types/{type_id}", {
          params: { path: { type_id: type.id } },
          body: fromForm(body),
        }),
      );
      if (manual) await postMultipart(`/api/material/types/${type.id}/manual`, { manual });
    },
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Gespeichert.");
        setManual(undefined);
        setEditing(false);
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
        client.DELETE("/api/material/types/{type_id}", { params: { path: { type_id: type.id } } }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Materialtyp gelöscht.");
        navigate(BASE);
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );

  const set = (patch: Partial<TypeForm>) => setForm({ ...form, ...patch });
  const text = (field: keyof TypeForm, label: string, value: string, inputType = "text"): DetailRow => ({
    label,
    field,
    value: value || "—",
    edit: (
      <input
        type={inputType}
        value={form[field] as string}
        onChange={(e) => set({ [field]: e.target.value } as Partial<TypeForm>)}
      />
    ),
  });
  const rows: DetailRow[] = [
    text("name", "Name", type.name),
    text("manufacturer", "Hersteller", type.manufacturer),
    text("product_group", "Produktgruppe", type.product_group),
    {
      label: "Beschreibung",
      field: "description",
      value: type.description || "—",
      edit: (
        <textarea rows={3} value={form.description} onChange={(e) => set({ description: e.target.value })} />
      ),
    },
    {
      label: "PSA",
      field: "is_psa",
      value: type.is_psa ? "ja" : "nein",
      edit: (
        <label className="inline-check">
          <input type="checkbox" checked={form.is_psa} onChange={(e) => set({ is_psa: e.target.checked })} />
          persönliche Schutzausrüstung
        </label>
      ),
    },
    text("article_number", "Artikelnummer", type.article_number),
    text("usage_years", "Nutzungsdauer (Jahre)", type.usage_years?.toString() ?? "", "number"),
    text(
      "inspection_interval_days",
      "Prüfintervall (Tage)",
      String(type.inspection_interval_days),
      "number",
    ),
    text("daily_rate", "Tagessatz", type.daily_rate ? euro(Number(type.daily_rate)) : "", "number"),
    {
      label: "Tags",
      field: "tags",
      value: type.tags.length ? type.tags.map((t) => t.name).join(", ") : "—",
      edit: (
        <MultiSelect
          options={(tags.data ?? []).map((t) => ({ value: t.id, label: t.name }))}
          selected={form.tags}
          onChange={(ids) => set({ tags: ids })}
        />
      ),
    },
    {
      label: "Gebrauchsanleitung",
      field: "manual",
      value: type.manual ? (
        <a href={mediaUrl(type.manual)} target="_blank" rel="noreferrer">
          öffnen
        </a>
      ) : (
        "—"
      ),
      edit: (
        <input
          type="file"
          accept="application/pdf"
          aria-label="Gebrauchsanleitung (PDF)"
          onChange={(e) => setManual(e.target.files?.[0])}
        />
      ),
    },
  ];


  const overview = (
    <div className="material-detail">
      <PhotoFrame
        src={type.photo}
        title={type.name}
        path={editing ? `/api/material/types/${type.id}/photo` : undefined}
      />
      <EditableDetail rows={rows} editing={editing} errors={errors} />
    </div>
  );

  const sized = type.sizes.length > 0 || type.parts?.length === 0;
  const sizes = (
    <section className="inline-section">
      <div className="inline-head">
        <h3 className="fieldset-title">Größen</h3>
        {roles.inventory && (
          <Button variant="ghost" onClick={() => setSizeEditing("new")}>
            Größe hinzufügen
          </Button>
        )}
      </div>
      <DataTable
        rows={type.sizes}
        rowKey={(s) => s.id}
        onRowClick={roles.inventory ? (s) => setSizeEditing(s) : undefined}
        empty="Keine Größen: die Teile dieses Typs haben eigene IDs."
        columns={[
          { header: "Größe", cell: (s) => s.name },
          { header: "Frei", cell: (s) => `${s.available} / ${s.quantity}` },
          { header: "Im Satz", cell: (s) => s.per_set || "—" },
          { header: "Gehört", cell: (s) => s.group?.name ?? "Sektion" },
          {
            header: "",
            className: "inline-actions",
            cell: (s) => (
              <Button
                variant="ghost"
                disabled={s.available === 0}
                aria-label={`${type.name} ${s.name} in den Korb`}
                onClick={(e) => {
                  e.stopPropagation();
                  cart.addSizes(type.name, [{ id: s.id, name: s.name, quantity: 1 }]);
                  toast.success(`${type.name} ${s.name} im Korb.`);
                }}
              >
                + Korb
              </Button>
            ),
          },
        ]}
      />
    </section>
  );

  const availability = (
    <div className="page-stack">
      <p>
        Im gewählten Zeitraum ({period(cart.start, cart.end)}) sind <strong>{type.available}</strong>{" "}
        von {type.total} frei.
      </p>
      <DataTable
        rows={type.groups}
        rowKey={(g) => String(g.id)}
        empty="Nichts frei."
        columns={[
          { header: "Gehört", cell: (g) => g.name || "Sektion" },
          { header: "Frei", cell: (g) => g.available },
          {
            header: "",
            cell: (g) => (g.needs_approval ? <Badge tone="warning">mit Freigabe</Badge> : null),
          },
        ]}
      />
    </div>
  );

  const calendar = (
    <DataTable
      rows={type.calendar}
      rowKey={(c) => `${c.start}-${c.end}-${c.borrower?.id}`}
      empty="Keine Reservierungen."
      columns={[
        { header: "Zeitraum", cell: (c) => period(c.start, c.end) },
        { header: "Anzahl", cell: (c) => c.count },
        { header: "Für", cell: (c) => c.borrower?.name ?? "—" },
        { header: "Status", cell: (c) => <ReservationStatus status={c.status} /> },
      ]}
    />
  );

  const tabs = [
    { id: "overview", label: "Übersicht", content: overview },
    ...(sized ? [{ id: "sizes", label: `Größen (${type.sizes.length})`, content: sizes }] : []),
    { id: "availability", label: "Verfügbarkeit", content: availability },
    { id: "calendar", label: "Belegung", content: calendar },
  ];
  if (type.parts && type.sizes.length === 0) {
    tabs.push({
      id: "parts",
      label: `Teile (${type.parts.length})`,
      content: (
        <DataTable
          rows={type.parts}
          rowKey={(p) => p.id}
          onRowClick={(p) => navigate(`${BASE}/parts/${p.id}`)}
          empty="Noch keine Teile."
          columns={[
            { header: "ID", cell: (p) => <span className="mono">{p.label}</span> },
            { header: "Gruppe", cell: (p) => p.group?.name ?? "Sektion" },
            { header: "Wo", cell: (p) => <Whereabouts part={p} /> },
            { header: "Status", cell: (p) => <PartStatus status={p.status} /> },
          ]}
        />
      ),
    });
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setErrors({});
        save.mutate(form);
      }}
    >
      <PageHeader
        breadcrumbs={[{ label: "Material", to: BASE }, { label: type.name }]}
        actions={
          editing ? (
            <>
              <Button variant="ghost" onClick={() => setEditing(false)}>
                Abbrechen
              </Button>
              <Button type="submit" busy={save.isPending}>
                Speichern
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              <Menu label="Aktionen">
                <Button variant="ghost" onClick={() => setDeficit(true)}>
                  Defizit melden
                </Button>
                {roles.inventory && (
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setForm(toForm(type));
                      setErrors({});
                      setManual(undefined);
                      setEditing(true);
                    }}
                  >
                    Bearbeiten
                  </Button>
                )}
                {roles.inventory && type.sizes.length === 0 && (
                  <Button variant="ghost" onClick={() => setAdding(true)}>
                    Teile hinzufügen
                  </Button>
                )}
                {roles.inventory && (
                  <Button
                    variant="danger"
                    onClick={async () => {
                      if (await confirm({ message: "Materialtyp löschen?", danger: true, confirmLabel: "Löschen" }))
                        remove.mutate(undefined);
                    }}
                  >
                    Löschen
                  </Button>
                )}
              </Menu>
              {type.sets !== null ? (
                <Button
                  disabled={type.sets === 0}
                  onClick={() => {
                    cart.addSizes(
                      type.name,
                      type.sizes.map((s) => ({ id: s.id, name: s.name, quantity: s.per_set })),
                    );
                    toast.success(`Ein Satz ${type.name} im Korb.`);
                  }}
                >
                  Satz in den Korb
                </Button>
              ) : (
                <Button
                  disabled={type.total === 0}
                  onClick={() => {
                    cart.addType(type);
                    toast.success(`${type.name} im Korb.`);
                  }}
                >
                  In den Korb
                </Button>
              )}
            </>
          )
        }
      />
      <WithCart>
        <Tabs tabs={tabs} />
      </WithCart>
      {deficit && (
        <DeficitModal productType={type} start={cart.start} end={cart.end} onClose={() => setDeficit(false)} />
      )}
      {adding && <AddPartsModal type={type} onClose={() => setAdding(false)} />}
      {sizeEditing && (
        <SizeModal
          typeId={type.id}
          size={sizeEditing === "new" ? null : sizeEditing}
          next={type.sizes.length + 1}
          onClose={() => setSizeEditing(null)}
        />
      )}
    </form>
  );
}

/** Add pieces of a type: one with its IDs, or several identical ones. */
export function AddPartsModal({
  type,
  onClose,
}: {
  type: Pick<ProductTypeOut, "id" | "name" | "is_psa">;
  onClose: () => void;
}) {
  const toast = useToast();
  const groups = useGroups();
  const locations = useLocations();
  const [form, setForm] = useState({
    count: "1",
    group: "",
    home_location: "",
    psa_id: "",
    serial_number: "",
    manufactured_on: "",
    buy_date: "",
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/material/parts", {
          body: {
            product_type: type.id,
            count: Number(form.count) || 1,
            group: form.group ? Number(form.group) : null,
            home_location: form.home_location ? Number(form.home_location) : null,
            psa_id: form.psa_id || null,
            serial_number: form.serial_number,
            manufactured_on: form.manufactured_on || null,
            buy_date: form.buy_date || null,
            note: "",
          },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: (parts) => {
        toast.success(parts.length === 1 ? "Teil angelegt." : `${parts.length} Teile angelegt.`);
        onClose();
      },
      onError: (e) => {
        if (e instanceof ApiError) setErrors(e.fieldErrors);
        toast.error(errorText(e));
      },
    },
  );
  const input = (key: keyof typeof form, label: string, inputType = "text") => (
    <Field label={label}>
      <input
        type={inputType}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
      {errors[key] && <div className="field-error">{errors[key].join(" ")}</div>}
    </Field>
  );
  return (
    <Modal title={`${type.name}: Teile hinzufügen`} onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          mutation.mutate(undefined);
        }}
      >
        {!type.is_psa && input("count", "Anzahl (ohne IDs)", "number")}
        {input("psa_id", type.is_psa ? "PSA-ID" : "PSA-ID (optional)")}
        {input("serial_number", "Seriennummer")}
        <div className="field-pair">
          {input("manufactured_on", "Herstellungsdatum", "date")}
          {input("buy_date", "Kaufdatum", "date")}
        </div>
        <Field label="Gehört">
          <Select
            value={form.group}
            onChange={(v) => setForm({ ...form, group: v })}
            allowEmpty
            emptyLabel="der Sektion"
            placeholder="der Sektion"
            options={(groups.data ?? []).map((g) => ({ value: g.id, label: g.name }))}
          />
        </Field>
        <Field label="Stammort">
          <Select
            value={form.home_location}
            onChange={(v) => setForm({ ...form, home_location: v })}
            allowEmpty
            options={(locations.data ?? []).map((l) => ({ value: l.id, label: l.name }))}
          />
        </Field>
        <ModalActions>
          <Button type="submit" busy={mutation.isPending}>
            Anlegen
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
}

/** Add or edit a size: its name, stock, how many go into a set, owner and place. */
function SizeModal({
  typeId,
  size,
  next,
  onClose,
}: {
  typeId: number;
  size: SizeOut | null;
  /** The position a new size takes. */
  next: number;
  onClose: () => void;
}) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const groups = useGroups();
  const locations = useLocations();
  const [form, setForm] = useState({
    name: size?.name ?? "",
    quantity: String(size?.quantity ?? 1),
    per_set: String(size?.per_set ?? 1),
    group: size?.group ? String(size.group.id) : "",
    location: size?.location ? String(size.location.id) : "",
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const body = () => ({
    name: form.name,
    quantity: Number(form.quantity) || 0,
    per_set: Number(form.per_set) || 0,
    group: form.group ? Number(form.group) : null,
    location: form.location ? Number(form.location) : null,
  });
  const save = useApiMutation(
    () =>
      size
        ? unwrap(
            client.PATCH("/api/material/sizes/{size_id}", {
              params: { path: { size_id: size.id } },
              body: body(),
            }),
          )
        : unwrap(
            client.POST("/api/material/types/{type_id}/sizes", {
              params: { path: { type_id: typeId } },
              body: { ...body(), position: next },
            }),
          ),
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
      unwrap(client.DELETE("/api/material/sizes/{size_id}", { params: { path: { size_id: size!.id } } })),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Größe gelöscht.");
        onClose();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  const input = (key: "name" | "quantity" | "per_set", label: string, inputType = "text") => (
    <Field label={label}>
      <input
        type={inputType}
        min={inputType === "number" ? 0 : undefined}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        required={key === "name"}
      />
      {errors[key] && <div className="field-error">{errors[key].join(" ")}</div>}
    </Field>
  );
  return (
    <Modal title={size ? `Größe ${size.name}` : "Neue Größe"} onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          save.mutate(undefined);
        }}
      >
        {input("name", "Größe")}
        <div className="field-pair">
          {input("quantity", "Bestand", "number")}
          {input("per_set", "Davon im Satz", "number")}
        </div>
        <Field label="Gehört">
          <Select
            value={form.group}
            onChange={(v) => setForm({ ...form, group: v })}
            allowEmpty
            emptyLabel="der Sektion"
            placeholder="der Sektion"
            options={(groups.data ?? []).map((g) => ({ value: g.id, label: g.name }))}
          />
        </Field>
        <Field label="Ort">
          <Select
            value={form.location}
            onChange={(v) => setForm({ ...form, location: v })}
            allowEmpty
            options={(locations.data ?? []).map((l) => ({ value: l.id, label: l.name }))}
          />
        </Field>
        <ModalActions>
          <Button type="submit" busy={save.isPending}>
            Speichern
          </Button>
          {size && (
            <Button
              variant="danger"
              busy={remove.isPending}
              onClick={async () => {
                if (await confirm({ message: "Größe löschen?", danger: true, confirmLabel: "Löschen" }))
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
