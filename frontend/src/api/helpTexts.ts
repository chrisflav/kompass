import type { DetailRow } from "../components/ui";

/**
 * Field help texts recovered from the Django admin (model `help_text`), keyed by
 * model slug then field name. Kept in the frontend as static copy rather than
 * fetched — if a model's help_text changes, update it here too. The night cost
 * hint embeds a deployment value captured at recovery time.
 */
const FIELD_HELP: Record<string, Record<string, string>> = {
  member: {
    waitinglist_application_date:
      "Falls sich die Person über die Warteliste angemeldet hat ist dies ihr Bewerbungsdatum.",
  },
  freizeit: {
    postcode: "nur für einen LJP-Antrag relevant",
    destination: "z.B. ein Gipfel",
    approved_extra_youth_leader_count:
      "Die Anzahl der genehmigten Jugendleiter*innen pro Ausfahrt wird grundsätzlich durch die Anzahl der Teilnehmer*innen festgelegt. In besonderen Fällen, zum Beispiel bei einer fachlich herausfordernden Ausfahrt, können zusätzliche Jugendleiter*innen genehmigt werden.",
    kilometers_traveled:
      "Gesamte Fahrtstrecke (Hin- und Rückfahrt). Die Angabe ist relevant für die Berechnung der Zuschüsse durch den Jugendetat.",
    approved:
      "Wähle Ja bei Genehmigung, Nein bei Ablehung und Unbekannt, falls noch keine Entscheidung getroffen wurde.",
  },
  ljpproposal: {
    title:
      "Offizieller Titel des Seminars, dieser weicht in der Regel vom informellen Titel ab. Verwende zum Beispiel Sportkletterkurs statt Kletterfreizeit.",
    category: "Kurstyp. In der Regel Themenorientierte Bildungsmaßnahme.",
    goal: "Offizielles Bildungsziel gemäß LJP Richtlinien.",
    goal_strategy:
      "Wie wolltet ihr das Bildungsziel erreichen? Ist das Ziel so erreicht worden? Wenn nicht, warum nicht? Wenn ja, was hat geholfen, das Ziel zu erreichen?",
    not_bw_reason:
      "Falls die Ausfahrt außerhalb von Baden-Württemberg stattfindet, gib bitte eine Begründung an. Sonst lass dieses Feld frei.",
  },
  activitycategory: {
    ljp_category: "Die offizielle Spielart für LJP Anträge mit dieser Aktivität.",
  },
  statement: {
    allowance_to:
      "Die Jugendleiter*innen an die eine Aufwandsentschädigung ausgezahlt werden soll.",
    subsidy_to:
      "Die Person, die die Übernachtungs- und Fahrtkostenzuschüsse erhalten soll. Dies ist in der Regel die Person, die sie bezahlt hat.",
    ljp_to:
      "Die Person, die die LJP-Zuschüsse für die Teilnehmenden erhalten soll. Nur auswählen, wenn ein LJP-Antrag abgegeben wird.",
    night_cost:
      "Laut Preisliste für eine*n Jugendleiter*in. Angabe wird benötigt für die Berechnung von Zuschüssen aus dem Jugendetat. Maximaler Zuschuss pro Person und Nacht: 11 €",
    settings_snapshot: "Gültige Finanzregeln bei Einreichung bzw. Bestätigung",
  },
  emailaddress: {
    internal_only:
      "Leite nur E-Mails weiter, die von einer der internen Domains verschickt wurden.",
    allowed_senders:
      "Leite nur E-Mails von Mitgliedern dieser Gruppen weiter. Lasse dieses Feld frei, um alle Absender*innen zu erlauben.",
  },
};

/**
 * Admin fieldset descriptions, keyed by model slug then the fieldset's first
 * field (so a detail section names its leading field to fetch its intro text).
 */
const FIELDSET_HELP: Record<string, Record<string, string>> = {
  freizeit: {
    name: "Hier kannst du allgemein Angaben zu deiner Ausfahrt machen. Diese sind teilweise relevant für die Zuschüsse aus dem Jugendetat (Verkehrsmittel, Fahrstrecke in km).",
    approved:
      "Informationen zum Genehmigungszustand der Ausfahrt. Die Felder hier sind nicht sichtbar für Standardbenutzer*innen, nur der Genehmigungszustand wird in der Übersicht alle Ausfahrten angezeigt.",
  },
};

/** Lookup `help(model, field)` for a field's help text. */
export function useHelpTexts(): (model: string, field: string) => string | undefined {
  return (model, field) => FIELD_HELP[model]?.[field] || undefined;
}

/**
 * Returns a helper that attaches each model's help text to detail rows by their
 * backend field name: `hint(rows, "freizeit")`. Existing `hint`s are preserved.
 */
export function useRowHints(): (rows: DetailRow[], model: string) => DetailRow[] {
  return (rows, model) =>
    rows.map((r) => (r.field ? { ...r, hint: r.hint ?? FIELD_HELP[model]?.[r.field] } : r));
}

/** Lookup `help(model, firstField)` for a fieldset's description. */
export function useFieldsetHelp(): (model: string, firstField: string) => string | undefined {
  return (model, firstField) => FIELDSET_HELP[model]?.[firstField] || undefined;
}

/**
 * Intro text for a related-object section (recovered from the inline admins'
 * `description`), keyed by a stable section slug. Shown above the section's
 * table / fieldset.
 */
const SECTION_HELP: Record<string, string> = {
  participants:
    "Gib hier bitte alle Personen an, die bei der Ausfahrt dabei sind (auch JL). Hier kannst du auch spontan kurz vor Abfahrt noch Änderungen machen und so jederzeit die aktuelle Teilnehmer*innenliste für die Krisenintervention generieren.",
  ljp: "Hier kannst du an einem Seminarbericht für die Beantragung von Zuschüssen des Landesjugendplans (LJP) arbeiten. Weitere Informationen zur Gestaltung von Seminarberichten findest du im JL-Wiki. Den Seminarbericht oder wahlweise nur TN-Liste und Kostenübersicht kannst du anschließend herunterladen.",
  bills:
    "Gib hier bitte alle deine Ausgaben in Zusammenhang mit der Ausfahrt an und lade entsprechende Belege/Quittungen hoch. Diese müssen für die Beantragung von LJP-Zuschüssen langfristig aufbewahrt werden. Die Kurzbeschreibung der einzelnen Posten wird dabei auf der LJP-Kostenübersicht angezeigt (sinnvoll wären z.B. Anreise, Verpflegung, Material etc.).",
  // Member change-view inlines (Django admin inline `description` intros).
  "emergency-contacts":
    "Trage hier bitte mindestens einen Notfallkontakt mit Kontaktdaten ein. Diese sind notwendig für die Krisenintervention auf Ausfahrten und bei Veranstaltungen.",
  trainings:
    "Bitte trage alle Ausbildungen und Fortbildungen ein, die du bereits besucht hast oder bald besuchst. Lade auch deine Teilnahmebestätigung hoch, damit von der verantwortlichen Person die Felder 'Teilgenommen' und 'Bestanden' gepflegt werden können. Wenn die Aktivitätsauswahl nicht zu deiner Ausbildung passt, dann beschreibe sie im Kommentarfeld.",
  documents:
    "Lade zusätzliche Dokumente hoch (z.B. medizinische Formulare, Einverständniserklärung für Medikamentengabe). Diese Dokumente werden zentral gespeichert und sind im Notfall abrufbar.",
};

/** Lookup `help(section)` for a related-object section's intro text. */
export function useSectionHelp(): (section: string) => string | undefined {
  return (section) => SECTION_HELP[section] || undefined;
}
