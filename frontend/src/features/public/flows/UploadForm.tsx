import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, DownloadButton, Field, QueryBoundary } from "../../../components/ui";
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
      <ol className="flow-steps">
        <li>
          <strong>Anmeldebogen herunterladen.</strong> Er ist bereits mit deinen Daten
          ausgefüllt.
          <div className="row-actions" style={{ marginTop: ".5rem" }}>
            <DownloadButton
              path={`/api/members/public/registration-form/${flowKey}`}
              filename={`Anmeldebogen_${info.name}.pdf`}
            >
              Anmeldebogen herunterladen (PDF)
            </DownloadButton>
          </div>
        </li>
        <li>
          <strong>Ausfüllen und unterschreiben.</strong> Bitte ergänze die fehlenden Felder und
          lies die allgemeinen Bedingungen. Wenn du noch nicht volljährig bist, lass bitte eine
          erziehungsberechtigte Person unterschreiben.
        </li>
        <li>
          <strong>Wieder hochladen.</strong> Ein Scan oder ein Foto genügt (PDF oder Bild,
          max. 5 MiB).
        </li>
      </ol>
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
