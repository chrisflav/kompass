import { useState } from "react";
import { Link } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  Badge,
  Button,
  DataTable,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  useConfirmDialog,
  useRowSelection,
  useToast,
} from "../../components/ui";
import {
  BASE,
  errorText,
  isoToday,
  linesText,
  MATERIAL,
  ModalActions,
  PartLink,
  period,
  PickupModal,
  ReservationStatus,
  ReturnModal,
  Section,
  shortDate,
  sizeName,
  HandOverModal,
  whereabouts,
  type OutstandingSize,
  type ReservationOut,
} from "./shared";

/** What I have, what I reserved, and the requests that wait for my decision. */
export function Mine() {
  const query = useApiQuery(["material", "mine"], () => unwrap(client.GET("/api/material/mine")));
  const requests = useApiQuery(["material", "reservations", "approvals"], () =>
    unwrap(client.GET("/api/material/reservations", { params: { query: { scope: "approvals" } } })),
  );
  const selection = useRowSelection<number>();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [dialog, setDialog] = useState<"" | "return" | "transfer">("");
  const [pickup, setPickup] = useState<ReservationOut | null>(null);
  const [returningSizes, setReturningSizes] = useState<OutstandingSize[] | null>(null);
  const cancel = useApiMutation(
    (id: number) =>
      unwrap(
        client.POST("/api/material/reservations/{reservation_id}/cancel", {
          params: { path: { reservation_id: id } },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => toast.success("Storniert."),
      onError: (e) => toast.error(errorText(e)),
    },
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Material", to: BASE }, { label: "Mein Material" }]}
        actions={
          <Link className="btn" to={BASE}>
            Material suchen
          </Link>
        }
      />
      <QueryBoundary query={query}>
        {(data) => {
          const selected = data.held.filter((p) => selection.selected.has(p.id));
          return (
            <div>
              {(requests.data ?? []).length > 0 && (
                <Section
                  title={
                    <>
                      Anfragen für deine Gruppen <Badge tone="warning">{requests.data!.length}</Badge>
                    </>
                  }
                >
                  <div className="page-stack">
                    {requests.data!.map((r) => (
                      <RequestCard key={r.id} reservation={r} />
                    ))}
                  </div>
                </Section>
              )}
              <Section
                title="Bei mir"
                actions={
                  selection.count > 0 && (
                    <>
                      <Button variant="ghost" onClick={() => setDialog("transfer")}>
                        {selection.count} übergeben
                      </Button>
                      <Button onClick={() => setDialog("return")}>{selection.count} zurückgeben</Button>
                    </>
                  )
                }
              >
                <div className="page-stack">
                  <DataTable
                    rows={data.held}
                    rowKey={(p) => p.id}
                    selection={{
                      selected: selection.selected,
                      onToggle: (k) => selection.toggle(k as number),
                      onToggleAll: (ks) => selection.toggleAll(ks as number[]),
                    }}
                    empty={data.held_sizes.length ? "Keine Teile mit ID." : "Du hast gerade kein Material."}
                    columns={[
                      { header: "Teil", cell: (p) => <PartLink part={p} /> },
                      { header: "Gehört", cell: (p) => p.group?.name ?? "Sektion" },
                      {
                        header: "Wie lange",
                        cell: (p) =>
                          p.overdue ? (
                            <Badge tone="danger">überfällig seit {shortDate(p.due)}</Badge>
                          ) : p.due ? (
                            `bis ${shortDate(p.due)}`
                          ) : (
                            "dauerhaft"
                          ),
                      },
                    ]}
                  />
                  {data.held_sizes.length > 0 && (
                    <DataTable
                      rows={data.held_sizes}
                      rowKey={(s) => s.id}
                      columns={[
                        { header: "Größe", cell: (s) => sizeName(s.size) },
                        { header: "Anzahl", cell: (s) => s.quantity },
                        {
                          header: "Wie lange",
                          cell: (s) =>
                            s.overdue ? (
                              <Badge tone="danger">überfällig seit {shortDate(s.due)}</Badge>
                            ) : (
                              `bis ${shortDate(s.due)}`
                            ),
                        },
                        {
                          header: "",
                          className: "inline-actions",
                          cell: (s) => (
                            <Button variant="ghost" onClick={() => setReturningSizes([s])}>
                              Zurückgeben
                            </Button>
                          ),
                        },
                      ]}
                    />
                  )}
                </div>
              </Section>
              <Section title="Meine Reservierungen">
                <DataTable
                  rows={data.reservations}
                  rowKey={(r) => r.id}
                  empty="Keine offenen Reservierungen."
                  columns={[
                    { header: "Zeitraum", cell: (r) => period(r.start, r.end) },
                    { header: "Material", cell: (r) => linesText(r) },
                    { header: "Status", cell: (r) => <ReservationStatus status={r.status} /> },
                    {
                      header: "",
                      className: "inline-actions",
                      cell: (r) => (
                        <span className="row-actions">
                          {r.status === "confirmed" && r.start <= isoToday() && (
                            <Button variant="ghost" onClick={() => setPickup(r)}>
                              Abholen
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            busy={cancel.isPending}
                            onClick={async () => {
                              if (await confirm({ message: "Reservierung stornieren?", confirmLabel: "Stornieren" }))
                                cancel.mutate(r.id);
                            }}
                          >
                            Stornieren
                          </Button>
                        </span>
                      ),
                    },
                  ]}
                />
              </Section>
              {dialog === "return" && (
                <ReturnModal
                  parts={selected}
                  onClose={() => setDialog("")}
                  onDone={() => {
                    setDialog("");
                    selection.clear();
                  }}
                />
              )}
              {returningSizes && (
                <ReturnModal
                  parts={[]}
                  sizes={returningSizes}
                  onClose={() => setReturningSizes(null)}
                  onDone={() => setReturningSizes(null)}
                />
              )}
              {dialog === "transfer" && (
                <HandOverModal
                  parts={selected}
                  onClose={() => setDialog("")}
                  onDone={() => {
                    setDialog("");
                    selection.clear();
                  }}
                />
              )}
              {pickup && (
                <PickupModal reservation={pickup} onClose={() => setPickup(null)} onDone={() => setPickup(null)} />
              )}
            </div>
          );
        }}
      </QueryBoundary>
    </div>
  );
}

export function RequestCard({ reservation }: { reservation: ReservationOut }) {
  const [deciding, setDeciding] = useState<{ group: number; approved: boolean } | null>(null);
  return (
    <article className="request-card">
      <div className="section-head">
        <div>
          <strong>{reservation.borrower.name}</strong>{" "}
          <span className="muted">{period(reservation.start, reservation.end)}</span>
        </div>
        <ReservationStatus status={reservation.status} />
      </div>
      {reservation.note && <p className="muted">{reservation.note}</p>}
      <ul className="plain-list">
        {reservation.parts.map((p) => (
          <li key={p.id}>
            <PartLink part={p} /> <span className="muted small">{p.group?.name ?? "Sektion"} · {whereabouts(p)}</span>
          </li>
        ))}
        {reservation.sizes.map((s) => (
          <li key={`s${s.size.id}`}>
            {s.quantity} × {sizeName(s.size)} <span className="muted small">{s.group?.name ?? "Sektion"}</span>
          </li>
        ))}
      </ul>
      {reservation.approvals
        .filter((a) => reservation.decidable_groups.includes(a.group.id))
        .map((a) => (
          <div key={a.group.id} className="row-actions">
            <span className="muted">Für {a.group.name}:</span>
            <Button variant="ghost" onClick={() => setDeciding({ group: a.group.id, approved: false })}>
              Ablehnen
            </Button>
            <Button onClick={() => setDeciding({ group: a.group.id, approved: true })}>Freigeben</Button>
          </div>
        ))}
      {deciding && (
        <DecisionModal
          reservation={reservation}
          group={deciding.group}
          approved={deciding.approved}
          onClose={() => setDeciding(null)}
        />
      )}
    </article>
  );
}

function DecisionModal({
  reservation,
  group,
  approved,
  onClose,
}: {
  reservation: ReservationOut;
  group: number;
  approved: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const [comment, setComment] = useState("");
  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/material/reservations/{reservation_id}/decide", {
          params: { path: { reservation_id: reservation.id } },
          body: { group, approved, comment },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success(approved ? "Freigegeben." : "Abgelehnt.");
        onClose();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <Modal title={approved ? "Anfrage freigeben" : "Anfrage ablehnen"} onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(undefined);
        }}
      >
        <Field label="Kommentar an die anfragende Person">
          <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
        </Field>
        <ModalActions>
          <Button type="submit" variant={approved ? "primary" : "danger"} busy={mutation.isPending}>
            {approved ? "Freigeben" : "Ablehnen"}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
}
