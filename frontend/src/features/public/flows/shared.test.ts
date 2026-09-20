import { describe, expect, it } from "vitest";

import { cleanContacts, isBlankContact } from "./shared";

const filled = { prename: "Erika", lastname: "Mustermann", phone_number: "0711 1", email: "" };
const blank = { prename: "", lastname: "", phone_number: "", email: "" };

describe("isBlankContact", () => {
  it("treats a row the user never touched as blank", () => {
    expect(isBlankContact(blank)).toBe(true);
  });

  it("treats whitespace-only input as blank", () => {
    expect(isBlankContact({ ...blank, prename: "   " })).toBe(true);
  });

  it("is not blank once any field carries content", () => {
    expect(isBlankContact({ ...blank, phone_number: "0711" })).toBe(false);
    expect(isBlankContact({ ...blank, email: "a@b.de" })).toBe(false);
    expect(isBlankContact(filled)).toBe(false);
  });

  it("tolerates a missing optional email", () => {
    expect(isBlankContact({ ...blank, email: undefined as unknown as string })).toBe(true);
  });
});

describe("cleanContacts", () => {
  it("drops an extra row the user added but never filled in", () => {
    // The regression: that row used to be stored as a contact with four empty
    // fields, silently polluting the member's emergency contacts.
    expect(cleanContacts([filled, blank])).toEqual([filled]);
  });

  it("keeps every filled row", () => {
    const second = { ...filled, prename: "Max" };
    expect(cleanContacts([filled, second])).toEqual([filled, second]);
  });

  it("keeps one row when everything is blank, so the backend still complains", () => {
    // Submitting an empty list would pass the "at least one contact" check on a
    // technicality; keeping the row makes the server report a missing contact.
    expect(cleanContacts([blank, blank])).toEqual([blank]);
  });

  it("leaves a single filled row untouched", () => {
    expect(cleanContacts([filled])).toEqual([filled]);
  });
});
