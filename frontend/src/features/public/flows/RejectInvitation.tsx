import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, DetailList, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, useFlowKey } from "./shared";

type InvitationDetailOut = components["schemas"]["InvitationDetailOut"];
type RejectInvitationOut = components["schemas"]["RejectInvitationOut"];

/** Reject a group invitation (``/api/members/public/reject-invitation/{key}``). */
export function RejectInvitationFlow() {
  const key = useFlowKey();
  const query = useApiQuery(
    ["public", "reject-invitation", key],
    () =>
      unwrap(
        client.GET("/api/members/public/reject-invitation/{key}", {
          params: { path: { key } },
        }),
      ),
    { enabled: key !== "", retry: false },
  );

  if (!key) {
    return (
      <FlowShell title="Einladung ablehnen">
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      </FlowShell>
    );
  }

  return (
    <FlowShell title="Einladung ablehnen">
      <QueryBoundary query={query}>
        {(data: InvitationDetailOut) => <RejectStep flowKey={key} detail={data} />}
      </QueryBoundary>
    </FlowShell>
  );
}

function RejectStep({ flowKey, detail }: { flowKey: string; detail: InvitationDetailOut }) {
  const [done, setDone] = useState<RejectInvitationOut | null>(null);

  const mutation = useApiMutation(
    (action: "reject" | "leave") =>
      unwrap(
        client.POST("/api/members/public/reject-invitation/{key}", {
          params: { path: { key: flowKey } },
          body: { action },
        }),
      ),
    { onSuccess: (data: RejectInvitationOut) => setDone(data) },
  );

  if (done) {
    return (
      <FlowResult tone="success">
        Du hast die Einladung in die Gruppe <strong>{done.groupname}</strong> abgelehnt.
        {done.left_waitinglist
          ? " Du wurdest außerdem von der Warteliste entfernt."
          : " Du bleibst weiterhin auf der Warteliste."}
      </FlowResult>
    );
  }

  const items: [string, string][] = [["Gruppe", detail.groupname], ["Termine", detail.timeinfo]];
  if (detail.contact_email) items.push(["Kontakt", detail.contact_email]);

  return (
    <div className="stack">
      <p className="muted">
        Möchtest du die Einladung in diese Gruppe ablehnen? Du kannst zusätzlich die Warteliste
        verlassen.
      </p>
      <DetailList items={items} />
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button variant="ghost" onClick={() => mutation.mutate("reject")} busy={mutation.isPending}>
          Nur ablehnen (Warteliste behalten)
        </Button>
        <Button variant="danger" onClick={() => mutation.mutate("leave")} busy={mutation.isPending}>
          Ablehnen und Warteliste verlassen
        </Button>
      </div>
    </div>
  );
}
