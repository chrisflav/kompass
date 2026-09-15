import { describe, expect, it, vi } from "vitest";

import { ApiError, setUnauthorizedHandler, unwrap } from "./http";

/** The three error payload shapes the backend actually produces. */
const ninja422 = {
  detail: [
    {
      type: "string_too_short",
      loc: ["body", "payload", "prename"],
      msg: "String should have at least 1 character",
      ctx: { min_length: 1 },
    },
    {
      type: "missing",
      loc: ["body", "payload", "emergency_contacts", 0, "phone_number"],
      msg: "Field required",
    },
  ],
};
const django422 = {
  detail: ["Diese Ausfahrt hat bereits eine Abrechnung."],
  errors: { __all__: ["Diese Ausfahrt hat bereits eine Abrechnung."] },
};

describe("ApiError.messageFor", () => {
  it("turns a django-ninja validation list into readable German, not [object Object]", () => {
    const message = ApiError.messageFor(422, ninja422);
    expect(message).not.toContain("[object Object]");
    expect(message).toContain("prename");
    expect(message).toContain("Dieses Feld darf nicht leer sein.");
    expect(message).toContain("phone_number");
    expect(message).toContain("Dieses Feld ist erforderlich.");
  });

  it("joins our own ValidationError messages", () => {
    expect(ApiError.messageFor(422, django422)).toBe(
      "Diese Ausfahrt hat bereits eine Abrechnung.",
    );
  });

  it("never shows the permission codename a 403 carries", () => {
    const message = ApiError.messageFor(403, { detail: "members.view_group" });
    expect(message).not.toContain("members.view_group");
    expect(message).toBe("Dazu fehlt dir die Berechtigung.");
  });

  it("shows a 403 the API marked as written for the user", () => {
    // Refusals that explain a rule are the only thing that makes the 403
    // actionable; replacing them with the generic sentence hid the reason.
    const message = ApiError.messageFor(403, {
      detail: "A sent message can no longer be edited.",
      displayable: true,
    });
    expect(message).toBe("A sent message can no longer be edited.");
  });

  it("still hides a 403 that only claims to be displayable", () => {
    expect(ApiError.messageFor(403, { detail: "members.view_group", displayable: false })).toBe(
      "Dazu fehlt dir die Berechtigung.",
    );
    expect(ApiError.messageFor(403, { detail: "x", displayable: "yes" })).toBe(
      "Dazu fehlt dir die Berechtigung.",
    );
  });

  it("uses the status for 401 rather than the body", () => {
    const message = ApiError.messageFor(401, { detail: "Unauthorized" });
    expect(message).not.toContain("Unauthorized");
    expect(message).toMatch(/nicht angemeldet/i);
  });

  it("replaces Django's developer-facing 404 text", () => {
    const message = ApiError.messageFor(404, {
      detail: "Not Found: No Member matches the given query.",
    });
    expect(message).not.toContain("No Member matches");
    expect(message).toBe("Nicht gefunden.");
  });

  it("gives a 5xx an actionable sentence instead of a bare code", () => {
    const message = ApiError.messageFor(500, null);
    expect(message).toMatch(/Serverfehler/);
    expect(message).not.toBe("Fehler 500.");
  });

  it("passes a plain string detail through for statuses that carry one", () => {
    expect(ApiError.messageFor(422, { detail: "Etwas ist schiefgelaufen." })).toBe(
      "Etwas ist schiefgelaufen.",
    );
  });

  it("falls back to a generic sentence when there is no body at all", () => {
    expect(ApiError.messageFor(418, undefined)).toContain("418");
  });
});

describe("ApiError.fieldErrors", () => {
  it("keys a ninja validation list by its innermost field name", () => {
    const errors = new ApiError(422, ninja422).fieldErrors;
    expect(Object.keys(errors).sort()).toEqual(["phone_number", "prename"]);
    expect(errors.prename).toEqual(["Dieses Feld darf nicht leer sein."]);
  });

  it("passes our own per-field map through unchanged", () => {
    const errors = new ApiError(422, {
      detail: ["x"],
      errors: { year_from: ["Dieses Feld darf nicht null sein."] },
    }).fieldErrors;
    expect(errors.year_from).toEqual(["Dieses Feld darf nicht null sein."]);
  });

  it("is empty when the body carries no field information", () => {
    expect(new ApiError(500, null).fieldErrors).toEqual({});
  });

  it("collects several messages for the same field", () => {
    const errors = new ApiError(422, {
      detail: [
        { type: "missing", loc: ["body", "payload", "email"], msg: "Field required" },
        { type: "value_error", loc: ["body", "payload", "email"], msg: "bad" },
      ],
    }).fieldErrors;
    expect(errors.email).toHaveLength(2);
  });
});

describe("unwrap", () => {
  const ok = (data: unknown) =>
    Promise.resolve({ data, response: new Response(null, { status: 200 }) });
  const fail = (status: number, error: unknown) =>
    Promise.resolve({ error, response: new Response(null, { status }) });

  it("returns the payload on success", async () => {
    await expect(unwrap(ok({ id: 1 }))).resolves.toEqual({ id: 1 });
  });

  it("throws an ApiError carrying the status", async () => {
    await expect(unwrap(fail(403, { detail: "members.view_group" }))).rejects.toMatchObject({
      status: 403,
      message: "Dazu fehlt dir die Berechtigung.",
    });
  });

  it("notifies the unauthorized handler exactly once per 401", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    await expect(unwrap(fail(401, null))).rejects.toThrow();
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
    setUnauthorizedHandler(null);
  });

  it("leaves the handler alone for other failures", async () => {
    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);
    await expect(unwrap(fail(500, null))).rejects.toThrow();
    expect(onUnauthorized).not.toHaveBeenCalled();
    setUnauthorizedHandler(null);
  });
});

describe("ApiError.fieldErrors — locations without a field", () => {
  it("groups an error that names no field under the empty key", () => {
    // ninja reports a body-level failure as loc: ["body"] — there is no field to
    // hang the message on, so it must not be lost.
    const err = new ApiError(422, {
      detail: [{ type: "missing", loc: ["body"], msg: "Field required" }],
    });
    expect(err.fieldErrors).toEqual({});
    // The message is still translated and shown, just not attached to a field.
    expect(err.message).toBe("Dieses Feld ist erforderlich.");
  });
});
