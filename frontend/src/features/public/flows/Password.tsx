import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, Field, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, useFlowKey } from "./shared";

type RegisterInfo = components["schemas"]["RegisterInfo"];
type RegisterIn = components["schemas"]["RegisterIn"];
type RegisterResult = components["schemas"]["RegisterResult"];

/** Set / reset the Kompass login password (``/api/logindata/register``). */
export function PasswordFlow() {
  const key = useFlowKey();
  const query = useApiQuery(
    ["public", "register-key", key],
    () => unwrap(client.GET("/api/logindata/register", { params: { query: { key } } })),
    { enabled: key !== "", retry: false },
  );

  if (!key) {
    return (
      <FlowShell title="Passwort setzen">
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      </FlowShell>
    );
  }

  return (
    <FlowShell title="Passwort setzen">
      <QueryBoundary query={query}>
        {(info: RegisterInfo) => <PasswordForm flowKey={key} info={info} />}
      </QueryBoundary>
    </FlowShell>
  );
}

function PasswordForm({ flowKey, info }: { flowKey: string; info: RegisterInfo }) {
  const [registrationPassword, setRegistrationPassword] = useState("");
  const [username, setUsername] = useState(info.suggested_username);
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const [done, setDone] = useState<RegisterResult | null>(null);

  const mutation = useApiMutation(
    () => {
      const body: RegisterIn = {
        key: flowKey,
        registration_password: registrationPassword,
        new_password1: pw1,
        new_password2: pw2,
        username: info.is_reset_mode ? null : username,
      };
      return unwrap(client.POST("/api/logindata/register", { body }));
    },
    { onSuccess: (data: RegisterResult) => setDone(data) },
  );

  if (done) {
    return (
      <FlowResult tone="success">
        {done.is_reset_mode
          ? "Dein Passwort wurde geändert. Du kannst dich jetzt anmelden."
          : "Dein Konto wurde erstellt. Du kannst dich jetzt anmelden."}
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
        Hallo {info.name}, {info.is_reset_mode ? "setze hier ein neues Passwort." : "richte hier deinen Zugang ein."}
      </p>
      <Field label="Anmeldepasswort" hint="Das gemeinsame Passwort aus deiner Einladung.">
        <input
          type="password"
          value={registrationPassword}
          onChange={(e) => setRegistrationPassword(e.target.value)}
        />
      </Field>
      {!info.is_reset_mode && (
        <Field label="Benutzername">
          <input value={username} onChange={(e) => setUsername(e.target.value)} />
        </Field>
      )}
      <Field label="Neues Passwort">
        <input type="password" value={pw1} onChange={(e) => setPw1(e.target.value)} />
      </Field>
      <Field label="Passwort wiederholen">
        <input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
      </Field>
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          Passwort speichern
        </Button>
      </div>
    </form>
  );
}
