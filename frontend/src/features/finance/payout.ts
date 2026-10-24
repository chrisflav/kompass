import type { components } from "../../api/schema";

type StatementOut = components["schemas"]["StatementOut"];

/**
 * Who makes the bank transfers once a statement is released.
 *
 * It is a declaration of the section's rules (`Ruleset.payout`), carried on
 * every statement because a statement is bound to the version it was created
 * under: `"self"` means the person reviewing it transfers the money, `"office"`
 * means the Geschäftsstelle does, after a handoff.
 */
export type PayoutMode = "self" | "office";

/** The mode of one statement, with an unknown value read as the default. */
export function payoutMode(statement: Pick<StatementOut, "payout_mode">): PayoutMode {
  return statement.payout_mode === "office" ? "office" : "self";
}

/**
 * What the terminal step of a review says, per mode.
 *
 * There is no wording true in both, which is the whole reason this file exists.
 * "Ausgezahlt" is false in a section whose office pays — Kompass never learns
 * the money moved — and "zur Auszahlung übergeben" is false in one whose
 * treasurer pays, because nothing was handed to anybody. A single screen cannot
 * describe both acts in one sentence, so it looks the sentence up.
 *
 * Collected in one table rather than scattered as ternaries over the component
 * for two reasons. A reader can see what the two modes actually differ in, down
 * to the word; and a sentence that has to exist twice is forced to exist twice,
 * instead of one mode quietly inheriting the other's wording, which is exactly
 * the defect this replaces.
 */
export interface PayoutWords {
  /** The one button a handed-in statement offers on its record page. */
  door: string;
  /** The heading over the transfers, inside the Freigabe leg. */
  heading: string;
  /** What to do, before the act. */
  lead: (transfers: number, payees: number) => string;
  /** What a released statement says about itself. */
  released: string;
  /**
   * The booking column that says a booking has been released.
   *
   * `Transaction.confirmed` is set by the release, so in a handoff it means
   * the booking was handed over — nobody in Kompass knows whether it has been
   * paid. The column used to say "Bezahlt" under both arrangements, which was
   * a claim about money in a section that moves none from here.
   */
  booked: string;
  /** The two record rows that say who released it, and when. */
  releasedBy: string;
  releasedOn: string;
  /** The Etappen rail's readout for a released statement. */
  readout: string;
  /** The sentence in front of the reason a release is impossible. */
  locked: (reason: string) => string;
  /** Why a booking without a ledger holds the leg up. */
  needsLedger: (bookings: number) => string;
  /** The bookings nobody can transfer, and why that matters here. */
  unpayable: (names: string[]) => string;
  /** Whether the reviewer is asked to confirm having made the transfers. */
  acknowledgement: string | null;
  /** Whether a QR code is worth drawing: only a mode that pays from here. */
  codes: boolean;
  /** The act, as a button. */
  release: string;
  /**
   * Whether `/confirm` mails the office's copy by itself.
   *
   * It does where the mail *is* the release: the server sends it before the
   * status moves and refuses to move the status if it did not go. The client
   * must then not ask for it with `send`, or one act becomes two mails. Where
   * the reviewer makes the transfers the mail is a receipt they ask for, and
   * the flag is how they ask.
   */
  mailsItself: boolean;
  /** The dialog in front of the act. */
  dialog: { title: string; message: (total: string, payees: number) => string; confirm: string };
  /** What the toast says once it is done. */
  done: string;
  /**
   * The second act, where the mode has two.
   *
   * Self-payment splits the release in two — confirm, and confirm *and* mail
   * the receipt to the office — because the mail is a courtesy there and the
   * money has already moved either way. A handoff has no such pair: the mail
   * *is* the handoff, so "release without mailing" would be a status claiming
   * an act that did not happen, and the mode offers one button.
   */
  releaseOnly: string | null;
}

export const PAYOUT_WORDS: Record<PayoutMode, PayoutWords> = {
  self: {
    door: "Prüfen & auszahlen",
    heading: "Auszahlung",
    lead: (transfers, payees) =>
      `Überweise die folgenden ${transfers} Beträge an ${payees} Empfänger*innen — scanne dazu den QR-Code mit deiner Banking-App — und bestätige die Abrechnung danach.`,
    released: "Diese Abrechnung ist bereits ausgezahlt.",
    booked: "Bezahlt",
    releasedBy: "Bezahlt von",
    releasedOn: "Bezahlt am",
    readout: "ausgezahlt",
    locked: (reason) => `Auszahlen ist gesperrt: ${reason}`,
    needsLedger: (bookings) =>
      `${bookings} Buchung(en) ohne Konto — Zusammenfassen und Auszahlen brauchen es.`,
    unpayable: (names) =>
      `${names.length} Buchung(en) ohne QR-Code: ${names.join(", ")}. Ohne gültige IBAN muss die Überweisung von Hand erfasst werden.`,
    acknowledgement: "Ich habe die aufgeführten Überweisungen ausgeführt.",
    codes: true,
    release: "Bestätigen & Beleg senden",
    mailsItself: false,
    dialog: {
      title: "Auszahlung bestätigen?",
      message: (total, payees) =>
        `${total} an ${payees} Empfänger*innen. Der Zuschussbeleg geht an die Geschäftsstelle.`,
      confirm: "Bestätigen & senden",
    },
    done: "Abrechnung bestätigt und Beleg versendet.",
    releaseOnly: "Nur bestätigen",
  },
  office: {
    door: "Prüfen & übergeben",
    heading: "Übergabe an die Geschäftsstelle",
    lead: (transfers, payees) =>
      `Die Geschäftsstelle überweist die folgenden ${transfers} Beträge an ${payees} Empfänger*innen. Mit der Übergabe geht der Beleg mit allen Überweisungsaufträgen an sie; ob das Geld geflossen ist, erfährt Kompass nicht.`,
    released: "Diese Abrechnung ist zur Auszahlung übergeben.",
    booked: "Übergeben",
    releasedBy: "Übergeben von",
    releasedOn: "Übergeben am",
    readout: "übergeben",
    locked: (reason) => `Die Übergabe ist gesperrt: ${reason}`,
    needsLedger: (bookings) =>
      `${bookings} Buchung(en) ohne Konto — Zusammenfassen und Übergeben brauchen es.`,
    unpayable: (names) =>
      `${names.length} Buchung(en) ohne gültige IBAN: ${names.join(", ")}. Die Geschäftsstelle kann diese Überweisungen nicht ausführen — hinterlege die IBAN vor der Übergabe.`,
    // Nothing moves here, so there is nothing to acknowledge. Asking "ich habe
    // die Überweisungen ausgeführt" of somebody who does not make them is
    // asking them to claim a payment that nobody has made, which is the one
    // thing this mode exists to stop saying. The dialog below is the deliberate
    // stop instead, and it is not optional.
    acknowledgement: null,
    codes: false,
    release: "Zur Auszahlung übergeben",
    mailsItself: true,
    dialog: {
      title: "Zur Auszahlung übergeben?",
      message: (total, payees) =>
        `${total} an ${payees} Empfänger*innen. Der Beleg mit allen Überweisungsaufträgen geht an die Geschäftsstelle; sie führt die Überweisungen aus.`,
      confirm: "Übergeben",
    },
    done: "Abrechnung zur Auszahlung übergeben.",
    releaseOnly: null,
  },
};

/** The words for one statement's mode. */
export function payoutWords(statement: Pick<StatementOut, "payout_mode">): PayoutWords {
  return PAYOUT_WORDS[payoutMode(statement)];
}
