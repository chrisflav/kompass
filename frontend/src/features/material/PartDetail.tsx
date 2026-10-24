import { Fragment, useId, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useMe } from "../../api/me";
import { useGroups } from "../../api/queries";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  formatDate,
  Menu,
  Modal,
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
  isoToday,
  MATERIAL,
  mediaUrl,
  ModalActions,
  HandOverModal,
  PartLink,
  PhotoFrame,
  PartStatus,
  period,
  postMultipart,
  ReservationStatus,
  ReturnModal,
  useLocations,
  useMaterialRoles,
  Whereabouts,
  type PartOut,
} from "./shared";

const KIND: Record<string, string> = {
  checkout: "Ausleihe",
  return: "Rückgabe",
  transfer: "Übergabe",
  assemble: "Zusammenbau",
  retire: "Aussonderung",
};

function count(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

/** What deleting the piece would erase, as a list for the warning; empty if nothing. */
function historyText(part: PartOut): string {
  const h = part.history ?? { loans: 0, reservations: 0, inspections: 0, handovers: 0 };
  return [
    h.loans > 0 && count(h.loans, "Ausleihe", "Ausleihen"),
    h.reservations > 0 && count(h.reservations, "vergangene Reservierung", "vergangene Reservierungen"),
    h.inspections > 0 && count(h.inspections, "Prüfung", "Prüfungen"),
    h.handovers > 0 && count(h.handovers, "Übergabe", "Übergaben"),
  ]
    .filter(Boolean)
    .join(", ");
}

export function PartDetailPage() {
  const { id } = useParams();
  const partId = Number(id);
  const query = useApiQuery(["material", "parts", partId], () =>
    unwrap(client.GET("/api/material/parts/{part_id}", { params: { path: { part_id: partId } } })),
  );
  // Keyed by the piece, so following a link to another piece starts afresh
  // rather than keeping the edit form of this one.
  return <QueryBoundary query={query}>{(part) => <PartDetailBody key={part.id} part={part} />}</QueryBoundary>;
}

type PartForm = {
  group: string;
  psa_id: string;
  serial_number: string;
  manufactured_on: string;
  buy_date: string;
  note: string;
  home_location: string;
};

function toForm(p: PartOut): PartForm {
  return {
    group: p.group ? String(p.group.id) : "",
    psa_id: p.psa_id ?? "",
    serial_number: p.serial_number,
    manufactured_on: p.manufactured_on ?? "",
    buy_date: p.buy_date ?? "",
    note: p.note,
    home_location: p.home_location ? String(p.home_location.id) : "",
  };
}

function PartDetailBody({ part }: { part: PartOut }) {
  const roles = useMaterialRoles();
  const me = useMe();
  const cart = useCart();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const navigate = useNavigate();
  // The groups one leads, for passing on their pieces; every group for the inventory.
  const groups = useGroups({ enabled: roles.inventory || part.group !== null });
  const locations = useLocations();
  const formId = useId();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<PartForm>(() => toForm(part));
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [dialog, setDialog] = useState<"" | "return" | "transfer" | "inspect" | "deficit">("");

  const memberId = me.data?.member_id ?? null;
  const mine = part.holder !== null && part.holder.id === memberId;
  // A lent piece can still be reserved for later; a piece built into another goes with it.
  const bookable = part.status === "active" && !part.parent;
  // Who may pass the piece on: who has it, the leaders of the group it belongs
  // to (unless it is lent to someone else just now), and the material team.
  const leads =
    part.group !== null &&
    (groups.data ?? []).some(
      (g) => g.id === part.group!.id && g.leiters.some((l) => l.id === memberId),
    );
  const canHandOver = mine || roles.manager || (leads && part.lent_until === null);
  // The material team takes back what is out with someone.
  const canTakeBack = mine || (roles.manager && (part.holder !== null || part.lent_until !== null));

  const save = useApiMutation(
    (f: PartForm) =>
      unwrap(
        client.PATCH("/api/material/parts/{part_id}", {
          params: { path: { part_id: part.id } },
          body: {
            group: f.group ? Number(f.group) : null,
            psa_id: f.psa_id,
            serial_number: f.serial_number,
            manufactured_on: f.manufactured_on || null,
            buy_date: f.buy_date || null,
            note: f.note,
            home_location: f.home_location ? Number(f.home_location) : null,
          },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Gespeichert.");
        setEditing(false);
      },
      onError: (e) => {
        if (e instanceof ApiError) setErrors(e.fieldErrors);
        toast.error(errorText(e));
      },
    },
  );

  const remove = useApiMutation(
    () => unwrap(client.DELETE("/api/material/parts/{part_id}", { params: { path: { part_id: part.id } } })),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Teil gelöscht.");
        cart.remove(`p${part.id}`);
        navigate(`${BASE}/types/${part.product_type.id}`);
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  const confirmRemove = async () => {
    // Its loan is the only one its components are lent on, so it comes back first.
    if (part.lent_until !== null) {
      toast.error("Ein verliehenes Teil muss vor dem Löschen zurückgenommen werden.");
      return;
    }
    const history = historyText(part);
    const ok = history
      ? await confirm({
          title: "Teil mit Verlauf löschen?",
          message: [
            `Mit dem Teil wird sein Verlauf gelöscht: ${history}. Kommende Reservierungen bekommen, wenn möglich, ein anderes Teil.`,
            part.status !== "retired" &&
              "Wird das Teil nicht mehr benutzt, sondere es besser über eine Prüfung aus. Dann bleibt der Verlauf erhalten.",
          ]
            .filter(Boolean)
            .join(" "),
          danger: true,
          confirmLabel: "Trotzdem löschen",
        })
      : await confirm({ message: "Teil löschen?", danger: true, confirmLabel: "Löschen" });
    if (ok) remove.mutate(undefined);
  };

  const input = (field: keyof PartForm, inputType = "text") => (
    <input
      type={inputType}
      value={form[field]}
      onChange={(e) => setForm({ ...form, [field]: e.target.value })}
    />
  );
  const rows: DetailRow[] = [
    { label: "Typ", value: part.product_type.name },
    {
      label: "Gehört",
      field: "group",
      value: part.group?.name ?? "Sektion",
      edit: (
        <Select
          value={form.group}
          onChange={(v) => setForm({ ...form, group: v })}
          allowEmpty
          emptyLabel="der Sektion"
          options={(groups.data ?? []).map((g) => ({ value: g.id, label: g.name }))}
        />
      ),
    },
    { label: "Wo", value: <Whereabouts part={part} /> },
    { label: "Status", value: <PartStatus status={part.status} /> },
    { label: "PSA-ID", field: "psa_id", value: part.psa_id ?? "—", edit: input("psa_id") },
    {
      label: "Seriennummer",
      field: "serial_number",
      value: part.serial_number || "—",
      edit: input("serial_number"),
    },
    {
      label: "Herstellungsdatum",
      field: "manufactured_on",
      value: formatDate(part.manufactured_on),
      edit: input("manufactured_on", "date"),
    },
    {
      label: "Kaufdatum",
      field: "buy_date",
      value: formatDate(part.buy_date),
      edit: input("buy_date", "date"),
    },
    {
      label: "Stammort",
      field: "home_location",
      value: part.home_location?.name ?? "—",
      edit: (
        <Select
          value={form.home_location}
          onChange={(v) => setForm({ ...form, home_location: v })}
          allowEmpty
          options={(locations.data ?? []).map((l) => ({ value: l.id, label: l.name }))}
        />
      ),
    },
    { label: "Notiz", field: "note", value: part.note || "—", edit: input("note") },
    {
      label: "Nächste Prüfung",
      value: part.next_inspection ? (
        <>
          {formatDate(part.next_inspection)}{" "}
          {part.next_inspection < isoToday() && <Badge tone="danger">überfällig</Badge>}
        </>
      ) : (
        "—"
      ),
    },
  ];
  if (part.past_usage_period) {
    rows.push({ label: "Nutzungsdauer", value: <Badge tone="danger">überschritten</Badge> });
  }
  if (part.parent) {
    rows.push({ label: "Bestandteil von", value: <PartLink part={part.parent} /> });
  }

  const tabs = [
    {
      id: "overview",
      label: "Übersicht",
      content: (
        <div className="material-detail">
          <PhotoFrame
            src={part.photo}
            title={`${part.product_type.name} ${part.label}`}
            path={editing ? `/api/material/parts/${part.id}/photo` : undefined}
          />
          <EditableDetail rows={rows} editing={editing} errors={errors} />
        </div>
      ),
    },
    {
      id: "reservations",
      label: "Reservierungen",
      content: (
        <DataTable
          rows={part.reservations}
          rowKey={(r) => r.id}
          empty="Nicht reserviert."
          columns={[
            { header: "Zeitraum", cell: (r) => period(r.start, r.end) },
            { header: "Für", cell: (r) => r.borrower.name },
            { header: "Status", cell: (r) => <ReservationStatus status={r.status} /> },
          ]}
        />
      ),
    },
  ];
  if (part.components.length > 0) {
    tabs.push({
      id: "components",
      label: "Bestandteile",
      content: (
        <DataTable
          rows={part.components}
          rowKey={(c) => c.id}
          columns={[
            { header: "Teil", cell: (c) => <PartLink part={c} /> },
            { header: "Status", cell: (c) => <PartStatus status={c.status} /> },
          ]}
        />
      ),
    });
  }
  if (part.inspections) {
    tabs.push({
      id: "inspections",
      label: "Prüfungen",
      content: (
        <DataTable
          rows={part.inspections}
          rowKey={(i) => i.id}
          empty="Noch nicht geprüft."
          columns={[
            { header: "Datum", cell: (i) => formatDate(i.date) },
            {
              header: "Ergebnis",
              cell: (i) =>
                i.result === "ok" ? <Badge tone="success">ok</Badge> : <Badge tone="danger">ausgesondert</Badge>,
            },
            { header: "Prüfer*in", cell: (i) => i.inspector?.name ?? "—" },
            { header: "Kommentar", cell: (i) => i.comment || "—" },
            {
              header: "Foto",
              cell: (i) =>
                i.photo ? (
                  <a href={mediaUrl(i.photo)} target="_blank" rel="noreferrer">
                    ansehen
                  </a>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      ),
    });
  }
  if (part.custody) {
    tabs.push({
      id: "custody",
      label: "Verlauf",
      content: (
        <DataTable
          rows={part.custody}
          rowKey={(e) => e.id}
          empty="Noch nichts passiert."
          columns={[
            { header: "Wann", cell: (e) => new Date(e.at).toLocaleString("de-DE") },
            { header: "Was", cell: (e) => KIND[e.kind] ?? e.kind },
            { header: "Von", cell: (e) => e.from_name ?? "—" },
            { header: "An", cell: (e) => e.to_name ?? "—" },
            { header: "Eingetragen von", cell: (e) => e.by?.name ?? "—" },
          ]}
        />
      ),
    });
  }

  const title = `${part.product_type.name} ${part.label}`;
  return (
    <>
      <PageHeader
        breadcrumbs={[
          { label: "Material", to: BASE },
          { label: part.product_type.name, to: `${BASE}/types/${part.product_type.id}` },
          { label: part.label },
        ]}
        actions={
          editing ? (
            <Fragment key="edit">
              <Button variant="ghost" onClick={() => setEditing(false)}>
                Abbrechen
              </Button>
              <Button type="submit" form={formId} busy={save.isPending}>
                Speichern
              </Button>
            </Fragment>
          ) : (
            <Fragment key="view">
              <Button variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              <Menu label="Aktionen">
                <Button variant="ghost" onClick={() => setDialog("deficit")}>
                  Defizit melden
                </Button>
                {roles.inventory && part.status !== "retired" && (
                  <Button variant="ghost" onClick={() => setDialog("inspect")}>
                    Prüfung eintragen
                  </Button>
                )}
                {roles.inventory && (
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setForm(toForm(part));
                      setErrors({});
                      setEditing(true);
                    }}
                  >
                    Bearbeiten
                  </Button>
                )}
                {roles.inventory && (
                  <Button variant="danger" onClick={confirmRemove}>
                    Löschen
                  </Button>
                )}
              </Menu>
              {/* What one has is handed over or given back; anything else goes in the cart. */}
              {canHandOver && (
                <Button variant="ghost" onClick={() => setDialog("transfer")}>
                  Übergeben
                </Button>
              )}
              {canTakeBack && (
                <Button variant={mine ? "primary" : "ghost"} onClick={() => setDialog("return")}>
                  {mine ? "Zurückgeben" : "Zurücknehmen"}
                </Button>
              )}
              {!mine && bookable && (
                <Button
                  onClick={() => {
                    cart.addPart(part);
                    toast.success(`${title} im Korb.`);
                  }}
                >
                  In den Korb
                </Button>
              )}
            </Fragment>
          )
        }
      />
      {/* The cart sits beside the form, not in it: Enter in its fields does not save the piece. */}
      <WithCart>
        <form
          id={formId}
          onSubmit={(e) => {
            e.preventDefault();
            setErrors({});
            save.mutate(form);
          }}
        >
          <Tabs tabs={tabs} />
        </form>
      </WithCart>
      {dialog === "deficit" && (
        <DeficitModal productType={part.product_type} onClose={() => setDialog("")} />
      )}
      {dialog === "return" && (
        <ReturnModal parts={[part]} onClose={() => setDialog("")} onDone={() => setDialog("")} />
      )}
      {dialog === "transfer" && (
        <HandOverModal parts={[part]} onClose={() => setDialog("")} onDone={() => setDialog("")} />
      )}
      {dialog === "inspect" && <InspectionModal part={part} onClose={() => setDialog("")} />}
    </>
  );
}

function InspectionModal({ part, onClose }: { part: PartOut; onClose: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ result: "ok", date: isoToday(), comment: "" });
  const [file, setFile] = useState<File | null>(null);
  const mutation = useApiMutation(
    () =>
      postMultipart(`/api/material/parts/${part.id}/inspections`, {
        result: form.result,
        date: form.date,
        comment: form.comment,
        photo: file,
      }),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success(form.result === "ok" ? "Prüfung eingetragen." : "Teil ausgesondert.");
        onClose();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <Modal title="Prüfung eintragen" onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(undefined);
        }}
      >
        <Field label="Ergebnis">
          <Select
            value={form.result}
            onChange={(v) => setForm({ ...form, result: v })}
            options={[
              { value: "ok", label: "in Ordnung" },
              { value: "retired", label: "aussondern" },
            ]}
          />
        </Field>
        <Field label="Datum">
          <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </Field>
        <Field label="Kommentar">
          <textarea rows={3} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
        </Field>
        <Field label="Foto">
          <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        {form.result === "retired" && (
          <p className="error small">Ein ausgesondertes Teil kann nicht mehr verliehen werden.</p>
        )}
        <ModalActions>
          <Button type="submit" variant={form.result === "ok" ? "primary" : "danger"} busy={mutation.isPending}>
            Eintragen
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
}
