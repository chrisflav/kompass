import { Fragment, type ReactNode } from "react";

import { Button, decimal, euro, Field, MultiSelect, Select } from "../../components/ui";
import type { components } from "../../api/schema";

type InputDeclarationOut = components["schemas"]["InputDeclarationOut"];
type InputFieldOut = components["schemas"]["InputFieldOut"];
type InputOptionOut = components["schemas"]["InputOptionOut"];
type InputChoiceOut = components["schemas"]["InputChoiceOut"];
type StatementFormOut = components["schemas"]["StatementFormOut"];
type FormStepOut = components["schemas"]["FormStepOut"];

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
// All nine types get the control they want. `choice` was the exception — it
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
//
// A **rows** declaration is the one entry that is a shape rather than a widget:
// the question asked once per row over the cells `fields` declares. It is here
// because one statement settles a trip several people travelled differently,
// and whether somebody gets the rate per kilometre at all depends on *their*
// mode of travel — so the mode and the distance belong together, per
// traveller, in a row. `RowsField` lays the table out and every cell goes
// through the same `control` a question of that type would have.
//
// And **one rendering for the person answering and the person signing.** The
// signer used to read the answers through a layout of their own — a list of
// terms appended under the approval record — while the submitter answered them
// in groups, fields and tables. The same content in two shapes is two things
// to keep in step with the rules, and it asks the signer to recognise a
// statement they have never seen laid out that way. So the form is rendered
// once, by `AnswerSteps`, and `readOnly` is the whole of the difference: every
// group, label, hint, derived reading and table column is where the submitter
// had it, and each control is replaced by what was answered in it.

/** The answers a statement carries, as `GET …/form` hands them over. */
export type Answers = Record<string, unknown>;

/**
 * Types whose control is typed into, so a keystroke must not be a request.
 *
 * `rows` is in here because a table *contains* typed-into cells. This set is
 * keyed by the declaration's own type, so a table left out of it would make
 * every keystroke in every cell a request — and a table goes back whole, so
 * that is the entire table once per character. The price is that adding or
 * removing a row waits for the same pause, which nobody sees: the row appears
 * at once and only the save is deferred.
 */
export const TYPED_INTO = new Set(["money", "decimal", "int", "text", "rows"]);

/** Each number type's resolution, as the `step` of its input. */
const NUMBER_STEP: Record<string, string> = { money: "0.01", decimal: "any", int: "1" };

/**
 * What rendering one answer needs to know — which a question and a cell of a
 * table both are.
 *
 * A cell is a question asked once per row, so a `Field` carries the same
 * `type`, `max` and `choices` an `Input` does. The one difference is where the
 * people come from: a party-valued cell has **no `options` of its own**,
 * because one column served two different domains in two rows is not a thing a
 * form can explain. They are the *declaration's* options, stated once for the
 * whole table, and `cellOf` is where that is filled in.
 */
type Asked = {
  label: string;
  type: string;
  max?: number | null;
  options: InputOptionOut[];
  choices: InputChoiceOut[];
};

/** One cell of `declaration`, as a question in its own right. */
function cellOf(declaration: InputDeclarationOut, field: InputFieldOut): Asked {
  return { ...field, options: declaration.options };
}

/** One row of a table's answer: a mapping over the declaration's field keys. */
type Row = Record<string, unknown>;

/**
 * A table's answer, as rows.
 *
 * `[]`, an absent key and a table the rules have stopped offering all read the
 * same — an unanswered question — because nothing distinguishes them and
 * inventing a difference would need a state nothing stores. So an empty table
 * is never an error here either: whether one is *needed* is the ruleset's own
 * `Check`, which the last leg of the flow prints.
 */
function rowsOf(value: unknown): Row[] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => (row !== null && typeof row === "object" ? (row as Row) : {}));
}

/** Where a refusal about the row at `index` is keyed — zero-based, as sent. */
function rowPath(key: string, index: number): string {
  return `${key}[${index}]`;
}

/** Where a refusal about one cell of that row is keyed. */
function cellPath(key: string, index: number, field: string): string {
  return `${rowPath(key, index)}.${field}`;
}

