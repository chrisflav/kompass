import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation } from "../../../api/hooks";
import { Button } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, useFlowKey } from "./shared";

type ConfirmMailOut = components["schemas"]["ConfirmMailOut"];

/** Confirm an email address (``/api/members/public/confirm-mail/{key}``). */
export function ConfirmMailFlow() {
  const key = useFlowKey();
  const [done, setDone] = useState<ConfirmMailOut | null>(null);

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/members/public/confirm-mail/{key}", {
          params: { path: { key } },
        }),
      ),
    { onSuccess: (data: ConfirmMailOut) => setDone(data) },
  );

  return (
    <FlowShell title="E-Mail bestätigen">
      {!key ? (
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      ) : done ? (
        <FlowResult tone="success">
          Danke, {done.name}! Die Adresse {done.email} wurde bestätigt.
        </FlowResult>
      ) : (
        <div className="stack">
          <p className="muted">Bitte bestätige deine E-Mail-Adresse.</p>
          {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
          <div className="row-actions">
            <Button onClick={() => mutation.mutate(undefined)} busy={mutation.isPending}>
              E-Mail bestätigen
            </Button>
          </div>
        </div>
      )}
    </FlowShell>
  );
}
