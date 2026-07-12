import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, Field, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, useFlowKey } from "./shared";

type UploadFormVerifyOut = components["schemas"]["UploadFormVerifyOut"];
type UploadFormSuccessOut = components["schemas"]["UploadFormSuccessOut"];

export function UploadFormFlow() {
  const key = useFlowKey();
  const query = useApiQuery(
    ["public", "upload-registration-form", key],
    () =>
      unwrap(
        client.GET("/api/members/public/upload-registration-form/{key}", {
          params: { path: { key } },
        }),
      ),
    { enabled: key !== "", retry: false },
  );

  if (!key) {
    return (
      <FlowShell title="Anmeldebogen hochladen">
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      </FlowShell>
    );
  }

  return (
    <FlowShell title="Anmeldebogen hochladen">
      <QueryBoundary query={query}>
        {(data: UploadFormVerifyOut) => <UploadForm flowKey={key} info={data} />}
      </QueryBoundary>
    </FlowShell>
  );
}

function UploadForm({ flowKey, info }: { flowKey: string; info: UploadFormVerifyOut }) {
  const [file, setFile] = useState<File | null>(null);
  const [done, setDone] = useState<UploadFormSuccessOut | null>(null);

  const mutation = useApiMutation(
    () => {
      if (!file) throw new Error("Bitte wähle eine Datei aus.");
      const upload = file;
      return unwrap(
        client.POST("/api/members/public/upload-registration-form/{key}", {
          params: { path: { key: flowKey } },
          // Multipart file field; the typed body expects a string (binary), so
          // the File is serialized via an explicit FormData bodySerializer.
          body: { registration_form: upload as unknown as string },
          bodySerializer: () => {
            const fd = new FormData();
            fd.append("registration_form", upload);
            return fd;
          },
        }),
      );
    },
    { onSuccess: (data: UploadFormSuccessOut) => setDone(data) },
  );

  if (done) {
    return (
      <FlowResult tone="success">
        Danke, {done.name}! Dein Anmeldebogen wurde hochgeladen.
      </FlowResult>
    );
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate(undefined);
      }}
    >
      <p className="muted">
        Hallo {info.name}, bitte lade deinen unterschriebenen Anmeldebogen hoch (PDF oder Bild,
        max. 5 MiB).
      </p>
      {info.has_registration_form && (
        <FlowResult tone="success">
          Es liegt bereits ein Anmeldebogen vor. Du kannst ihn hier ersetzen.
        </FlowResult>
      )}
      <Field label="Datei">
        <input
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/gif"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </Field>
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending} disabled={!file}>
          Hochladen
        </Button>
      </div>
    </form>
  );
}
