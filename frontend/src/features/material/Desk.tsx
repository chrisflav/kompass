import { useState } from "react";

import { client, unwrap } from "../../api/http";
import { useApiQuery } from "../../api/hooks";
import {
  Badge,
  Button,
  DataTable,
  DownloadButton,
  EmptyState,
  PageHeader,
  QueryBoundary,
} from "../../components/ui";
import { RequestCard } from "./Mine";
import {
  BASE,
  HandOverModal,
  linesText,
  PartLink,
  period,
  PickupModal,
  ReturnModal,
  Section,
  shortDate,
  sizeName,
  type LoanOut,
  type OutstandingSize,
  type PartBrief,
  type ReservationOut,
} from "./shared";

/** What of a loan is still out. */
function outstanding(loan: LoanOut): { parts: PartBrief[]; sizes: OutstandingSize[] } {
  return {
    parts: loan.lines.filter((line) => line.returned_at === null).map((line) => line.part),
    sizes: loan.sizes
      .filter((s) => s.returned < s.quantity)
      .map((s) => ({ id: s.id, size: s.size, quantity: s.quantity - s.returned })),
  };
}

type Returning = ReturnType<typeof outstanding>;

function LoanTable({
  loans,
  empty,
  onReturn,
}: {
  loans: LoanOut[];
  empty: string;
  onReturn: (what: Returning) => void;
}) {
  return (
    <DataTable
      rows={loans}
      rowKey={(l) => l.id}
      empty={empty}
      columns={[
        { header: "Wer", cell: (l) => l.borrower.name },
        {
          header: "Was",
          cell: (l) => {
            const out = outstanding(l);
            return [
              ...out.parts.map((p) => `${p.product_type.name} ${p.label}`),
              ...out.sizes.map((s) => `${s.quantity} × ${sizeName(s.size)}`),
            ].join(", ");
          },
        },
        {
          header: "Bis",
          cell: (l) => (l.overdue ? <Badge tone="danger">{shortDate(l.due)}</Badge> : shortDate(l.due)),
        },
        {
          header: "",
          className: "inline-actions",
          cell: (l) => (
            <span className="row-actions">
              <DownloadButton path={`/api/material/loans/${l.id}/receipt`} filename={`Leihschein_${l.id}.pdf`}>
                Leihschein
              </DownloadButton>
              <Button
                variant="ghost"
                onClick={() => onReturn(outstanding(l))}
              >
                Zurücknehmen
              </Button>
            </span>
          ),
        },
      ]}
    />
  );
}

/** The desk's day: pickups, returns, overdue loans, open requests and pieces to inspect. */
export function Desk() {
  const query = useApiQuery(["material", "desk"], () => unwrap(client.GET("/api/material/desk")));
  const [pickup, setPickup] = useState<ReservationOut | null>(null);
  const [returning, setReturning] = useState<Returning | null>(null);
  const [lending, setLending] = useState(false);
  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Material", to: BASE }, { label: "Ausgabe" }]}
        actions={<Button onClick={() => setLending(true)}>Übergeben</Button>}
      />
      <QueryBoundary query={query}>
        {(desk) => (
          <div className="dash-columns">
            <Section title="Abholungen heute und morgen">
              <DataTable
                rows={desk.pickups}
                rowKey={(r) => r.id}
                empty="Keine Abholungen."
                columns={[
                  { header: "Wer", cell: (r) => r.borrower.name },
                  { header: "Wann", cell: (r) => period(r.start, r.end) },
                  { header: "Was", cell: (r) => linesText(r) },
                  {
                    header: "",
                    className: "inline-actions",
                    cell: (r) => (
                      <Button variant="ghost" onClick={() => setPickup(r)}>
                        Ausgeben
                      </Button>
                    ),
                  },
                ]}
              />
            </Section>
            <Section title="Heute zurück">
              <LoanTable loans={desk.due} empty="Heute kommt nichts zurück." onReturn={setReturning} />
            </Section>
            <Section title="Überfällig">
              <LoanTable loans={desk.overdue} empty="Nichts überfällig." onReturn={setReturning} />
            </Section>
            <Section title="Zu prüfen">
              <DataTable
                rows={desk.inspection_due}
                rowKey={(p) => p.id}
                empty="Nichts zu prüfen."
                columns={[{ header: "Teil", cell: (p) => <PartLink part={p} /> }]}
              />
            </Section>
            <Section title="Offene Anfragen">
              {desk.requests.length === 0 ? (
                <EmptyState>Keine offenen Anfragen.</EmptyState>
              ) : (
                <div className="page-stack">
                  {desk.requests.map((r) => (
                    <RequestCard key={r.id} reservation={r} />
                  ))}
                </div>
              )}
            </Section>
          </div>
        )}
      </QueryBoundary>
      {pickup && (
        <PickupModal reservation={pickup} forBorrower onClose={() => setPickup(null)} onDone={() => setPickup(null)} />
      )}
      {returning && (
        <ReturnModal
          parts={returning.parts}
          sizes={returning.sizes}
          onClose={() => setReturning(null)}
          onDone={() => setReturning(null)}
        />
      )}
      {lending && (
        <HandOverModal parts={[]} desk onClose={() => setLending(false)} onDone={() => setLending(false)} />
      )}
    </div>
  );
}
