import { useState } from "react";
import { Link } from "react-router-dom";

import { client, unwrap } from "../../../api/http";
import { useApiMutation } from "../../../api/hooks";
import { Button, Field } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { EmergencyContactsEditor, FlowResult, FlowShell, cleanContacts, newEmergencyContact } from "./shared";
import { emptyRegisterMember, RegisterMemberFields } from "./RegisterFields";

type RegisterVerifyOut = components["schemas"]["RegisterVerifyOut"];
type RegisterSubmitIn = components["schemas"]["RegisterSubmitIn"];
type RegistrationSuccessOut = components["schemas"]["RegistrationSuccessOut"];
type RegisterMemberData = components["schemas"]["RegisterMemberFields"];
type EmergencyContactIn = components["schemas"]["EmergencyContactIn"];

/** Password-gated public self-registration (``/api/members/public/register``). */
export function RegisterFlow() {
  const [password, setPassword] = useState("");
  const [group, setGroup] = useState<RegisterVerifyOut["group"] | null>(null);

  const verify = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/members/public/register/verify", { body: { password } }),
      ),
    { onSuccess: (data: RegisterVerifyOut) => setGroup(data.group) },
  );

  return (
    <FlowShell title="Anmeldung">
      {group ? (
        <RegisterForm password={password} groupName={group.name} />
      ) : (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            verify.mutate(undefined);
          }}
        >
          <p className="muted">Bitte gib das Anmeldepasswort deiner Gruppe ein.</p>
          <Field label="Passwort">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
            />
          </Field>
          {verify.error && <FlowResult tone="error">{verify.error.message}</FlowResult>}
          <div className="row-actions">
            <Button type="submit" busy={verify.isPending}>
              Weiter
            </Button>
          </div>
        </form>
      )}
    </FlowShell>
  );
}

function RegisterForm({ password, groupName }: { password: string; groupName: string }) {
  const [member, setMember] = useState<RegisterMemberData>(emptyRegisterMember());
  const [contacts, setContacts] = useState<EmergencyContactIn[]>([newEmergencyContact()]);
  const [done, setDone] = useState<RegistrationSuccessOut | null>(null);

  const mutation = useApiMutation(
    () => {
      const body: RegisterSubmitIn = { ...member, password, emergency_contacts: cleanContacts(contacts) };
      return unwrap(client.POST("/api/members/public/register", { body }));
    },
    { onSuccess: (data: RegistrationSuccessOut) => setDone(data) },
  );

  if (done) {
    return <RegistrationDone name={done.name} uploadKey={done.upload_registration_form_key} />;
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
        Anmeldung für die Gruppe <strong>{groupName}</strong>.
      </p>
      <RegisterMemberFields member={member} onChange={setMember} />
      <EmergencyContactsEditor contacts={contacts} onChange={setContacts} />
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          Anmeldung absenden
        </Button>
      </div>
    </form>
  );
}

export function RegistrationDone({ name, uploadKey }: { name: string; uploadKey: string }) {
  return (
    <>
      <FlowResult tone="success">
        Vielen Dank, {name}! Deine Anmeldung wurde entgegengenommen. Als Nächstes benötigen wir
        deinen unterschriebenen Anmeldebogen.
      </FlowResult>
      <p>
        <Link to={`/anmeldebogen?key=${uploadKey}`}>Anmeldebogen jetzt hochladen</Link>
      </p>
    </>
  );
}
