import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DetailRow } from "../components/ui";
import { useFieldsetHelp, useHelpTexts, useRowHints, useSectionHelp } from "./helpTexts";

describe("useHelpTexts", () => {
  it("returns the model's recovered help text for a field", () => {
    const { result } = renderHook(() => useHelpTexts());
    expect(result.current("freizeit", "destination")).toBe("z.B. ein Gipfel");
  });

  it("returns undefined for a field or model it knows nothing about", () => {
    const { result } = renderHook(() => useHelpTexts());
    expect(result.current("freizeit", "name")).toBeUndefined();
    expect(result.current("gibtesnicht", "destination")).toBeUndefined();
  });
});

describe("useRowHints", () => {
  it("attaches a help text to the row whose field name matches", () => {
    const { result } = renderHook(() => useRowHints());
    const rows: DetailRow[] = [
      { label: "Ziel", value: "Gipfel", field: "destination" },
      { label: "Name", value: "Skifreizeit", field: "name" },
    ];
    const hinted = result.current(rows, "freizeit");
    expect(hinted[0].hint).toBe("z.B. ein Gipfel");
    expect(hinted[1].hint).toBeUndefined();
  });

  it("leaves a row without a backend field name untouched", () => {
    const { result } = renderHook(() => useRowHints());
    const rows: DetailRow[] = [{ label: "Alter", value: 15 }];
    expect(result.current(rows, "member")).toEqual(rows);
  });

  it("does not overwrite a hint the caller set itself", () => {
    const { result } = renderHook(() => useRowHints());
    const rows: DetailRow[] = [
      { label: "Ziel", value: "x", field: "destination", hint: "Eigener Hinweis" },
    ];
    expect(result.current(rows, "freizeit")[0].hint).toBe("Eigener Hinweis");
  });
});

describe("useFieldsetHelp", () => {
  it("returns the fieldset intro keyed by its leading field", () => {
    const { result } = renderHook(() => useFieldsetHelp());
    expect(result.current("freizeit", "name")).toMatch(/allgemein Angaben zu deiner Ausfahrt/);
  });

  it("returns undefined for a model without fieldset descriptions", () => {
    const { result } = renderHook(() => useFieldsetHelp());
    expect(result.current("member", "prename")).toBeUndefined();
  });
});

describe("useSectionHelp", () => {
  it("returns the inline admin's intro for a known section slug", () => {
    const { result } = renderHook(() => useSectionHelp());
    expect(result.current("emergency-contacts")).toMatch(/mindestens einen Notfallkontakt/);
  });

  it("returns undefined for an unknown section", () => {
    const { result } = renderHook(() => useSectionHelp());
    expect(result.current("gibtesnicht")).toBeUndefined();
  });
});
