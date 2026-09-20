import { useState } from "react";

import { defaultChoice, type TerminChoice, type TerminEnums } from "../../api/terminEnums";
import { Button, Field, Select as UiSelect } from "../../components/ui";

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

/** A blank draft whose choice fields start on the defaults the API reports. */
export function emptyTermin(enums: TerminEnums): TerminFormValues {
  return {
    title: "",
    subtitle: "",
    start_date: "",
    end_date: "",
    group: defaultChoice(enums, "group"),
    responsible: "",
    phone: "",
    email: "",
    category: defaultChoice(enums, "category"),
    condition: defaultChoice(enums, "condition"),
    technik: defaultChoice(enums, "technik"),
    saison: defaultChoice(enums, "saison"),
    eventart: defaultChoice(enums, "eventart"),
    klassifizierung: defaultChoice(enums, "klassifizierung"),
    equipment: "",
    voraussetzungen: "",
    description: "",
    max_participants: 10,
    anforderung_hoehe: 0,
    anforderung_strecke: 0,
    anforderung_dauer: 0,
  };
}

export function Select({
  value,
  options,
  onChange,
}: {
  value: string;
  options: TerminChoice[];
  onChange: (v: string) => void;
}) {
  return <UiSelect value={value} onChange={onChange} options={options} />;
}

export function TerminForm({
  initial,
  enums,
  submitLabel,
  busy,
  onSubmit,
  onCancel,
  errors = {},
}: {
  initial: TerminFormValues;
  enums: TerminEnums;
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
        <Select value={form.group} options={enums.group ?? []} onChange={(v) => set("group", v)} />
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
        <Select
          value={form.category}
          options={enums.category ?? []}
          onChange={(v) => set("category", v)}
        />
        {fieldError("category")}
      </Field>
      <Field label="Kondition">
        <Select
          value={form.condition}
          options={enums.condition ?? []}
          onChange={(v) => set("condition", v)}
        />
        {fieldError("condition")}
      </Field>
      <Field label="Technik">
        <Select
          value={form.technik}
          options={enums.technik ?? []}
          onChange={(v) => set("technik", v)}
        />
        {fieldError("technik")}
      </Field>
      <Field label="Saison">
        <Select
          value={form.saison}
          options={enums.saison ?? []}
          onChange={(v) => set("saison", v)}
        />
        {fieldError("saison")}
      </Field>
      <Field label="Eventart">
        <Select
          value={form.eventart}
          options={enums.eventart ?? []}
          onChange={(v) => set("eventart", v)}
        />
        {fieldError("eventart")}
      </Field>
      <Field label="Klassifizierung">
        <Select
          value={form.klassifizierung}
          options={enums.klassifizierung ?? []}
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
