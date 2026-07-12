import { useState } from "react";

import { client, unwrap } from "../../../api/http";
import { useApiMutation } from "../../../api/hooks";
import { Button, Field, Select as UiSelect } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { FlowResult, FlowShell } from "./shared";

type TerminSubmit = components["schemas"]["TerminSubmit"];

// Choice values mirror ``ludwigsburgalpin.models`` (GRUPPE / KATEGORIE / …).
const GRUPPE: [string, string][] = [
  ["ASG", "Alpinsportgruppe"],
  ["OGB", "Ortsgruppe Bietigheim"],
  ["OGV", "Ortsgruppe Vaihingen"],
  ["JUG", "Jugend"],
  ["FAM", "Familie"],
  ["Ü30", "Ü30"],
  ["MTB", "Mountainbike"],
  ["RA", "RegioAktiv"],
  ["SEK", "Sektion"],
];
const KATEGORIE: [string, string][] = [
  ["WAN", "Wandern"],
  ["BW", "Bergwandern"],
  ["KST", "Klettersteig"],
  ["KL", "Klettern"],
  ["SKI", "Piste, Loipe"],
  ["SCH", "Schneeschuhgehen"],
  ["ST", "Skitour"],
  ["STH", "Skihochtour"],
  ["HT", "Hochtour"],
  ["MTB", "Mountainbike"],
  ["AUS", "Ausbildung"],
  ["SON", "Sonstiges z.B. Treffen"],
];
const KONDITION = ["gering", "mittel", "groß", "sehr groß"];
const TECHNIK = ["leicht", "mittel", "schwer", "sehr schwer"];
const SAISON = ["ganzjährig", "Indoor", "Sommer", "Winter"];
const EVENTART = [
  "Einzeltermin",
  "Mehrtagesevent",
  "Regelmäßiges Event/Training",
  "Tagesevent",
  "Wochenendevent",
];
const KLASSIFIZIERUNG = ["Gemeinschaftstour", "Ausbildung"];

function initialTermin(): TerminSubmit {
  return {
    title: "",
    subtitle: "",
    start_date: "",
    end_date: "",
    group: "ASG",
    category: "SON",
    condition: "mittel",
    technik: "mittel",
    saison: "ganzjährig",
    eventart: "Einzeltermin",
    klassifizierung: "Gemeinschaftstour",
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
  options: (string | [string, string])[];
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      <UiSelect
        value={value}
        onChange={onChange}
        options={options.map((o) => {
          const [v, l] = Array.isArray(o) ? o : [o, o];
          return { value: v, label: l };
        })}
      />
    </Field>
  );
}

/** Public event proposal (``POST /api/ludwigsburgalpin/public/termine``). */
export function SubmitTerminFlow() {
  const [form, setForm] = useState<TerminSubmit>(initialTermin());
  const [done, setDone] = useState(false);

  const mutation = useApiMutation(
    () => unwrap(client.POST("/api/ludwigsburgalpin/public/termine", { body: form })),
    { onSuccess: () => setDone(true) },
  );

  const set = (patch: Partial<TerminSubmit>) => setForm({ ...form, ...patch });

  if (done) {
    return (
      <FlowShell title="Termin einreichen">
        <FlowResult tone="success">
          Vielen Dank! Dein Terminvorschlag wurde eingereicht und wird geprüft.
        </FlowResult>
      </FlowShell>
    );
  }

  return (
    <FlowShell title="Termin einreichen">
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
        <Select label="Gruppe" value={form.group} options={GRUPPE} onChange={(group) => set({ group })} />
        <Select label="Kategorie" value={form.category} options={KATEGORIE} onChange={(category) => set({ category })} />
        <Select label="Kondition" value={form.condition} options={KONDITION} onChange={(condition) => set({ condition })} />
        <Select label="Technik" value={form.technik} options={TECHNIK} onChange={(technik) => set({ technik })} />
        <Select label="Saison" value={form.saison} options={SAISON} onChange={(saison) => set({ saison })} />
        <Select label="Eventart" value={form.eventart} options={EVENTART} onChange={(eventart) => set({ eventart })} />
        <Select
          label="Klassifizierung"
          value={form.klassifizierung}
          options={KLASSIFIZIERUNG}
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
        <Field label="Verantwortliche:r">
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
    </FlowShell>
  );
}
