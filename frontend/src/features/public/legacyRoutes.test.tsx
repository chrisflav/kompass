import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderRoute } from "../../test/utils";

/**
 * The pre-SPA Django URLs are still in circulation (bookmarks, e-mails sent
 * years ago), so each must land on its new flow with the ``?key=`` intact.
 */
describe("legacy URL redirects", () => {
  const cases: [string, string][] = [
    ["/members/echo", "Daten aktualisieren"],
    ["/members/registration", "Einladung annehmen"],
    ["/members/register/upload", "Anmeldebogen hochladen"],
    ["/members/register/download", "Anmeldebogen hochladen"],
    ["/members/register", "Anmeldung"],
    ["/members/waitinglist/confirm", "Warteliste bestätigen"],
    ["/members/waitinglist/leave", "Warteliste verlassen"],
    ["/members/waitinglist/invitation/confirm", "Einladung annehmen"],
    ["/members/waitinglist/invitation/reject", "Einladung ablehnen"],
    ["/members/waitinglist", "Auf die Warteliste"],
    ["/members/mail/confirm", "E-Mail bestätigen"],
    ["/newsletter/unsubscribe", "Newsletter abbestellen"],
    ["/login/register", "Passwort setzen"],
  ];

  it.each(cases)("%s lands on the %s flow", (from, heading) => {
    renderRoute(from, { authenticated: false });
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it.each(cases)("the /de/ variant of %s works too", (from, heading) => {
    renderRoute(`/de${from}`, { authenticated: false });
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("preserves the secret key across the redirect", () => {
    renderRoute("/de/members/mail/confirm?key=GEHEIM", { authenticated: false });
    // With the key carried over the flow offers its action rather than the
    // "no key given" error.
    expect(screen.getByRole("button", { name: "E-Mail bestätigen" })).toBeInTheDocument();
  });
});
