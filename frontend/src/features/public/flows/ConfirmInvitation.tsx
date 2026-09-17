import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, DetailList, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, useFlowKey } from "./shared";

type InvitationDetailOut = components["schemas"]["InvitationDetailOut"];
type ConfirmInvitationOut = components["schemas"]["ConfirmInvitationOut"];

/** Accept a group invitation (``/api/members/public/confirm-invitation/{key}``). */
export function ConfirmInvitationFlow() {
  const key = useFlowKey();
  const query = useApiQuery(
    ["public", "confirm-invitation", key],
    () =>
      unwrap(
        client.GET("/api/members/public/confirm-invitation/{key}", {
          params: { path: { key } },
        }),
      ),
    { enabled: key !== "", retry: false },
  );

  if (!key) {
    return (
      <FlowShell title="Einladung annehmen">
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      </FlowShell>
    );
  }

  return (
    <FlowShell title="Einladung annehmen">
      <QueryBoundary query={query}>
        {(data: InvitationDetailOut) => <ConfirmStep flowKey={key} detail={data} />}
      </QueryBoundary>
    </FlowShell>
  );
}

function ConfirmStep({ flowKey, detail }: { flowKey: string; detail: InvitationDetailOut }) {
  const [done, setDone] = useState<ConfirmInvitationOut | null>(null);

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/members/public/confirm-invitation/{key}", {
          params: { path: { key: flowKey } },
        }),
      ),
    { onSuccess: (data: ConfirmInvitationOut) => setDone(data) },
  );

  if (done) {
    return (
      <FlowResult tone="success">
        Super! Du hast die Einladung in die Gruppe <strong>{done.groupname}</strong> angenommen. Wir
        freuen uns auf dich!
      </FlowResult>
    );
  }

  const items: [string, string][] = [["Gruppe", detail.groupname], ["Termine", detail.timeinfo]];
  if (detail.contact_email) items.push(["Kontakt", detail.contact_email]);

  return (
    <div className="stack">
      <p className="muted">Du wurdest in eine Gruppe eingeladen:</p>
      <DetailList items={items} />
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button onClick={() => mutation.mutate(undefined)} busy={mutation.isPending}>
          Einladung annehmen
        </Button>
      </div>
    </div>
  );
}
