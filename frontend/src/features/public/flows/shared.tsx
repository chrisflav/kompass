import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useSite } from "../../../api/site";
import { KompassMark } from "../../../components/Contour";
import { Button, Field, Select } from "../../../components/ui";
import type { components } from "../../../api/schema";

type EmergencyContactIn = components["schemas"]["EmergencyContactIn"];

/** Gender codes as defined on ``Member.gender_choices`` (0/1/2). */
export const GENDER_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: "Männlich" },
  { value: 1, label: "Weiblich" },
  { value: 2, label: "Divers" },
];

/** Read the ``key`` query-string parameter shared by every secret-link flow. */
export function useFlowKey(): string {
  const [params] = useSearchParams();
  return params.get("key") ?? "";
}

/**
 * Centered card shell for the standalone (chrome-less) self-service pages. It is
 * intentionally styled with the login card so these task pages look like the
 * rest of the standalone surfaces.
 *
 * These pages sit outside `PublicLayout` and so carry no site navigation — right
 * for a secret link opened from an email, but a dead end for the waiting-list
 * form, which is reachable from the public Gruppen menu. The brand doubles as
 * the way back, so no flow can strand someone who arrived by navigating.
 */
export function FlowShell({ title, children }: { title: string; children: ReactNode }) {
  const site = useSite();
  return (
    <div className="login">
      <Link to="/" className="flow-home" aria-label="Zur Website">
        <KompassMark size={26} />
        <span>{site.display_name}</span>
      </Link>
      <div className="card" style={{ width: "min(620px, 94vw)" }}>
        <h1>{title}</h1>
        {children}
      </div>
      <Link to="/" className="flow-back">
        ← Zurück zur Website
      </Link>
    </div>
  );
}

/** Prominent success / error result message inside a flow shell. */
export function FlowResult({
  tone,
  children,
}: {
  tone: "success" | "error";
  children: ReactNode;
}) {
  return (
    <p className={tone === "error" ? "error state" : "state"} role={tone === "error" ? "alert" : "status"}>
      {children}
    </p>
  );
}

export function GenderSelect({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <Field label="Geschlecht">
      <Select
        value={String(value)}
        onChange={(v) => onChange(Number(v))}
        options={GENDER_OPTIONS}
      />
    </Field>
  );
}

const EMPTY_CONTACT: EmergencyContactIn = {
  prename: "",
  lastname: "",
  phone_number: "",
  email: "",
};

/** True when the user added a contact row but never typed anything into it. */
export function isBlankContact(c: EmergencyContactIn): boolean {
  return !(c.prename.trim() || c.lastname.trim() || c.phone_number.trim() || (c.email ?? "").trim());
}

/**
 * The contacts worth submitting: untouched extra rows are dropped rather than
 * stored as empty records. Always keeps at least the first row so the backend's
 * "at least one emergency contact" rule still reports a missing contact rather
 * than an empty list silently passing.
 */
export function cleanContacts(contacts: EmergencyContactIn[]): EmergencyContactIn[] {
  const filled = contacts.filter((c) => !isBlankContact(c));
  return filled.length ? filled : contacts.slice(0, 1);
}

/**
 * Editor for the ``emergency_contacts`` list required by the registration and
 * echo submissions (the backend enforces at least one, mirroring the formset's
 * ``min_num=1``).
 */
export function EmergencyContactsEditor({
  contacts,
  onChange,
}: {
  contacts: EmergencyContactIn[];
  onChange: (contacts: EmergencyContactIn[]) => void;
}) {
  const update = (index: number, patch: Partial<EmergencyContactIn>) =>
    onChange(contacts.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  const remove = (index: number) => onChange(contacts.filter((_, i) => i !== index));

  return (
    <div className="stack">
      <h3 style={{ margin: 0 }}>Notfallkontakte</h3>
      {contacts.map((contact, index) => (
        <div key={index} className="stack" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
          {/* Only the first contact is mandatory (the admin formset's
              `min_num=1`). Marking every block required would make an added but
              untouched block block submission instead of simply being dropped. */}
          <Field label={index === 0 ? "Vorname *" : "Vorname"}>
            <input
              required={index === 0}
              value={contact.prename}
              onChange={(e) => update(index, { prename: e.target.value })}
            />
          </Field>
          <Field label={index === 0 ? "Nachname *" : "Nachname"}>
            <input
              required={index === 0}
              value={contact.lastname}
              onChange={(e) => update(index, { lastname: e.target.value })}
            />
          </Field>
          <Field label={index === 0 ? "Telefon *" : "Telefon"}>
            <input
              required={index === 0}
              value={contact.phone_number}
              onChange={(e) => update(index, { phone_number: e.target.value })}
            />
          </Field>
          <Field label="E-Mail (optional)">
            <input
              type="email"
              value={contact.email}
              onChange={(e) => update(index, { email: e.target.value })}
            />
          </Field>
          {contacts.length > 1 && (
            <div className="row-actions">
              <Button type="button" variant="ghost" onClick={() => remove(index)}>
                Kontakt entfernen
              </Button>
            </div>
          )}
        </div>
      ))}
      <div className="row-actions">
        <Button type="button" variant="ghost" onClick={() => onChange([...contacts, { ...EMPTY_CONTACT }])}>
          Weiteren Kontakt hinzufügen
        </Button>
      </div>
    </div>
  );
}

export function newEmergencyContact(): EmergencyContactIn {
  return { ...EMPTY_CONTACT };
}
