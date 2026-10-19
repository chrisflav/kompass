import { euro, Field, MultiSelect, Select } from "../../components/ui";
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
// All seven types get the control they want. `choice` was the exception — it
// got a free-text input, because `Input.options` carried `Member`s and a
// declaration had no way to name a list of non-member alternatives (taxis
// #573) — and it is not any more: a declaration carries its own `choices`, and
// those are what the API now checks an answer against.
//
// A **derived** declaration is not a question at all: it is a reading. The
// engine resolves it from the statement's own data on every request — the
// kilometres off the excursion rather than off a person — so there is nothing
// to type and nothing to send: `PATCH …/{id}` *refuses* a value for the key,
// keyed by that question. `answerText` reads one, and `DerivedFacts` states it
// in the voice the trip's own facts are stated in a leg earlier.

/** The answers a statement carries, as `GET …/form` hands them over. */
export type Answers = Record<string, unknown>;

/** Types whose control is typed into, so a keystroke must not be a request. */
export const TYPED_INTO = new Set(["money", "int", "text"]);

function ids(value: unknown): number[] {
  return Array.isArray(value) ? value.map(Number) : [];
}

function options(declaration: InputDeclarationOut) {
  return declaration.options.map((option) => ({ value: option.id, label: option.name }));
}

function choices(declaration: InputDeclarationOut) {
  return declaration.choices.map((choice) => ({ value: choice.value, label: choice.label }));
}

/** No answer yet, in any of the three shapes the API expresses one in. */
function blank(value: unknown): boolean {
  return value === null || value === undefined || value === "";
}

/** The name the rules offered for `id`, or that they no longer offer it. */
function memberName(declaration: InputDeclarationOut, id: number): string {
  return declaration.options.find((option) => option.id === id)?.name ?? "unbekannt";
}

/**
 * One answer as a reading rather than as a control.
 *
 * One path for a derived answer and a stored one, because `GET …/form` hands a
 * derived value over in the shape `Statement.inputs` holds it: money as text, a
 * person as an id, a set of people as a list of ids. There is nothing to tell
 * apart here, which is the point — a figure the engine supplied reads like a
 * figure somebody answered.
 */
export function answerText(declaration: InputDeclarationOut, value: unknown): string {
  if (declaration.type === "member_set") {
    const named = ids(value).map((id) => memberName(declaration, id));
    return named.length > 0 ? named.join(", ") : "—";
  }
  if (declaration.type === "member") {
    return blank(value) ? "—" : memberName(declaration, Number(value));
  }
  if (declaration.type === "bool") {
    return value ? "Ja" : "Nein";
  }
  if (declaration.type === "money") {
    return euro(Number(value));
  }
  if (declaration.type === "choice") {
    const chosen = declaration.choices.find((choice) => choice.value === String(value ?? ""));
    return chosen?.label ?? "—";
  }
  return blank(value) ? "—" : String(value);
}

/**
 * The questions the engine answers itself, stated as what they are.
 *
 * A `derived` answer is a fact about the statement — the kilometres driven, the
 * nights away — read off its own data every time the form is served. Rendered
 * as a disabled field it would say "you may not fill this in", and as an empty
 * one it would look broken; this says where the figure comes from instead, in
 * the same words the trip's facts are given in on the first leg of the flow. A
 * wrong one is corrected on the trip, which is where it is kept.
 */
export function DerivedFacts({
  declarations,
  answers,
}: {
  declarations: InputDeclarationOut[];
  answers: Answers;
}) {
  return (
    <div className="readout">
      <span className="readout-caption">Aus der Fahrt übernommen</span>
      <dl>
        {declarations.map((declaration) => (
          <div key={declaration.key}>
            <dt>{declaration.label}</dt>
            <dd>{answerText(declaration, answers[declaration.key])}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
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
        value={blank(value) ? "" : String(value)}
        onChange={(next) => onChange(next ? Number(next) : null)}
        options={options(declaration)}
        placeholder="— niemand —"
        allowEmpty
        emptyLabel="— niemand —"
      />
    );
  }
  if (declaration.type === "choice") {
    // `""` is an answer and not the absence of one: a form is filled in
    // gradually, and "not chosen yet" is what the API stores for it. Anything
    // that is neither that nor one of these is refused under this question, so
    // there is nothing else to offer.
    return (
      <Select
        value={blank(value) ? "" : String(value)}
        onChange={(next) => onChange(next)}
        options={choices(declaration)}
        placeholder="— nicht gewählt —"
        allowEmpty
        emptyLabel="— nicht gewählt —"
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
        value={blank(value) ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      type="text"
      value={blank(value) ? "" : String(value)}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
