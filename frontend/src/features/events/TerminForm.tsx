import { useState } from "react";

import { Button, Field, Select as UiSelect } from "../../components/ui";

/* Choice values mirror ludwigsburgalpin.models. The backend runs full_clean and
 * rejects unknown choices with 422, so keeping these in sync avoids invalid
 * submissions while the toast still surfaces any server-side validation error. */
export const GRUPPE: [string, string][] = [
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
export const KATEGORIE: [string, string][] = [
  ["WAN", "Wandern"],
  ["BW", "Bergwandern"],
  ["KST", "Klettersteig"],
  ["KL", "Klettern"],
  ["SKI", "Piste, Loipe"],
  ["SCH", "Schneeschuhgehen"],
  ["ST", "Skitour"],
  ["STH", "Skihochtour"],
  ["HT", "Hochtour"],
  ["MTB", "Montainbike"],
  ["AUS", "Ausbildung"],
  ["SON", "Sonstiges z.B. Treffen"],
];
export const KONDITION: [string, string][] = [
  ["gering", "gering"],
  ["mittel", "mittel"],
  ["groß", "groß"],
  ["sehr groß", "sehr groß"],
];
export const TECHNIK: [string, string][] = [
  ["leicht", "leicht"],
  ["mittel", "mittel"],
  ["schwer", "schwer"],
  ["sehr schwer", "sehr schwer"],
];
export const SAISON: [string, string][] = [
  ["ganzjährig", "ganzjährig"],
  ["Indoor", "Indoor"],
  ["Sommer", "Sommer"],
  ["Winter", "Winter"],
];
export const EVENTART: [string, string][] = [
  ["Einzeltermin", "Einzeltermin"],
  ["Mehrtagesevent", "Mehrtagesevent"],
  ["Regelmäßiges Event/Training", "Regelmäßiges Event/Training"],
  ["Tagesevent", "Tagesevent"],
  ["Wochenendevent", "Wochenendevent"],
];
export const KLASSIFIZIERUNG: [string, string][] = [
  ["Gemeinschaftstour", "Gemeinschaftstour"],
  ["Ausbildung", "Ausbildung"],
];

/** All Termin fields as edit-friendly primitives (numbers kept as numbers). */
export interface TerminFormValues {
  title: string;
  subtitle: string;
  start_date: string;
  end_date: string;
  group: string;
  responsible: string;
  phone: string;
  email: string;
  category: string;
  condition: string;
  technik: string;
  saison: string;
  eventart: string;
  klassifizierung: string;
  equipment: string;
  voraussetzungen: string;
  description: string;
  max_participants: number;
  anforderung_hoehe: number;
  anforderung_strecke: number;
  anforderung_dauer: number;
}

export const emptyTermin: TerminFormValues = {
  title: "",
  subtitle: "",
  start_date: "",
  end_date: "",
  group: "ASG",
  responsible: "",
  phone: "",
  email: "",
  category: "SON",
  condition: "mittel",
  technik: "mittel",
  saison: "ganzjährig",
  eventart: "Einzeltermin",
  klassifizierung: "Gemeinschaftstour",
  equipment: "",
  voraussetzungen: "",
  description: "",
  max_participants: 10,
  anforderung_hoehe: 0,
  anforderung_strecke: 0,
  anforderung_dauer: 0,
};

export function Select({
  value,
  options,
  onChange,
}: {
  value: string;
  options: [string, string][];
  onChange: (v: string) => void;
}) {
  return (
    <UiSelect
      value={value}
      onChange={onChange}
      options={options.map(([v, label]) => ({ value: v, label }))}
    />
  );
}

export function TerminForm({
  initial,
  submitLabel,
  busy,
  onSubmit,
  onCancel,
  errors = {},
}: {
  initial: TerminFormValues;
  submitLabel: string;
  busy: boolean;
  onSubmit: (values: TerminFormValues) => void;
  onCancel: () => void;
  errors?: Record<string, string[]>;
}) {
  const [form, setForm] = useState<TerminFormValues>(initial);
  const set = <K extends keyof TerminFormValues>(key: K, value: TerminFormValues[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const fieldError = (key: string) =>
    errors[key] ? <div className="field-error">{errors[key].join(" ")}</div> : null;

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
    >
      <Field label="Titel">
        <input value={form.title} onChange={(e) => set("title", e.target.value)} required />
        {fieldError("title")}
      </Field>
      <Field label="Untertitel">
        <input value={form.subtitle} onChange={(e) => set("subtitle", e.target.value)} />
        {fieldError("subtitle")}
      </Field>
      <Field label="Von">
        <input
          type="date"
          value={form.start_date}
          onChange={(e) => set("start_date", e.target.value)}
          required
        />
        {fieldError("start_date")}
      </Field>
      <Field label="Bis">
        <input
          type="date"
          value={form.end_date}
          onChange={(e) => set("end_date", e.target.value)}
          required
        />
        {fieldError("end_date")}
      </Field>
      <Field label="Gruppe">
        <Select value={form.group} options={GRUPPE} onChange={(v) => set("group", v)} />
        {fieldError("group")}
      </Field>
      <Field label="Organisator:in">
        <input
          value={form.responsible}
          onChange={(e) => set("responsible", e.target.value)}
          required
        />
        {fieldError("responsible")}
      </Field>
      <Field label="Telefonnummer">
        <input value={form.phone} onChange={(e) => set("phone", e.target.value)} />
        {fieldError("phone")}
      </Field>
      <Field label="E-Mail">
        <input
          type="email"
          value={form.email}
          onChange={(e) => set("email", e.target.value)}
          required
        />
        {fieldError("email")}
      </Field>
      <Field label="Kategorie">
        <Select value={form.category} options={KATEGORIE} onChange={(v) => set("category", v)} />
        {fieldError("category")}
      </Field>
      <Field label="Kondition">
        <Select value={form.condition} options={KONDITION} onChange={(v) => set("condition", v)} />
        {fieldError("condition")}
      </Field>
      <Field label="Technik">
        <Select value={form.technik} options={TECHNIK} onChange={(v) => set("technik", v)} />
        {fieldError("technik")}
      </Field>
      <Field label="Saison">
        <Select value={form.saison} options={SAISON} onChange={(v) => set("saison", v)} />
        {fieldError("saison")}
      </Field>
      <Field label="Eventart">
        <Select value={form.eventart} options={EVENTART} onChange={(v) => set("eventart", v)} />
        {fieldError("eventart")}
      </Field>
      <Field label="Klassifizierung">
        <Select
          value={form.klassifizierung}
          options={KLASSIFIZIERUNG}
          onChange={(v) => set("klassifizierung", v)}
        />
        {fieldError("klassifizierung")}
      </Field>
      <Field label="Ausrüstung">
        <textarea
          value={form.equipment}
          onChange={(e) => set("equipment", e.target.value)}
          rows={2}
        />
        {fieldError("equipment")}
      </Field>
      <Field label="Voraussetzungen">
        <textarea
          value={form.voraussetzungen}
          onChange={(e) => set("voraussetzungen", e.target.value)}
          rows={2}
        />
        {fieldError("voraussetzungen")}
      </Field>
      <Field label="Beschreibung">
        <textarea
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          rows={4}
        />
        {fieldError("description")}
      </Field>
      <Field label="Max. Teilnehmerzahl">
        <input
          type="number"
          value={form.max_participants}
          onChange={(e) => set("max_participants", Number(e.target.value))}
        />
        {fieldError("max_participants")}
      </Field>
      <Field label="Höhenmeter in Meter">
        <input
          type="number"
          value={form.anforderung_hoehe}
          onChange={(e) => set("anforderung_hoehe", Number(e.target.value))}
        />
        {fieldError("anforderung_hoehe")}
      </Field>
      <Field label="Strecke in Kilometer">
        <input
          type="number"
          value={form.anforderung_strecke}
          onChange={(e) => set("anforderung_strecke", Number(e.target.value))}
        />
        {fieldError("anforderung_strecke")}
      </Field>
      <Field label="Etappendauer in Stunden">
        <input
          type="number"
          value={form.anforderung_dauer}
          onChange={(e) => set("anforderung_dauer", Number(e.target.value))}
        />
        {fieldError("anforderung_dauer")}
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={busy}>
          {submitLabel}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Abbrechen
        </Button>
      </div>
    </form>
  );
}
