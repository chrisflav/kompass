import { useState } from "react";
import { Link } from "react-router-dom";

import { client, unwrap } from "../../../api/http";
import { useApiMutation, useApiQuery } from "../../../api/hooks";
import { Button, Field, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { EmergencyContactsEditor, FlowResult, FlowShell, GenderSelect, cleanContacts, newEmergencyContact, useFlowKey } from "./shared";

type EchoVerifyOut = components["schemas"]["EchoVerifyOut"];
type EchoPrefillOut = components["schemas"]["EchoPrefillOut"];
type EchoSubmitIn = components["schemas"]["EchoSubmitIn"];
type EchoSuccessOut = components["schemas"]["EchoSuccessOut"];
type EmergencyContactIn = components["schemas"]["EmergencyContactIn"];

export function EchoFlow() {
  const key = useFlowKey();
  const query = useApiQuery(
    ["public", "echo", key],
    () => unwrap(client.GET("/api/members/public/echo/{key}", { params: { path: { key } } })),
    { enabled: key !== "", retry: false },
  );

  if (!key) {
    return (
      <FlowShell title="Daten aktualisieren">
        <FlowResult tone="error">Dieser Link ist ungültig (kein Schlüssel angegeben).</FlowResult>
      </FlowShell>
    );
  }

  return (
    <FlowShell title="Daten aktualisieren">
      <QueryBoundary query={query}>
        {(_verify: EchoVerifyOut) => <EchoPasswordStep flowKey={key} />}
      </QueryBoundary>
    </FlowShell>
  );
}

function EchoPasswordStep({ flowKey }: { flowKey: string }) {
  const [password, setPassword] = useState("");
  const [prefill, setPrefill] = useState<EchoPrefillOut | null>(null);

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/members/public/echo/{key}/prefill", {
          params: { path: { key: flowKey } },
          body: { password },
        }),
      ),
    { onSuccess: (data: EchoPrefillOut) => setPrefill(data) },
  );

  if (prefill) {
    return <EchoEditForm flowKey={flowKey} password={password} prefill={prefill} />;
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate(undefined);
      }}
    >
      <p className="muted">Bitte gib das Passwort aus der E-Mail ein, um deine Daten zu bearbeiten.</p>
      <Field label="Passwort">
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
      </Field>
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          Weiter
        </Button>
      </div>
    </form>
  );
}

function EchoEditForm({
  flowKey,
  password,
  prefill,
}: {
  flowKey: string;
  password: string;
  prefill: EchoPrefillOut;
}) {
  const [member, setMember] = useState(prefill.member);
  const [contacts, setContacts] = useState<EmergencyContactIn[]>(
    prefill.emergency_contacts.length > 0
      ? prefill.emergency_contacts.map((c) => ({
          prename: c.prename,
          lastname: c.lastname,
          phone_number: c.phone_number,
          email: c.email,
        }))
      : [newEmergencyContact()],
  );
  const [done, setDone] = useState<EchoSuccessOut | null>(null);

  const mutation = useApiMutation(
    () => {
      const body: EchoSubmitIn = { ...member, password, emergency_contacts: cleanContacts(contacts) };
      return unwrap(
        client.POST("/api/members/public/echo/{key}", {
          params: { path: { key: flowKey } },
          body,
        }),
      );
    },
    { onSuccess: (data: EchoSuccessOut) => setDone(data) },
  );

  if (done) {
    return (
      <>
        <FlowResult tone="success">
          Vielen Dank, {done.name}! Deine Daten wurden gespeichert.
        </FlowResult>
        {done.needs_registration_form_upload && done.upload_registration_form_key && (
          <p>
            <Link to={`/anmeldebogen?key=${done.upload_registration_form_key}`}>
              Jetzt Anmeldebogen hochladen
            </Link>
          </p>
        )}
      </>
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
      <Field label="Vorname">
        <input value={member.prename} onChange={(e) => setMember({ ...member, prename: e.target.value })} />
      </Field>
      <Field label="Nachname">
        <input value={member.lastname} onChange={(e) => setMember({ ...member, lastname: e.target.value })} />
      </Field>
      <GenderSelect value={member.gender} onChange={(gender) => setMember({ ...member, gender })} />
      <Field label="Straße">
        <input value={member.street} onChange={(e) => setMember({ ...member, street: e.target.value })} />
      </Field>
      <Field label="PLZ">
        <input value={member.plz} onChange={(e) => setMember({ ...member, plz: e.target.value })} />
      </Field>
      <Field label="Ort">
        <input value={member.town} onChange={(e) => setMember({ ...member, town: e.target.value })} />
      </Field>
      <Field label="Adresszusatz">
        <input
          value={member.address_extra}
          onChange={(e) => setMember({ ...member, address_extra: e.target.value })}
        />
      </Field>
      <Field label="Telefon">
        <input
          value={member.phone_number}
          onChange={(e) => setMember({ ...member, phone_number: e.target.value })}
        />
      </Field>
      <Field label="DAV-Ausweisnummer">
        <input
          value={member.dav_badge_no}
          onChange={(e) => setMember({ ...member, dav_badge_no: e.target.value })}
        />
      </Field>
      <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
        <input
          type="checkbox"
          checked={member.photos_may_be_taken}
          onChange={(e) => setMember({ ...member, photos_may_be_taken: e.target.checked })}
        />
        <span className="field-label">Fotos dürfen gemacht werden</span>
      </label>
      <EmergencyContactsEditor contacts={contacts} onChange={setContacts} />
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          Speichern
        </Button>
      </div>
    </form>
  );
}
