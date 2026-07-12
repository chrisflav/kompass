import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import {
  EmergencyContactsEditor,
  FlowResult,
  FlowShell,
  newEmergencyContact,
  useFlowKey,
} from "./shared";
import { RegisterMemberFields } from "./RegisterFields";
import { RegistrationDone } from "./Register";

type InvitedRegisterPrefillOut = components["schemas"]["InvitedRegisterPrefillOut"];
type InvitedRegisterSubmitIn = components["schemas"]["InvitedRegisterSubmitIn"];
type RegistrationSuccessOut = components["schemas"]["RegistrationSuccessOut"];
type RegisterMemberData = components["schemas"]["RegisterMemberData"];
type EmergencyContactIn = components["schemas"]["EmergencyContactIn"];

/** Invited registration keyed by an ``InvitationToGroup.key`` (``anmeldung``). */
export function InvitedRegistrationFlow() {
  const key = useFlowKey();
  const query = useApiQuery(
    ["public", "invited-registration", key],
    () =>
      unwrap(
        client.GET("/api/members/public/invited-registration/{key}", {
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
        {(data: InvitedRegisterPrefillOut) => (
          <InvitedForm flowKey={key} prefill={data} />
        )}
      </QueryBoundary>
    </FlowShell>
  );
}

function InvitedForm({
  flowKey,
  prefill,
}: {
  flowKey: string;
  prefill: InvitedRegisterPrefillOut;
}) {
  const [member, setMember] = useState<RegisterMemberData>(prefill.member);
  const [contacts, setContacts] = useState<EmergencyContactIn[]>([newEmergencyContact()]);
  const [done, setDone] = useState<RegistrationSuccessOut | null>(null);

  const mutation = useApiMutation(
    () => {
      const body: InvitedRegisterSubmitIn = { ...member, emergency_contacts: contacts };
      return unwrap(
        client.POST("/api/members/public/invited-registration/{key}", {
          params: { path: { key: flowKey } },
          body,
        }),
      );
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
        Du wurdest in die Gruppe <strong>{prefill.group.name}</strong> eingeladen. Bitte
        vervollständige deine Anmeldung.
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
