import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, useFlowKey } from "./shared";

type WaiterOut = components["schemas"]["LeaveWaitingOut"];

/** Leave the waiting list (``/api/members/public/leave-waitinglist/{key}``). */
export function LeaveWaitingListFlow() {
  const key = useFlowKey();
  const query = useApiQuery(
    ["public", "leave-waitinglist", key],
    () =>
      unwrap(
        client.GET("/api/members/public/leave-waitinglist/{key}", {
          params: { path: { key } },
        }),
      ),
    { enabled: key !== "", retry: false },
  );

  if (!key) {
    return (
      <FlowShell title="Warteliste verlassen">
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      </FlowShell>
    );
  }

  return (
    <FlowShell title="Warteliste verlassen">
      <QueryBoundary query={query}>
        {(data: WaiterOut) => <LeaveConfirm flowKey={key} name={data.name} />}
      </QueryBoundary>
    </FlowShell>
  );
}

function LeaveConfirm({ flowKey, name }: { flowKey: string; name: string }) {
  const [done, setDone] = useState<WaiterOut | null>(null);

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/members/public/leave-waitinglist/{key}", {
          params: { path: { key: flowKey } },
        }),
      ),
    { onSuccess: (data: WaiterOut) => setDone(data) },
  );

  if (done) {
    return (
      <FlowResult tone="success">
        {done.name}, du wurdest von der Warteliste entfernt. Schade, dass es nicht geklappt hat!
      </FlowResult>
    );
  }

  return (
    <div className="stack">
      <p className="muted">
        Möchtest du <strong>{name}</strong> wirklich von der Warteliste entfernen? Diese Aktion kann
        nicht rückgängig gemacht werden.
      </p>
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button variant="danger" onClick={() => mutation.mutate(undefined)} busy={mutation.isPending}>
          Warteliste verlassen
        </Button>
      </div>
    </div>
  );
}
