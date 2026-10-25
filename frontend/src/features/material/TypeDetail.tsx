import { Fragment, useId, useState } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

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
  setTypes,
  useLocations,
  useMaterialRoles,
  useTags,
  Whereabouts,
  type PartBrief,
  type ProductTypeOut,
  type SetEntryOut,
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
  const [entryEditing, setEntryEditing] = useState<SetEntryOut | "new" | null>(null);
  const formId = useId();

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
    ...(type.in_sets.length > 0
      ? [
          {
            label: "Teil von",
            value: (
              <span>
                {type.in_sets.map((s, i) => (
                  <Fragment key={s.id}>
                    {i > 0 && ", "}
                    <Link to={`${BASE}/types/${s.id}`}>{s.name}</Link>
                  </Fragment>
                ))}
              </span>
            ),
          },
        ]
      : []),
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

  // A set is made of other types; a type without pieces or sizes of its own may
  // become one, unless it belongs to a set itself.
  const isSet = type.set_entries.length > 0;
  const empty = type.sizes.length === 0 && type.parts?.length === 0;
  const setShown = isSet || (roles.inventory && empty && type.in_sets.length === 0);
  const sized = !isSet && (type.sizes.length > 0 || type.parts?.length === 0);
  const entries = (
    <section className="inline-section">
      <div className="inline-head">
        <h3 className="fieldset-title">Satz</h3>
        {roles.inventory && (
          <Button variant="ghost" onClick={() => setEntryEditing("new")}>
            Typ hinzufügen
          </Button>
        )}
      </div>
      <p className="muted small">
        Ein Satz besteht aus Teilen anderer Typen. Wer ihn in den Korb legt, bekommt sie alle; jedes
        Teil lässt sich weiter auch einzeln ausleihen.
      </p>
      <DataTable
        rows={type.set_entries}
        rowKey={(e) => e.id}
        onRowClick={roles.inventory ? (e) => setEntryEditing(e) : undefined}
        empty="Noch kein Satz: füge die Typen hinzu, aus denen er besteht."
        columns={[
          {
            header: "Typ",
            cell: (e) => (
              <Link to={`${BASE}/types/${e.product_type.id}`} onClick={(ev) => ev.stopPropagation()}>
                {e.product_type.name}
              </Link>
            ),
          },
          { header: "Im Satz", cell: (e) => e.per_set },
          { header: "Frei", cell: (e) => e.available },
        ]}
      />
    </section>
  );
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
        von {type.total} {isSet ? "Sätzen " : ""}frei.
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
    ...(setShown ? [{ id: "set", label: `Satz (${type.set_entries.length})`, content: entries }] : []),
    ...(sized ? [{ id: "sizes", label: `Größen (${type.sizes.length})`, content: sizes }] : []),
    { id: "availability", label: "Verfügbarkeit", content: availability },
    { id: "calendar", label: "Belegung", content: calendar },
  ];
  // Retired pieces are out of the stock but still on record; they are listed
  // apart, and deleting the type deletes them too.
  const retired = type.retired_parts ?? [];
  const partColumns = [
    { header: "ID", cell: (p: PartBrief) => <span className="mono">{p.label}</span> },
    { header: "Gruppe", cell: (p: PartBrief) => p.group?.name ?? "Sektion" },
    { header: "Wo", cell: (p: PartBrief) => <Whereabouts part={p} /> },
    { header: "Status", cell: (p: PartBrief) => <PartStatus status={p.status} /> },
  ];
  if (type.parts && type.sizes.length === 0 && !isSet) {
    tabs.push({
      id: "parts",
      label: `Teile (${type.parts.length})`,
      content: (
        <>
          <DataTable
            rows={type.parts}
            rowKey={(p) => p.id}
            onRowClick={(p) => navigate(`${BASE}/parts/${p.id}`)}
            empty="Noch keine Teile."
            columns={partColumns}
          />
          {retired.length > 0 && (
            <section className="inline-section">
              <h3 className="fieldset-title">Ausgesondert ({retired.length})</h3>
              <DataTable
                rows={retired}
                rowKey={(p) => p.id}
                onRowClick={(p) => navigate(`${BASE}/parts/${p.id}`)}
                columns={partColumns}
              />
            </section>
          )}
        </>
      ),
    });
  }

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: "Material", to: BASE }, { label: type.name }]}
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
                {roles.inventory && type.sizes.length === 0 && !isSet && (
                  <Button variant="ghost" onClick={() => setAdding(true)}>
                    Teile hinzufügen
                  </Button>
                )}
                {roles.inventory && (
                  <Button
                    variant="danger"
                    onClick={async () => {
                      const message =
                        retired.length === 0
                          ? "Materialtyp löschen?"
                          : `Materialtyp löschen? ${
                              retired.length === 1
                                ? "Das ausgesonderte Teil wird"
                                : `Die ${retired.length} ausgesonderten Teile werden`
                            } mit ihm gelöscht, samt Prüfungen und Ausleihen.`;
                      if (await confirm({ message, danger: true, confirmLabel: "Löschen" }))
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
                    if (isSet) cart.addSet(type.name, setTypes(type));
                    else
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
                    cart.addType({ id: type.id, name: type.name });
                    toast.success(`${type.name} im Korb.`);
                  }}
                >
                  In den Korb
                </Button>
              )}
            </Fragment>
          )
        }
      />
      {/* The cart sits beside the form, not in it: Enter in its fields does not save the type. */}
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
      {entryEditing && (
        <SetEntryModal
          type={type}
          entry={entryEditing === "new" ? null : entryEditing}
          onClose={() => setEntryEditing(null)}
        />
      )}
    </>
  );
}

