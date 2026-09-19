import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation } from "../../../api/hooks";
import { Button, Field } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell, GenderSelect } from "./shared";

type WaitingListRegisterIn = components["schemas"]["WaitingListRegisterIn"];
type WaitingListRegisterOut = components["schemas"]["WaitingListRegisterOut"];

export function WaitingListFlow() {
  const [form, setForm] = useState<WaitingListRegisterIn>({
    prename: "",
    lastname: "",
    gender: 0,
    email: "",
    birth_date: "",
    application_text: "",
  });
  const [done, setDone] = useState<WaitingListRegisterOut | null>(null);

  const mutation = useApiMutation(
    () => unwrap(client.POST("/api/members/public/waiting-list", { body: form })),
    { onSuccess: (data: WaitingListRegisterOut) => setDone(data) },
  );

  const set = (patch: Partial<WaitingListRegisterIn>) => setForm({ ...form, ...patch });

  return (
    <FlowShell title="Auf die Warteliste">
      {done ? (
        <FlowResult tone="success">
          Danke, {done.name}! Wir haben dir eine E-Mail geschickt. Bitte bestätige darin deine
          Adresse, damit wir dich auf die Warteliste aufnehmen können.
        </FlowResult>
      ) : (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            mutation.mutate(undefined);
          }}
        >
          <p className="muted">
            Trage dich in die Warteliste ein. Sobald ein Platz frei wird, melden wir uns bei dir.
          </p>
          <Field label="Vorname">
            <input value={form.prename} onChange={(e) => set({ prename: e.target.value })} />
          </Field>
          <Field label="Nachname">
            <input value={form.lastname} onChange={(e) => set({ lastname: e.target.value })} />
          </Field>
          <GenderSelect value={form.gender} onChange={(gender) => set({ gender })} />
          <Field label="E-Mail">
            <input type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
          </Field>
          <Field label="Geburtsdatum">
            <input
              type="date"
              value={form.birth_date}
              onChange={(e) => set({ birth_date: e.target.value })}
            />
          </Field>
          <Field label="Nachricht an uns (optional)">
            <textarea
              value={form.application_text}
              onChange={(e) => set({ application_text: e.target.value })}
              rows={4}
            />
          </Field>
          {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
          <div className="row-actions">
            <Button type="submit" busy={mutation.isPending}>
              Eintragen
            </Button>
          </div>
        </form>
      )}
    </FlowShell>
  );
}