function ids(value: unknown): number[] {
  return Array.isArray(value) ? value.map(Number) : [];
}

function options(asked: Asked) {
  return asked.options.map((option) => ({ value: option.id, label: option.name }));
}

function choices(asked: Asked) {
  return asked.choices.map((choice) => ({ value: choice.value, label: choice.label }));
}

/** No answer yet, in any of the three shapes the API expresses one in. */
function blank(value: unknown): boolean {
  return value === null || value === undefined || value === "";
}

/** The name the rules offered for `id`, or that they no longer offer it. */
function memberName(asked: Asked, id: number): string {
  return asked.options.find((option) => option.id === id)?.name ?? "unbekannt";
}

/**
 * One answer as a reading rather than as a control.
 *
 * One path for a derived answer and a stored one, because `GET …/form` hands a
 * derived value over in the shape `Statement.inputs` holds it: money as text, a
 * person as an id, a set of people as a list of ids. There is nothing to tell
 * apart here, which is the point — a figure the engine supplied reads like a
 * figure somebody answered.
 *
 * Asked of an `Asked` and not of a declaration, so one reading serves a
 * question and a cell of a table alike. A table has no reading of its own: it
 * is never `derived`, and what it is made of is read cell by cell.
 */
export function answerText(asked: Asked, value: unknown): string {
  if (asked.type === "member_set") {
    const named = ids(value).map((id) => memberName(asked, id));
    return named.length > 0 ? named.join(", ") : "—";
  }
  if (asked.type === "member") {
    return blank(value) ? "—" : memberName(asked, Number(value));
  }
  if (asked.type === "bool") {
    return value ? "Ja" : "Nein";
  }
  if (asked.type === "money") {
    return euro(Number(value));
  }
  if (asked.type === "decimal") {
    // A quantity, not an amount: „0,5“ days, never „0,50 €“.
    return blank(value) ? "—" : decimal(String(value));
  }
  if (asked.type === "choice") {
    const chosen = asked.choices.find((choice) => choice.value === String(value ?? ""));
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

/**
 * One question, as the control its declaration asks for.
 *
 * `errors` is the whole map the `422` carries rather than this question's own
 * messages, because a table's refusals are keyed by a *path* into it —
 * `"reisen"`, `"reisen[1]"`, `"reisen[1].kilometers"` — and a cell error
 * belongs against the cell that caused it. For every other type the map holds
 * one key and the lookup is the one it always was.
 */
export function AnswerField({
  declaration,
  value,
  onChange,
  errors,
  readOnly = false,
}: {
  declaration: InputDeclarationOut;
  value: unknown;
  /** The answer in the shape `inputs` stores it: a string, a number, ids, a flag. */
  onChange: (next: unknown) => void;
  /** The `422`'s own map, keyed by path. */
  errors?: Record<string, string[]>;
  /** Show what was answered where the control would be, and change nothing. */
  readOnly?: boolean;
}) {
  if (declaration.type === "rows") {
    return (
      <RowsField
        declaration={declaration}
        value={value}
        onChange={onChange}
        errors={errors ?? {}}
        readOnly={readOnly}
      />
    );
  }
  if (readOnly) {
    return (
      <ReadOnlyField label={declaration.label} hint={declaration.help || undefined}>
        {answerText(declaration, value)}
      </ReadOnlyField>
    );
  }
  const own = errors?.[declaration.key];
  return (
    <Field label={declaration.label} hint={declaration.help || undefined}>
      {control(declaration, value, onChange)}
      {own && <div className="field-error">{own.join(" ")}</div>}
    </Field>
  );
}

/**
 * `Field`, with the answer where its control would be.
 *
 * The same frame and the same three parts in the same order — label, value,
 * hint — so a question reads in the place and the voice the person answering
 * it saw. Not a `<label>`, which is what `Field` is: there is no control here
 * for it to name.
 */
function ReadOnlyField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="field field-readonly">
      <span className="field-label">{label}</span>
      <span className="field-value">{children}</span>
      {hint && <span className="field-hint">{hint}</span>}
    </div>
  );
}

