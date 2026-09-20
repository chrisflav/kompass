import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation } from "../../../api/hooks";
import {
  defaultChoice,
  usePublicTerminEnums,
  type TerminChoice,
  type TerminEnums,
} from "../../../api/terminEnums";
import { Button, Field, QueryBoundary, Select as UiSelect } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell } from "./shared";

type TerminSubmit = components["schemas"]["TerminSubmit"];

/** A blank submission whose choice fields start on the defaults the API reports. */
function initialTermin(enums: TerminEnums): TerminSubmit {
  return {
    title: "",
    subtitle: "",
    start_date: "",
    end_date: "",
    group: defaultChoice(enums, "group"),
    category: defaultChoice(enums, "category"),
    condition: defaultChoice(enums, "condition"),
    technik: defaultChoice(enums, "technik"),
    saison: defaultChoice(enums, "saison"),
    eventart: defaultChoice(enums, "eventart"),
    klassifizierung: defaultChoice(enums, "klassifizierung"),
    anforderung_hoehe: 0,
    anforderung_strecke: 0,
    anforderung_dauer: 0,
    max_participants: 10,
    description: "",
    equipment: "",
    voraussetzungen: "",
    responsible: "",
    phone: "",
    email: "",
  };
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: TerminChoice[];
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      <UiSelect value={value} onChange={onChange} options={options} />
    </Field>
  );
}

/**
 * Public event proposal (``POST /api/ludwigsburgalpin/public/termine``). The
 * choice lists come from the unauthenticated ``/public/enums`` mirror, so the
 * form waits for them rather than opening selects with nothing in them.
 */
export function SubmitTerminFlow() {
  const enumsQuery = usePublicTerminEnums();
  return (
    <FlowShell title="Termin einreichen">
      <QueryBoundary query={enumsQuery}>
        {(enums: TerminEnums) => <SubmitTerminForm enums={enums} />}
      </QueryBoundary>
    </FlowShell>
  );
}

function SubmitTerminForm({ enums }: { enums: TerminEnums }) {
  const [form, setForm] = useState<TerminSubmit>(() => initialTermin(enums));
  const [done, setDone] = useState(false);

  const mutation = useApiMutation(
    () => unwrap(client.POST("/api/ludwigsburgalpin/public/termine", { body: form })),
    { onSuccess: () => setDone(true) },
  );

  const set = (patch: Partial<TerminSubmit>) => setForm({ ...form, ...patch });

  if (done) {
    return (
      <FlowResult tone="success">
        Vielen Dank! Dein Terminvorschlag wurde eingereicht und wird geprüft.
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
      <Field label="Titel">
        <input value={form.title} onChange={(e) => set({ title: e.target.value })} />
      </Field>
      <Field label="Untertitel">
        <input value={form.subtitle} onChange={(e) => set({ subtitle: e.target.value })} />
      </Field>
      <Field label="Von">
        <input type="date" value={form.start_date} onChange={(e) => set({ start_date: e.target.value })} />
      </Field>
      <Field label="Bis">
        <input type="date" value={form.end_date} onChange={(e) => set({ end_date: e.target.value })} />
      </Field>
      <Select label="Gruppe" value={form.group} options={enums.group ?? []} onChange={(group) => set({ group })} />
      <Select label="Kategorie" value={form.category} options={enums.category ?? []} onChange={(category) => set({ category })} />
      <Select label="Kondition" value={form.condition} options={enums.condition ?? []} onChange={(condition) => set({ condition })} />
      <Select label="Technik" value={form.technik} options={enums.technik ?? []} onChange={(technik) => set({ technik })} />
      <Select label="Saison" value={form.saison} options={enums.saison ?? []} onChange={(saison) => set({ saison })} />
      <Select label="Eventart" value={form.eventart} options={enums.eventart ?? []} onChange={(eventart) => set({ eventart })} />
      <Select
        label="Klassifizierung"
        value={form.klassifizierung}
        options={enums.klassifizierung ?? []}
        onChange={(klassifizierung) => set({ klassifizierung })}
      />
      <Field label="Höhenmeter">
        <input
          type="number"
          value={form.anforderung_hoehe}
          onChange={(e) => set({ anforderung_hoehe: Number(e.target.value) })}
        />
      </Field>
      <Field label="Strecke (km)">
        <input
          type="number"
          value={form.anforderung_strecke}
          onChange={(e) => set({ anforderung_strecke: Number(e.target.value) })}
        />
      </Field>
      <Field label="Dauer (h)">
        <input
          type="number"
          value={form.anforderung_dauer}
          onChange={(e) => set({ anforderung_dauer: Number(e.target.value) })}
        />
      </Field>
      <Field label="Max. Teilnehmende">
        <input
          type="number"
          value={form.max_participants}
          onChange={(e) => set({ max_participants: Number(e.target.value) })}
        />
      </Field>
      <Field label="Beschreibung">
        <textarea value={form.description} onChange={(e) => set({ description: e.target.value })} rows={4} />
      </Field>
      <Field label="Ausrüstung">
        <textarea value={form.equipment} onChange={(e) => set({ equipment: e.target.value })} rows={2} />
      </Field>
      <Field label="Voraussetzungen">
        <textarea value={form.voraussetzungen} onChange={(e) => set({ voraussetzungen: e.target.value })} rows={2} />
      </Field>
      <Field label="Organisator:in">
        <input value={form.responsible} onChange={(e) => set({ responsible: e.target.value })} />
      </Field>
      <Field label="Telefon">
        <input value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
      </Field>
      <Field label="E-Mail">
        <input type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
      </Field>
      {mutation.error && <FlowResult tone="error">{mutation.error.message}</FlowResult>}
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          Termin einreichen
        </Button>
      </div>
    </form>
  );
}