/** Add a type to a set, or change how many of it go into one set. */
function SetEntryModal({
  type,
  entry,
  onClose,
}: {
  type: Pick<ProductTypeOut, "id" | "name" | "set_entries">;
  entry: SetEntryOut | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [productType, setProductType] = useState("");
  const [perSet, setPerSet] = useState(String(entry?.per_set ?? 1));
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const types = useApiQuery(["material", "types", "set-candidates"], () =>
    unwrap(client.GET("/api/material/types")),
  );
  // Sets are not nested, and a type is in a set once.
  const taken = new Set([type.id, ...type.set_entries.map((e) => e.product_type.id)]);
  const options = (types.data ?? [])
    .filter((t) => !taken.has(t.id) && t.set_entries.length === 0)
    .map((t) => ({ value: t.id, label: t.name }));
  const save = useApiMutation(
    () =>
      entry
        ? unwrap(
            client.PATCH("/api/material/set-entries/{entry_id}", {
              params: { path: { entry_id: entry.id } },
              body: { per_set: Number(perSet) || 0 },
            }),
          )
        : unwrap(
            client.POST("/api/material/types/{type_id}/set-entries", {
              params: { path: { type_id: type.id } },
              body: {
                product_type: Number(productType),
                per_set: Number(perSet) || 0,
                position: type.set_entries.length + 1,
              },
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
      unwrap(
        client.DELETE("/api/material/set-entries/{entry_id}", {
          params: { path: { entry_id: entry!.id } },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Aus dem Satz genommen.");
        onClose();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <Modal
      title={entry ? `${entry.product_type.name} im Satz ${type.name}` : `${type.name}: Typ hinzufügen`}
      onClose={onClose}
      size="sm"
    >
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          if (!entry && !productType) {
            toast.error("Wähle einen Typ.");
            return;
          }
          save.mutate(undefined);
        }}
      >
        {!entry && (
          <Field label="Typ">
            <Select value={productType} onChange={setProductType} options={options} />
            {errors.product_type && <div className="field-error">{errors.product_type.join(" ")}</div>}
          </Field>
        )}
        <Field label="Im Satz">
          <input type="number" min={1} value={perSet} onChange={(e) => setPerSet(e.target.value)} />
          {errors.per_set && <div className="field-error">{errors.per_set.join(" ")}</div>}
        </Field>
        <ModalActions>
          <Button type="submit" busy={save.isPending}>
            Speichern
          </Button>
          {entry && (
            <Button
              variant="danger"
              busy={remove.isPending}
              onClick={async () => {
                if (
                  await confirm({
                    message: `${entry.product_type.name} aus dem Satz nehmen?`,
                    danger: true,
                    confirmLabel: "Herausnehmen",
                  })
                )
                  remove.mutate(undefined);
              }}
            >
              Herausnehmen
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

/**
 * Add pieces of a type: one with its IDs, or several identical ones. With
 * ``parent``, the new pieces are built into it.
 */
export function AddPartsModal({
  type,
  parent,
  onClose,
}: {
  type: Pick<ProductTypeOut, "id" | "name" | "is_psa">;
  parent?: Pick<PartBrief, "id" | "label" | "product_type">;
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
            parent: parent?.id ?? null,
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
    <Modal
      title={
        parent
          ? `${type.name} in ${parent.product_type.name} ${parent.label} einbauen`
          : `${type.name}: Teile hinzufügen`
      }
      onClose={onClose}
    >
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