/**
 * A repeating row: one question, several travellers.
 *
 * A grid and not a stack of question groups, because the columns are the same
 * question asked again — the heading says what a cell is once and every row
 * answers it, so five journeys read as five lines rather than as twenty
 * labelled fields.
 *
 * Not a `Field`, which is a `<label>`: one label over a grid of controls would
 * focus the first cell on every click and read the whole table out as one
 * control's name. It keeps the class, so the form's spacing and a refusal's
 * styling are the form's.
 *
 * A **seeded** row — the one the excursion prefilled — is nothing special
 * here, and that is the point: a seed is an answer written once on the
 * person's behalf, not a reading of the trip, so it is editable, removable and
 * splittable like any row somebody typed. `derived` is the other thing and it
 * is rendered as the other thing (`DerivedFacts`); a table is never derived.
 */
function RowsField({
  declaration,
  value,
  onChange,
  errors,
  readOnly,
}: {
  declaration: InputDeclarationOut;
  value: unknown;
  onChange: (next: unknown) => void;
  errors: Record<string, string[]>;
  /** The same grid with every cell read out, and nothing to add or remove. */
  readOnly: boolean;
}) {
  const rows = rowsOf(value);
  // `max` on a table is the number of rows. A cell's own ceiling is on the
  // cell, which is where `control` reads it.
  const limit = declaration.max ?? null;
  const full = limit !== null && rows.length >= limit;
  const own = errors[declaration.key];

  function edit(index: number, field: string, next: unknown) {
    onChange(rows.map((row, i) => (i === index ? { ...row, [field]: next } : row)));
  }

  function add() {
    // An empty object and not a row of blanks: the API fills every cell it
    // asks for with its own type's empty value, and a row that named keys the
    // rules do not ask for is refused as a row. So the one thing a new row has
    // to be is a row.
    onChange([...rows, {}]);
  }

  function remove(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  return (
    <div className="field rows-field">
      <span className="field-label">{declaration.label}</span>
      {declaration.help && <span className="field-hint">{declaration.help}</span>}
      {rows.length === 0 ? (
        // An empty table is an unanswered question and never an error, so this
        // says what to do rather than what is missing — and to a reader, who
        // has nothing to do, only that there is none.
        <p className="rows-empty">
          {readOnly ? "Keine Zeile." : "Noch keine Zeile — unten die erste anlegen."}
        </p>
      ) : (
        <div className="table-wrap rows-wrap">
          <table className="rows-table">
            <thead>
              <tr>
                <th scope="col" className="rows-num">
                  Nr.
                </th>
                {declaration.fields.map((field) => (
                  <th scope="col" key={field.key}>
                    {field.label}
                    {field.help && <span className="rows-th-help">{field.help}</span>}
                  </th>
                ))}
                {!readOnly && <th scope="col" className="rows-drop" />}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const rowErrors = errors[rowPath(declaration.key, index)];
                return (
                  // Keyed by index because the index *is* a row's identity: the
                  // answer is an array, the API's error paths index back into
                  // it, and nothing in a row names it. Every cell is
                  // controlled from `rows[index]`, so a removal renders the
                  // rows that are left rather than shifting values about.
                  <Fragment key={index}>
                    <tr>
                      <td className="rows-num">{index + 1}</td>
                      {declaration.fields.map((field) => {
                        const cell = cellOf(declaration, field);
                        const problem = errors[cellPath(declaration.key, index, field.key)];
                        return (
                          <td
                            key={field.key}
                            data-label={field.label}
                            className={problem ? "rows-cell has-error" : "rows-cell"}
                          >
                            {readOnly
                              ? answerText(cell, row[field.key])
                              : control(
                                  cell,
                                  row[field.key],
                                  (next) => edit(index, field.key, next),
                                  `${field.label}, Zeile ${index + 1}`,
                                )}
                            {problem && <div className="field-error">{problem.join(" ")}</div>}
                          </td>
                        );
                      })}
                      {!readOnly && (
                      <td className="rows-drop">
                        <button
                          type="button"
                          className="rows-remove"
                          aria-label={`Zeile ${index + 1} entfernen`}
                          onClick={() => remove(index)}
                        >
                          ×
                        </button>
                      </td>
                      )}
                    </tr>
                    {rowErrors && (
                      <tr className="rows-row-error">
                        <td colSpan={declaration.fields.length + (readOnly ? 1 : 2)}>
                          <div className="field-error">{rowErrors.join(" ")}</div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {!readOnly && (
        <div className="rows-actions">
          <Button variant="ghost" onClick={add} disabled={full}>
            + Zeile hinzufügen
          </Button>
          {full && <span className="field-hint">Höchstens {limit} Zeilen.</span>}
        </div>
      )}
      {own && <div className="field-error">{own.join(" ")}</div>}
    </div>
  );
}

/**
 * The control one answer is given in.
 *
 * Asked of an `Asked`, so a cell of a table is rendered by the same code the
 * question of that type is — there is no second rendering of the widget
 * vocabulary to keep in step with this one. `ariaLabel` is how a cell gets a
 * name: its column heading is written once, above the grid.
 */
function control(
  asked: Asked,
  value: unknown,
  onChange: (next: unknown) => void,
  ariaLabel?: string,
) {
  if (asked.type === "member_set") {
    return (
      <MultiSelect
        options={options(asked)}
        selected={ids(value)}
        onChange={(next) => onChange(next)}
        placeholder="Personen auswählen…"
        emptyText="Hier bieten die Regeln niemanden an."
        ariaLabel={ariaLabel}
      />
    );
  }
  if (asked.type === "member") {
    return (
      <Select
        value={blank(value) ? "" : String(value)}
        onChange={(next) => onChange(next ? Number(next) : null)}
        options={options(asked)}
        placeholder="— niemand —"
        allowEmpty
        emptyLabel="— niemand —"
        ariaLabel={ariaLabel}
      />
    );
  }
  if (asked.type === "choice") {
    // `""` is an answer and not the absence of one: a form is filled in
    // gradually, and "not chosen yet" is what the API stores for it. Anything
    // that is neither that nor one of these is refused under this question, so
    // there is nothing else to offer.
    return (
      <Select
        value={blank(value) ? "" : String(value)}
        onChange={(next) => onChange(next)}
        options={choices(asked)}
        placeholder="— nicht gewählt —"
        allowEmpty
        emptyLabel="— nicht gewählt —"
        ariaLabel={ariaLabel}
      />
    );
  }
  if (asked.type === "bool") {
    return (
      <input
        type="checkbox"
        aria-label={ariaLabel}
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (asked.type === "money" || asked.type === "decimal" || asked.type === "int") {
    // The step is the type's resolution: the cent for money, none at all for a
    // decimal — which the API holds to no cent, so the browser must not either
    // — and the unit for a whole number.
    const step = NUMBER_STEP[asked.type];
    return (
      <input
        type="number"
        step={step}
        max={asked.max ?? undefined}
        inputMode={asked.type === "int" ? "numeric" : "decimal"}
        aria-label={ariaLabel}
        value={blank(value) ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      type="text"
      aria-label={ariaLabel}
      value={blank(value) ? "" : String(value)}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

/**
 * Whether `form` is the **opening step** of a longer form rather than all of it.
 *
 * A ruleset may narrow its own form down to the one question that decides what
 * else is worth asking: Ludwigsburg settles under one of two travel-cost
 * policies, and until that is answered a night is neither a receipt nor a
 * Pauschale and a kilometre has no rate — so `relevant_inputs` asks that and
 * nothing else. The backend needs nothing extra to say so and this needs
 * nothing extra to read it: `steps` already partitions the whole form into the
 * groups the rules named, so **one named step is a form that has more groups
 * than it is currently showing**.
 *
 * The label is what carries it. A ruleset that names no steps comes back as a
 * single step labelled `""` (Heidelberg, and every form that was a flat list
 * before there were steps), and that is emphatically *not* an opening step —
 * it is the whole form, and it is laid out exactly as it always was. So the
 * degenerate case needs no branch of its own: it simply never matches.
 *
 * What this is not: a second wizard. It changes the wording and takes away a
 * preview of figures that cannot exist yet. Weiter still goes where it went,
 * because what may be handed in is `/preflight`'s answer and not this
 * client's — the rules already refuse a statement with no Regelwerk, by name.
 */
export function opensWithOneStep(form: StatementFormOut): boolean {
  return form.steps.length === 1 && form.steps[0].label !== "";
}

/**
 * The section's questions, in the groups its rules put them in.
 *
 * The one rendering of the form, for both of the people who read it: the
 * person answering, who gets the controls, and the person signing, who gets
 * `readOnly` and the same groups, labels and tables with the answers in them.
 * See the note at the top of this file for why there are not two.
 */
export function AnswerSteps({
  form,
  answers,
  errors = {},
  onChange = () => {},
  readOnly = false,
}: {
  form: StatementFormOut;
  answers: Answers;
  errors?: Record<string, string[]>;
  onChange?: (declaration: InputDeclarationOut, value: unknown) => void;
  readOnly?: boolean;
}) {
  if (form.inputs.length === 0) {
    return <p className="muted">Für diese Abrechnung fragen die Regeln nichts ab.</p>;
  }
  const opening = opensWithOneStep(form);
  return (
    <>
      {form.steps.map((step) => (
        <AnswerGroup
          key={step.label}
          step={step}
          opening={opening}
          form={form}
          answers={answers}
          errors={errors}
          onChange={onChange}
          readOnly={readOnly}
        />
      ))}
    </>
  );
}

/**
 * One group of questions, as the ruleset grouped them.
 *
 * `steps` always partitions the whole form, so this is the only way the form is
 * laid out — including the degenerate case, a ruleset that named no steps,
 * which comes back as a single group with an empty label and reads as the flat
 * list it was before there were steps.
 *
 * Sections and not pages, deliberately. This form is already one leg of a
 * wizard (`EtappenRail`), and a second wizard inside it would make "Weiter"
 * mean two different things on one screen — and hide questions behind a step
 * the person cannot see they still have to answer. The backend is of the same
 * mind: `steps` carries a label and its keys and nothing else, no page state
 * and no notion of a step being finished.
 *
 * The readings come first within a group: what the trip says, then what it
 * leaves to be answered.
 *
 * `opening` says this group is the form's first step and the rest is waiting on
 * it (`opensWithOneStep`). It is still a section and still not a page — what it
 * adds is a frame and one sentence, because a form showing a single question
 * with nothing under it reads as a page that failed to load rather than as a
 * question that decides the others.
 */
function AnswerGroup({
  step,
  opening,
  form,
  answers,
  errors,
  onChange,
  readOnly,
}: {
  step: FormStepOut;
  opening: boolean;
  form: StatementFormOut;
  answers: Answers;
  errors: Record<string, string[]>;
  onChange: (declaration: InputDeclarationOut, value: unknown) => void;
  readOnly: boolean;
}) {
  const declared = step.keys
    .map((key) => form.inputs.find((declaration) => declaration.key === key))
    .filter((declaration): declaration is InputDeclarationOut => declaration !== undefined);
  const derived = declared.filter((declaration) => declaration.derived);
  const asked = declared.filter((declaration) => !declaration.derived);
  return (
    <section className={opening ? "answer-group answer-opening" : "answer-group"}>
      {step.label && <h3 className="answer-group-title">{step.label}</h3>}
      {derived.length > 0 && (
        // Read from `form.answers` rather than from the draft: a derived figure
        // is resolved again on every request and nothing stores it, so the form
        // as served is the only place it is current.
        <DerivedFacts declarations={derived} answers={form.answers} />
      )}
      {asked.map((declaration) => (
        <AnswerField
          key={declaration.key}
          declaration={declaration}
          value={answers[declaration.key]}
          // The whole map, not this key's messages: a table's refusals are
          // keyed by a path into it (`"reisen[1].kilometers"`), so where a
          // message lands is the renderer's business and not the form's.
          errors={errors}
          onChange={(value) => onChange(declaration, value)}
          readOnly={readOnly}
        />
      ))}
      {opening && !readOnly && (
        <p className="answer-opening-note">
          Die weiteren Fragen erscheinen, sobald dieser Schritt beantwortet ist.
        </p>
      )}
    </section>
  );
}
