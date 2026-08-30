import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, http, HttpResponse, server, useMe } from "../../test/server";
import { renderRoute } from "../../test/utils";

const MEMBERS = [
  {
    id: 1,
    name: "Emma Bergmann",
    prename: "Emma",
    lastname: "Bergmann",
    age: 16,
    birth_date: "2010-03-15",
    email: "emma@example.org",
    phone_number: "+49 6221 1",
    groups: ["Alpingruppe"],
    echoed: true,
    comments: "",
    activity_score: 3,
    confirmed: true,
  },
  {
    id: 2,
    name: "Nele Braun",
    prename: "Nele",
    lastname: "Braun",
    age: 17,
    birth_date: "2009-06-02",
    email: "nele@example.org",
    phone_number: "",
    groups: ["Klettergruppe"],
    echoed: false,
    comments: "",
    activity_score: 0,
    confirmed: true,
  },
];

function listReturns(rows = MEMBERS) {
  server.use(http.get(api("/api/members/"), () => HttpResponse.json(rows)));
}

/** The list is ready once its rows are on screen. */
async function waitForList() {
  await waitFor(() => expect(screen.getByText("Emma Bergmann")).toBeInTheDocument());
}

describe("members list", () => {
  it("renders every member the API returns, with the total in the header", async () => {
    listReturns();
    renderRoute("/app/members");
    await waitForList();

    expect(screen.getByText("Nele Braun")).toBeInTheDocument();
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("filters as the user types, keeping the unfiltered total visible", async () => {
    listReturns();
    const { user } = renderRoute("/app/members");
    await waitForList();

    await user.type(screen.getByPlaceholderText("Suchen…"), "Braun");

    await waitFor(() => expect(screen.queryByText("Emma Bergmann")).not.toBeInTheDocument());
    expect(screen.getByText("Nele Braun")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("offers a way back when a search matches nothing", async () => {
    listReturns();
    const { user } = renderRoute("/app/members");
    await waitForList();

    await user.type(screen.getByPlaceholderText("Suchen…"), "gibtesnicht");

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Filter zurücksetzen" })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await waitFor(() => expect(screen.getByText("Emma Bergmann")).toBeInTheDocument());
  });

  it("shows the create button to someone who may add members", async () => {
    listReturns();
    renderRoute("/app/members");
    await waitForList();
    expect(screen.getByRole("button", { name: "Neues Mitglied" })).toBeInTheDocument();
  });

  it("hides the create button from someone who may not", async () => {
    // The admin never rendered an action the user had no permission for; a
    // filled-in modal that ends in a 403 is worse than no button.
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/members");
    await waitForList();
    expect(screen.queryByRole("button", { name: "Neues Mitglied" })).not.toBeInTheDocument();
  });
});

describe("members list — bulk actions", () => {
  it("reveals the action bar once rows are selected", async () => {
    listReturns();
    const { user } = renderRoute("/app/members");
    await waitForList();

    expect(screen.queryByText(/ausgewählt/)).not.toBeInTheDocument();
    await user.click(screen.getAllByLabelText("Zeile auswählen")[0]);

    expect(screen.getByText("1 ausgewählt")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Aktionen für Auswahl/ }),
    ).toBeInTheDocument();
  });

  it("counts a select-all and clears again", async () => {
    listReturns();
    const { user } = renderRoute("/app/members");
    await waitForList();

    await user.click(screen.getByLabelText("Alle auswählen"));
    expect(screen.getByText("2 ausgewählt")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Auswahl aufheben" }));
    expect(screen.queryByText(/ausgewählt/)).not.toBeInTheDocument();
  });

  it("asks before sending mail to the selection, and reports the outcome", async () => {
    listReturns();
    const echoed: number[] = [];
    server.use(
      http.post(api("/api/members/:id/request-echo"), ({ params }) => {
        echoed.push(Number(params.id));
        return HttpResponse.json({ id: Number(params.id) });
      }),
    );

    const { user } = renderRoute("/app/members");
    await waitForList();
    await user.click(screen.getByLabelText("Alle auswählen"));
    await user.click(screen.getByRole("button", { name: /Aktionen für Auswahl/ }));
    await user.click(screen.getByRole("button", { name: "Echo anfordern" }));

    // Nothing is sent before the user confirms.
    const dialog = within(await screen.findByRole("dialog"));
    expect(echoed).toEqual([]);
    await user.click(dialog.getByRole("button", { name: "Echo anfordern" }));

    await waitFor(() => expect(echoed).toEqual([1, 2]));
    expect(await screen.findByText(/Rückmeldung von 2 Teilnehmenden angefordert/)).toBeInTheDocument();
  });

  it("reports partial failures rather than claiming success", async () => {
    listReturns();
    server.use(
      http.post(api("/api/members/:id/request-echo"), ({ params }) =>
        Number(params.id) === 2
          ? HttpResponse.json({ detail: ["Kein Geburtsdatum hinterlegt."] }, { status: 422 })
          : HttpResponse.json({ id: 1 }),
      ),
    );

    const { user } = renderRoute("/app/members");
    await waitForList();
    await user.click(screen.getByLabelText("Alle auswählen"));
    await user.click(screen.getByRole("button", { name: /Aktionen für Auswahl/ }));
    await user.click(screen.getByRole("button", { name: "Echo anfordern" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Echo anfordern" }));

    // One succeeded, one failed — the user must be told both.
    expect(await screen.findByText(/Rückmeldung von 1 Teilnehmenden angefordert/)).toBeInTheDocument();
    expect(await screen.findByText(/Nele Braun.*Kein Geburtsdatum/)).toBeInTheDocument();
  });
});

describe("members list — permission errors", () => {
  it("explains a 403 instead of printing the permission codename", async () => {
    server.use(
      http.get(api("/api/members/"), () =>
        HttpResponse.json({ detail: "members.view_member" }, { status: 403 }),
      ),
    );
    renderRoute("/app/members");

    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
    expect(screen.queryByText(/members\.view_member/)).not.toBeInTheDocument();
  });
});
