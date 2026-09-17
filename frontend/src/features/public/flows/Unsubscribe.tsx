import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, useFlowKey } from "./shared";

type UnsubscribeInfo = components["schemas"]["UnsubscribeInfo"];

/** Newsletter unsubscribe (``/api/mailer/public/unsubscribe``). */
export function UnsubscribeFlow() {
  const key = useFlowKey();
  const query = useApiQuery(
    ["public", "unsubscribe", key],
    () =>
      unwrap(
        client.GET("/api/mailer/public/unsubscribe", { params: { query: { key } } }),
      ),
    { enabled: key !== "", retry: false },
  );

  if (!key) {
    return (
      <FlowShell title="Newsletter abbestellen">
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      </FlowShell>
    );
  }

  return (
    <FlowShell title="Newsletter abbestellen">
      <QueryBoundary query={query}>
        {(data: UnsubscribeInfo) => <UnsubscribeStep flowKey={key} info={data} />}
      </QueryBoundary>
    </FlowShell>
  );
}

function UnsubscribeStep({ flowKey, info }: { flowKey: string; info: UnsubscribeInfo }) {
  const [done, setDone] = useState<UnsubscribeInfo | null>(null);

  const mutation = useApiMutation(
    () => unwrap(client.POST("/api/mailer/public/unsubscribe", { body: { key: flowKey } })),
    { onSuccess: (data: UnsubscribeInfo) => setDone(data) },
  );

  if (done) {
    return (
      <FlowResult tone="success">
        {done.name}, die Adresse {done.email} erhält keine Newsletter mehr.
      </FlowResult>
    );
  }

  return (
    <div className="stack">
      <p className="muted">
        Möchtest du <strong>{info.email}</strong> vom Newsletter abmelden?
      </p>
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button variant="danger" onClick={() => mutation.mutate(undefined)} busy={mutation.isPending}>
          Newsletter abbestellen
        </Button>
      </div>
    </div>
  );
}
