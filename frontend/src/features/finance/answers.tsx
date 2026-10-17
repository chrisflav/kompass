import { Field, MultiSelect, Select } from "../../components/ui";
import type { components } from "../../api/schema";

type InputDeclarationOut = components["schemas"]["InputDeclarationOut"];

// The widget vocabulary, as a renderer.
//
// The reimbursement step used to hardcode four fields — a number for the price
// per night and three member pickers — because `Statement` had four columns
// with those names. The section's rules declare what to ask
// (`Ruleset.inputs`), `GET /api/finance/statements/{id}/form` serves the
// declarations with the people a party-valued answer may name already
// resolved, and this renders whatever comes back: a section whose rules ask
// something else gets asked it without a line changing here.
//
// Six of the seven types get the control they want. `choice` gets a free-text
// input, because `Input.options` carries `Member`s and there is no way for a
// declaration to name a list of non-member choices — taxis #573. Rendering a
// `<select>` with nothing to put in it would be worse.

/** The answers a statement carries, as `GET …/form` hands them over. */
export type Answers = Record<string, unknown>;

/** Types whose control is typed into, so a keystroke must not be a request. */
export const TYPED_INTO = new Set(["money", "int", "text", "choice"]);

function ids(value: unknown): number[] {
  return Array.isArray(value) ? value.map(Number) : [];
}

function options(declaration: InputDeclarationOut) {
  return declaration.options.map((option) => ({ value: option.id, label: option.name }));
}

/** One question, as the control its declaration asks for. */
export function AnswerField({
  declaration,
  value,
  onChange,
  errors,
}: {
  declaration: InputDeclarationOut;
  value: unknown;
  /** The answer in the shape `inputs` stores it: a string, a number, ids, a flag. */
  onChange: (next: unknown) => void;
  errors?: string[];
}) {
  return (
    <Field label={declaration.label} hint={declaration.help || undefined}>
      {control(declaration, value, onChange)}
      {errors && <div className="field-error">{errors.join(" ")}</div>}
    </Field>
  );
}

function control(
  declaration: InputDeclarationOut,
  value: unknown,
  onChange: (next: unknown) => void,
) {
  if (declaration.type === "member_set") {
    return (
      <MultiSelect
        options={options(declaration)}
        selected={ids(value)}
        onChange={(next) => onChange(next)}
        placeholder="Personen auswählen…"
        emptyText="Hier bieten die Regeln niemanden an."
      />
    );
  }
  if (declaration.type === "member") {
    return (
      <Select
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(next) => onChange(next ? Number(next) : null)}
        options={options(declaration)}
        placeholder="— niemand —"
        allowEmpty
        emptyLabel="— niemand —"
      />
    );
  }
  if (declaration.type === "bool") {
    return (
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (declaration.type === "money" || declaration.type === "int") {
    return (
      <input
        type="number"
        step={declaration.type === "money" ? "0.01" : "1"}
        max={declaration.max ?? undefined}
        inputMode={declaration.type === "money" ? "decimal" : "numeric"}
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      type="text"
      value={value === null || value === undefined ? "" : String(value)}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
