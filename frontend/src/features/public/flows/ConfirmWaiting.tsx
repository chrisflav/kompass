import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation } from "../../../api/hooks";
import { Button } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, useFlowKey } from "./shared";

type ConfirmWaitingOut = components["schemas"]["ConfirmWaitingOut"];

/** Confirm intent to keep waiting (``/api/members/public/confirm-waiting/{key}``). */
export function ConfirmWaitingFlow() {
  const key = useFlowKey();
  const [done, setDone] = useState<ConfirmWaitingOut | null>(null);

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/members/public/confirm-waiting/{key}", {
          params: { path: { key } },
        }),
      ),
    { onSuccess: (data: ConfirmWaitingOut) => setDone(data) },
  );

  return (
    <FlowShell title="Warteliste bestätigen">
      {!key ? (
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      ) : done ? (
        <FlowResult tone="success">
          {done.already_confirmed
            ? `Danke, ${done.prename}! Deine Wartelisten-Bestätigung lag bereits vor.`
            : `Danke, ${done.prename}! Du stehst weiterhin auf der Warteliste.`}
        </FlowResult>
      ) : (
        <div className="stack">
          <p className="muted">
            Bitte bestätige, dass du weiterhin auf der Warteliste bleiben möchtest.
          </p>
          {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
          <div className="row-actions">
            <Button onClick={() => mutation.mutate(undefined)} busy={mutation.isPending}>
              Warteliste bestätigen
            </Button>
          </div>
        </div>
      )}
    </FlowShell>
  );
}
