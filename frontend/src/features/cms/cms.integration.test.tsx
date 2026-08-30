import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  api,
  djangoValidation,
  http,
  HttpResponse,
  multipartFields,
  multipartFilenames,
  server,
  useMe,
} from "../../test/server";
import {
  fillEveryField,
  pickEverySelect,
  renderRoute,
  sortByEveryColumn,
} from "../../test/utils";

/** The dropdown panel shared by Select / MultiSelect. */
const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

/* --- FAQ ------------------------------------------------------------------ */

const FAQ = { id: 1, question: "Was kostet das?", answer: "Nichts." };

describe("cms — FAQ", () => {
  function listReturns(rows = [FAQ]) {
    server.use(http.get(api("/api/startpage/faqs"), () => HttpResponse.json(rows)));
  }

  it("lists the questions with a count", async () => {
    listReturns();
    renderRoute("/app/cms/faqs");
    expect(await screen.findByText("Was kostet das?")).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/cms/faqs");
    expect(await screen.findByText("Keine Fragen vorhanden.")).toBeInTheDocument();
  });

  it("sorts by its column in both directions", async () => {
    listReturns([FAQ, { ...FAQ, id: 2, question: "Und sonst?" }]);
    const { user } = renderRoute("/app/cms/faqs");
    await screen.findByText("Was kostet das?");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/cms/faqs");
    await screen.findByText("Was kostet das?");
    expect(screen.queryByRole("button", { name: "Neue Frage" })).not.toBeInTheDocument();
  });

  it("creates a question and opens it", async () => {
    useMe({ permissions: ["startpage.add_faq"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/startpage/faqs"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...FAQ, id: 2, question: "Neu?" });
      }),
      http.get(api("/api/startpage/faqs/2"), () =>
        HttpResponse.json({ ...FAQ, id: 2, question: "Neu?" }),
      ),
    );
    const { user } = renderRoute("/app/cms/faqs");
    await user.click(await screen.findByRole("button", { name: "Neue Frage" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Frage"), "Neu?");
    await user.type(dialog.getByLabelText("Antwort"), "Antwort.");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).toEqual({ question: "Neu?", answer: "Antwort." }));
    expect(await screen.findByText("Frage angelegt.")).toBeInTheDocument();
  });

  it("shows a server field error on the create form", async () => {
    useMe({ permissions: ["startpage.add_faq"] });
    listReturns();
    server.use(
      http.post(api("/api/startpage/faqs"), () =>
        djangoValidation({
          question: ["Diese Frage gibt es schon."],
          answer: ["Die Antwort fehlt auch."],
        }),
      ),
    );
    const { user } = renderRoute("/app/cms/faqs");
    await user.click(await screen.findByRole("button", { name: "Neue Frage" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Frage"), "Was kostet das?");
    await user.type(dialog.getByLabelText("Antwort"), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Diese Frage gibt es schon.")).not.toHaveLength(0);
    expect(screen.getByText("Die Antwort fehlt auch.")).toBeInTheDocument();
  });

  it("closes the create modal on Abbrechen", async () => {
    useMe({ permissions: ["startpage.add_faq"] });
    listReturns();
    const { user } = renderRoute("/app/cms/faqs");
    await user.click(await screen.findByRole("button", { name: "Neue Frage" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("closes the create modal with ×, and leaves edit mode again", async () => {
    useMe({ permissions: ["startpage.add_faq"] });
    listReturns();
    server.use(http.get(api("/api/startpage/faqs/1"), () => HttpResponse.json(FAQ)));
    const { user } = renderRoute("/app/cms/faqs");

    await user.click(await screen.findByRole("button", { name: "Neue Frage" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("opens a question from the list and edits it", async () => {
    listReturns();
    let put: unknown = null;
    server.use(
      http.get(api("/api/startpage/faqs/1"), () => HttpResponse.json(FAQ)),
      http.put(api("/api/startpage/faqs/1"), async ({ request }) => {
        put = await request.json();
        return HttpResponse.json({ ...FAQ, answer: "Doch etwas." });
      }),
    );
    const { user } = renderRoute("/app/cms/faqs");
    await user.click(await screen.findByText("Was kostet das?"));

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    const answer = screen.getByDisplayValue("Nichts.");
    await user.clear(answer);
    await user.type(answer, "Doch etwas.");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() =>
      expect(put).toEqual({ question: "Was kostet das?", answer: "Doch etwas." }),
    );
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("leaves edit mode again on Abbrechen", async () => {
    server.use(http.get(api("/api/startpage/faqs/1"), () => HttpResponse.json(FAQ)));
    const { user } = renderRoute("/app/cms/faqs/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Nichts.")).not.toBeInTheDocument();
  });

  it("reports a rejected save without leaving edit mode", async () => {
    server.use(
      http.get(api("/api/startpage/faqs/1"), () => HttpResponse.json(FAQ)),
      http.put(api("/api/startpage/faqs/1"), () =>
        djangoValidation({ answer: ["Die Antwort fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/cms/faqs/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(await screen.findAllByText("Die Antwort fehlt.")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });

  it("asks before deleting, and deletes on confirmation", async () => {
    listReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/startpage/faqs/1"), () => HttpResponse.json(FAQ)),
      http.delete(api("/api/startpage/faqs/1"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/cms/faqs/1");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Diese Frage wirklich löschen?")).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    expect(deleted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("reports a refused delete", async () => {
    server.use(
      http.get(api("/api/startpage/faqs/1"), () => HttpResponse.json(FAQ)),
      http.delete(api("/api/startpage/faqs/1"), () =>
        HttpResponse.json({ detail: "startpage.delete_faq" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/app/cms/faqs/1");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    server.use(http.get(api("/api/startpage/faqs/1"), () => HttpResponse.json(FAQ)));
    const { user } = renderRoute("/app/cms/faqs/1");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- Links ---------------------------------------------------------------- */

const LINK = {
  id: 3,
  title: "JL-Wiki",
  url: "https://wiki.example.org",
  description: "Interne Doku",
  visible: true,
  icon: null,
};

describe("cms — Links", () => {
  function listReturns(rows = [LINK]) {
    server.use(http.get(api("/api/startpage/links"), () => HttpResponse.json(rows)));
  }

  it("lists links with their visibility", async () => {
    listReturns([LINK, { ...LINK, id: 4, title: "", visible: false }]);
    renderRoute("/app/cms/links");
    expect(await screen.findByText("JL-Wiki")).toBeInTheDocument();
    // An unnamed link still shows its URL rather than a blank row.
    expect(screen.getAllByText("https://wiki.example.org")).toHaveLength(2);
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([LINK, { ...LINK, id: 4, title: "", visible: false }]);
    const { user } = renderRoute("/app/cms/links");
    await screen.findByText("JL-Wiki");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("fills every field of the create form", async () => {
    useMe({ permissions: ["startpage.add_link"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/startpage/links"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ url: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/cms/links");
    await user.click(await screen.findByRole("button", { name: "Neuer Link" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      title: "Text",
      url: "Text",
      description: "Text",
      // The checkbox starts checked in the create form, so the pass clears it.
      visible: false,
    });
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/cms/links");
    expect(await screen.findByText("Keine Links vorhanden.")).toBeInTheDocument();
  });

  it("creates a link", async () => {
    useMe({ permissions: ["startpage.add_link"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/startpage/links"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...LINK, id: 9 });
      }),
      http.get(api("/api/startpage/links/9"), () => HttpResponse.json({ ...LINK, id: 9 })),
    );
    const { user } = renderRoute("/app/cms/links");
    await user.click(await screen.findByRole("button", { name: "Neuer Link" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Titel"), "Neu");
    await user.type(dialog.getByLabelText("URL"), "https://neu.example.org");
    await user.click(dialog.getByLabelText("Sichtbar"));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ title: "Neu", url: "https://neu.example.org" });
    expect(await screen.findByText("Link angelegt.")).toBeInTheDocument();
  });

  it("edits a link's fields, including the visible flag", async () => {
    let put: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)),
      http.put(api("/api/startpage/links/3"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...LINK, visible: false });
      }),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const title = screen.getByDisplayValue("JL-Wiki");
    await user.clear(title);
    await user.type(title, "Wiki");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({ title: "Wiki", visible: false });
  });

  it("uploads an icon through its own multipart endpoint", async () => {
    let uploaded: string | undefined;
    server.use(
      http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)),
      http.post(api("/api/startpage/links/3/icon"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json({ ...LINK, icon: "/media/icon.png" });
      }),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(screen.getByRole("button", { name: "Hochladen" })).toBeDisabled();
    await user.upload(input, new File(["x"], "icon.png", { type: "image/png" }));
    await user.click(screen.getByRole("button", { name: "Hochladen" }));

    await waitFor(() => expect(uploaded).toBe("icon.png"));
    expect(await screen.findByText("Icon hochgeladen.")).toBeInTheDocument();
  });

  it("reports a refused icon upload", async () => {
    server.use(
      http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)),
      http.post(api("/api/startpage/links/3/icon"), () =>
        HttpResponse.json({ detail: "Die Datei ist zu groß." }, { status: 413 }),
      ),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.upload(
      document.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["x"], "gross.png", { type: "image/png" }),
    );
    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    expect(await screen.findByText("Die Datei ist zu groß.")).toBeInTheDocument();
  });

  it("still reports an upload failure whose body is not JSON", async () => {
    server.use(
      http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)),
      http.post(api("/api/startpage/links/3/icon"), () =>
        new HttpResponse("<html>502</html>", { status: 502 }),
      ),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.upload(
      document.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["x"], "icon.png", { type: "image/png" }),
    );
    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();
  });

  it("previews the current icon while replacing it", async () => {
    server.use(
      http.get(api("/api/startpage/links/3"), () =>
        HttpResponse.json({ ...LINK, icon: "/media/icon.png" }),
      ),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getByRole("img", { name: "Icon" })).toHaveAttribute("src", "/media/icon.png");
  });

  it("shows an existing icon rather than an em dash", async () => {
    server.use(
      http.get(api("/api/startpage/links/3"), () =>
        HttpResponse.json({ ...LINK, icon: "/media/icon.png" }),
      ),
    );
    renderRoute("/app/cms/links/3");
    expect(await screen.findByRole("img", { name: "Icon" })).toHaveAttribute(
      "src",
      "/media/icon.png",
    );
  });

  it("shows a server field error when the create is rejected", async () => {
    useMe({ permissions: ["startpage.add_link"] });
    listReturns();
    server.use(
      http.post(api("/api/startpage/links"), () =>
        djangoValidation({ url: ["Bitte eine gültige URL angeben."] }),
      ),
    );
    const { user } = renderRoute("/app/cms/links");
    await user.click(await screen.findByRole("button", { name: "Neuer Link" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("URL"), "keine-url");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Bitte eine gültige URL angeben.")).not.toHaveLength(0);
  });

  it("shows a server field error when the save is rejected", async () => {
    server.use(
      http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)),
      http.put(api("/api/startpage/links/3"), () =>
        djangoValidation({ url: ["Bitte eine gültige URL angeben."] }),
      ),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Bitte eine gültige URL angeben.")).not.toHaveLength(0);
  });

  it("shows every rejected field of the create form, and closes it with ×", async () => {
    useMe({ permissions: ["startpage.add_link"] });
    listReturns();
    server.use(
      http.post(api("/api/startpage/links"), () =>
        djangoValidation({
          title: ["Titel fehlt."],
          url: ["URL fehlt."],
          description: ["Zu lang."],
          visible: ["Ungültig."],
        }),
      ),
    );
    const { user } = renderRoute("/app/cms/links");
    await user.click(await screen.findByRole("button", { name: "Neuer Link" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("URL"), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Titel fehlt.")).not.toHaveLength(0);
    expect(screen.getByText("URL fehlt.")).toBeInTheDocument();
    expect(screen.getByText("Zu lang.")).toBeInTheDocument();
    expect(screen.getByText("Ungültig.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Neuer Link" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("opens a link from its row and leaves edit mode again", async () => {
    listReturns();
    server.use(http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)));
    const { user } = renderRoute("/app/cms/links");
    await user.click(await screen.findByText("JL-Wiki"));

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    await user.click(screen.getByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });

  it("copes with a link whose title and description are null", async () => {
    server.use(
      http.get(api("/api/startpage/links/3"), () =>
        HttpResponse.json({ ...LINK, title: null, description: null, visible: false }),
      ),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    // The nulls become empty strings in the draft rather than "null".
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("reports a refused delete", async () => {
    server.use(
      http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)),
      http.delete(api("/api/startpage/links/3"), () =>
        HttpResponse.json({ detail: "startpage.delete_link" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("clears a chosen icon file again", async () => {
    server.use(http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)));
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "icon.png", { type: "image/png" }));
    expect(screen.getByRole("button", { name: "Hochladen" })).toBeEnabled();
    // Clearing a file input yields an empty FileList, which must reset to null.
    await user.upload(input, []);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Hochladen" })).toBeDisabled(),
    );
  });

  it("deletes a link once confirmed", async () => {
    let deleted = false;
    server.use(
      http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)),
      http.get(api("/api/startpage/links"), () => HttpResponse.json([])),
      http.delete(api("/api/startpage/links/3"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Link gelöscht.")).toBeInTheDocument();
  });
});

/* --- Sections ------------------------------------------------------------- */

const SECTION = {
  id: 2,
  title: "Ausbildung",
  urlname: "ausbildung",
  website_text: "Werde Jugendleiter.",
  show_in_navigation: true,
};

describe("cms — Bereiche", () => {
  function listReturns(rows = [SECTION]) {
    server.use(http.get(api("/api/startpage/sections"), () => HttpResponse.json(rows)));
  }

  it("lists the sections with their public link", async () => {
    listReturns();
    renderRoute("/app/cms/sections");
    expect(await screen.findByText("Ausbildung")).toBeInTheDocument();
    expect(screen.getByText("ausbildung")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([SECTION, { ...SECTION, id: 3, title: "Zweiter", show_in_navigation: false }]);
    const { user } = renderRoute("/app/cms/sections");
    await screen.findByText("Ausbildung");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("fills every field of the create form", async () => {
    useMe({ permissions: ["startpage.add_section"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/startpage/sections"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ urlname: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/cms/sections");
    await user.click(await screen.findByRole("button", { name: "Neuer Bereich" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      title: "Text",
      urlname: "Text",
      website_text: "Text",
      // The checkbox starts checked in the create form, so the pass clears it.
      show_in_navigation: false,
    });
  });

  it("shows an em dash for a section without a slug", async () => {
    listReturns([{ ...SECTION, urlname: "" }]);
    renderRoute("/app/cms/sections");
    await screen.findByText("Ausbildung");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("closes the create modal on Abbrechen", async () => {
    useMe({ permissions: ["startpage.add_section"] });
    listReturns();
    const { user } = renderRoute("/app/cms/sections");
    await user.click(await screen.findByRole("button", { name: "Neuer Bereich" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/cms/sections");
    expect(await screen.findByText("Keine Bereiche vorhanden.")).toBeInTheDocument();
  });

  it("creates a section", async () => {
    useMe({ permissions: ["startpage.add_section"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/startpage/sections"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...SECTION, id: 9 });
      }),
      http.get(api("/api/startpage/sections/9"), () => HttpResponse.json({ ...SECTION, id: 9 })),
    );
    const { user } = renderRoute("/app/cms/sections");
    await user.click(await screen.findByRole("button", { name: "Neuer Bereich" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Titel/), "Neu");
    await user.type(dialog.getByLabelText(/^URL/), "neu");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ title: "Neu", urlname: "neu" });
    expect(await screen.findByText("Bereich angelegt.")).toBeInTheDocument();
  });

  it("shows server field errors on both the create and the save form", async () => {
    useMe({ permissions: ["startpage.add_section"] });
    listReturns();
    server.use(
      http.post(api("/api/startpage/sections"), () =>
        djangoValidation({
          title: ["Der Titel fehlt."],
          urlname: ["Dieses Kürzel ist vergeben."],
          website_text: ["Der Text fehlt."],
          show_in_navigation: ["Ungültig."],
        }),
      ),
    );
    const { user } = renderRoute("/app/cms/sections");
    await user.click(await screen.findByRole("button", { name: "Neuer Bereich" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Titel/), "Neu");
    await user.type(dialog.getByLabelText(/^URL/), "neu");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Dieses Kürzel ist vergeben.")).not.toHaveLength(0);
    expect(screen.getByText("Der Titel fehlt.")).toBeInTheDocument();
    expect(screen.getByText("Der Text fehlt.")).toBeInTheDocument();
    expect(screen.getByText("Ungültig.")).toBeInTheDocument();
  });

  it("reports a rejected save on the detail form", async () => {
    server.use(
      http.get(api("/api/startpage/sections/2"), () => HttpResponse.json(SECTION)),
      http.put(api("/api/startpage/sections/2"), () =>
        djangoValidation({ title: ["Der Titel fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/cms/sections/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Titel fehlt.")).not.toHaveLength(0);
  });

  it("links to the public page, or shows an em dash without a slug", async () => {
    server.use(
      http.get(api("/api/startpage/sections/2"), () => HttpResponse.json(SECTION)),
    );
    const withSlug = renderRoute("/app/cms/sections/2");
    expect(await screen.findByRole("link", { name: "/bereich/ausbildung" })).toHaveAttribute(
      "href",
      "/bereich/ausbildung",
    );
    withSlug.unmount();

    server.use(
      http.get(api("/api/startpage/sections/2"), () =>
        HttpResponse.json({ ...SECTION, urlname: "" }),
      ),
    );
    renderRoute("/app/cms/sections/2");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.queryByRole("link", { name: /bereich/ })).not.toBeInTheDocument();
  });

  it("opens a section from its row, leaves edit mode and goes back", async () => {
    listReturns();
    server.use(
      http.get(api("/api/startpage/sections/2"), () => HttpResponse.json(SECTION)),
    );
    const { user } = renderRoute("/app/cms/sections");
    await user.click(await screen.findByText("Ausbildung"));

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    await user.click(screen.getByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });

  it("closes the create modal with × and reports a refused delete", async () => {
    useMe({ permissions: ["startpage.add_section"] });
    listReturns();
    server.use(
      http.get(api("/api/startpage/sections/2"), () => HttpResponse.json(SECTION)),
      http.delete(api("/api/startpage/sections/2"), () =>
        HttpResponse.json({ detail: "startpage.delete_section" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/app/cms/sections");
    await user.click(await screen.findByRole("button", { name: "Neuer Bereich" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Ausbildung"));
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("copes with a section whose body is null", async () => {
    server.use(
      http.get(api("/api/startpage/sections/2"), () =>
        HttpResponse.json({ ...SECTION, website_text: null, show_in_navigation: false }),
      ),
    );
    const { user } = renderRoute("/app/cms/sections/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("edits and deletes a section", async () => {
    let put: Record<string, unknown> | null = null;
    let deleted = false;
    server.use(
      http.get(api("/api/startpage/sections/2"), () => HttpResponse.json(SECTION)),
      http.get(api("/api/startpage/sections"), () => HttpResponse.json([SECTION])),
      http.put(api("/api/startpage/sections/2"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(SECTION);
      }),
      http.delete(api("/api/startpage/sections/2"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/cms/sections/2");

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(put).toMatchObject({ show_in_navigation: false }));

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Bereich gelöscht.")).toBeInTheDocument();
  });
});

/* --- Posts ---------------------------------------------------------------- */

const POST_BRIEF: Record<string, unknown> = {
  id: 5,
  title: "Skifreizeit",
  urlname: "skifreizeit",
  date: "2026-02-20",
  section_title: "Berichte",
  section_urlname: "berichte",
  section_id: 2,
};

const POST = {
  id: 5,
  title: "Skifreizeit",
  urlname: "skifreizeit",
  date: "2026-02-20",
  website_text: "Wir waren oben.",
  detailed: false,
  section: { id: 2, title: "Berichte", urlname: "berichte" },
  section_id: 2,
  groups: [],
  group_ids: [],
};

describe("cms — Beiträge", () => {
  function listReturns(rows = [POST_BRIEF]) {
    server.use(
      http.get(api("/api/startpage/posts"), () => HttpResponse.json(rows)),
      http.get(api("/api/startpage/sections"), () => HttpResponse.json([SECTION])),
      http.get(api("/api/members/groups"), () =>
        HttpResponse.json([{ id: 5, name: "Klettergruppe" }]),
      ),
    );
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/startpage/posts/5"), () => HttpResponse.json({ ...POST, ...overrides })),
      http.get(api("/api/startpage/sections"), () => HttpResponse.json([SECTION])),
      http.get(api("/api/members/groups"), () =>
        HttpResponse.json([{ id: 5, name: "Klettergruppe" }]),
      ),
      http.get(api("/api/startpage/images"), () => HttpResponse.json([])),
      http.get(api("/api/startpage/member-on-posts"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([{ id: 7, name: "Hannah Beckers" }])),
    );
  }

  it("lists posts and filters them by section", async () => {
    listReturns([
      POST_BRIEF,
      { ...POST_BRIEF, id: 6, title: "Sommerfahrt", section_id: 3, section_title: "Aktuelles" },
    ]);
    const { user } = renderRoute("/app/cms/posts");
    await screen.findByText("Skifreizeit");

    // The filter's options are derived from the rows themselves, mirroring the
    // admin's list_filter.
    await user.click(screen.getByRole("button", { name: /Bereich:/ }));
    await user.click(dropdown().getByRole("button", { name: "Berichte" }));

    await waitFor(() => expect(screen.queryByText("Sommerfahrt")).not.toBeInTheDocument());
    expect(screen.getByText("Skifreizeit")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("searches by title", async () => {
    listReturns([POST_BRIEF, { ...POST_BRIEF, id: 6, title: "Sommerfahrt" }]);
    const { user } = renderRoute("/app/cms/posts");
    await screen.findByText("Skifreizeit");
    await user.type(screen.getByPlaceholderText("Suchen…"), "sommer");
    await waitFor(() => expect(screen.queryByText("Skifreizeit")).not.toBeInTheDocument());
    // The header keeps naming the unfiltered total.
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([POST_BRIEF, { ...POST_BRIEF, id: 6, title: "", date: null, section_title: null }]);
    const { user } = renderRoute("/app/cms/posts");
    await screen.findByText("Skifreizeit");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("marks a detailed post and one with no groups", async () => {
    detailReturns({ detailed: true, groups: [], group_ids: [] });
    renderRoute("/app/cms/posts/5");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getByText("Ja")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows an em dash for a post without a slug", async () => {
    listReturns([{ ...POST_BRIEF, urlname: "", section_urlname: null }]);
    renderRoute("/app/cms/posts");
    await screen.findByText("Skifreizeit");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/cms/posts");
    expect(await screen.findByText("Keine Beiträge vorhanden.")).toBeInTheDocument();
  });

  it("creates a post, sending the section and groups as ids", async () => {
    useMe({ permissions: ["startpage.add_post"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/startpage/posts"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...POST, id: 9 });
      }),
      http.get(api("/api/startpage/posts/9"), () => HttpResponse.json({ ...POST, id: 9 })),
      http.get(api("/api/startpage/images"), () => HttpResponse.json([])),
      http.get(api("/api/startpage/member-on-posts"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/cms/posts");
    await user.click(await screen.findByRole("button", { name: "Neuer Beitrag" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Titel/), "Neuer Beitrag");
    await user.type(dialog.getByLabelText(/^URL/), "neuer-beitrag");
    await user.type(dialog.getByLabelText(/^Datum/), "2026-03-01");

    // Both widgets sit inside a <label>, so their accessible name is the field
    // label rather than the trigger's own text.
    await user.click(dialog.getByRole("button", { name: "Bereich" }));
    await user.click(dropdown().getByRole("button", { name: "Ausbildung" }));

    await user.click(dialog.getByRole("button", { name: "Gruppen" }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));

    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      title: "Neuer Beitrag",
      urlname: "neuer-beitrag",
      date: "2026-03-01",
      section_id: 2,
      group_ids: [5],
      detailed: false,
    });
    expect(await screen.findByText("Beitrag angelegt.")).toBeInTheDocument();
  });

  it("shows server field errors on the create form and closes it cleanly", async () => {
    useMe({ permissions: ["startpage.add_post"] });
    listReturns();
    server.use(
      http.post(api("/api/startpage/posts"), () =>
        djangoValidation({ website_text: ["Der Text fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/cms/posts");
    await user.click(await screen.findByRole("button", { name: "Neuer Beitrag" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Titel/), "Neu");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Der Text fehlt.")).not.toHaveLength(0);

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("forgets the field errors when the create modal is closed with ×", async () => {
    useMe({ permissions: ["startpage.add_post"] });
    listReturns();
    server.use(
      http.post(api("/api/startpage/posts"), () =>
        djangoValidation({ title: ["Der Titel fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/cms/posts");
    await user.click(await screen.findByRole("button", { name: "Neuer Beitrag" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Titel/), "Neu");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    await screen.findAllByText("Der Titel fehlt.");

    await user.click(dialog.getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Neuer Beitrag" }));
    // The stale inline error is gone rather than greeting the next attempt.
    // (The toast is a separate, self-dismissing surface and may still stand.)
    const reopened = within(await screen.findByRole("dialog"));
    expect(reopened.queryByText("Der Titel fehlt.")).not.toBeInTheDocument();
  });

  it("opens a post from its row, leaves edit mode and goes back", async () => {
    listReturns();
    detailReturns();
    const { user } = renderRoute("/app/cms/posts");
    await user.click(await screen.findByText("Skifreizeit"));

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    await user.click(screen.getByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });

  it("reports a refused delete", async () => {
    detailReturns();
    server.use(
      http.delete(api("/api/startpage/posts/5"), () =>
        HttpResponse.json({ detail: "startpage.delete_post" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("closes the image and person dialogs with × and with Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    await user.click(screen.getByRole("tab", { name: "Bilder" }));
    await user.click(await screen.findByRole("button", { name: "+ Bild" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "+ Bild" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("tab", { name: "Personen" }));
    await user.click(await screen.findByRole("button", { name: "+ Person" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "+ Person" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("edits a person group's tag in the table", async () => {
    detailReturns();
    let put: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/startpage/member-on-posts"), () =>
        HttpResponse.json([{ id: 21, post_id: 5, tag: "Jugendleitung" }]),
      ),
      http.get(api("/api/startpage/member-on-posts/21"), () =>
        HttpResponse.json({
          id: 21,
          post_id: 5,
          tag: "Jugendleitung",
          description: "",
          members: [{ id: 7, name: "Hannah Beckers" }],
        }),
      ),
      http.put(api("/api/startpage/posts/5"), () => HttpResponse.json(POST)),
      http.put(api("/api/startpage/member-on-posts/21"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 21 });
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Personen" }));

    const tag = await screen.findByDisplayValue("Jugendleitung");
    await user.clear(tag);
    await user.type(tag, "Betreuung");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).toMatchObject({ tag: "Betreuung" }));
  });

  it("saves without uploading when an image row carries no file", async () => {
    detailReturns();
    let uploaded = false;
    server.use(
      http.put(api("/api/startpage/posts/5"), () => HttpResponse.json(POST)),
      http.post(api("/api/startpage/images"), () => {
        uploaded = true;
        return HttpResponse.json({ id: 11 });
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Bilder" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Bearbeiten" })).toBeInTheDocument());
    expect(uploaded).toBe(false);
  });

  it("shows every rejected field of the create form", async () => {
    useMe({ permissions: ["startpage.add_post"] });
    listReturns();
    server.use(
      http.post(api("/api/startpage/posts"), () =>
        djangoValidation({
          title: ["Titel fehlt."],
          urlname: ["Kürzel fehlt."],
          date: ["Datum ungültig."],
          section: ["Bereich unbekannt."],
          website_text: ["Text fehlt."],
          detailed: ["Ungültig."],
          groups: ["Gruppe unbekannt."],
        }),
      ),
    );
    const { user } = renderRoute("/app/cms/posts");
    await user.click(await screen.findByRole("button", { name: "Neuer Beitrag" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Titel/), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    for (const message of [
      "Titel fehlt.",
      "Kürzel fehlt.",
      "Datum ungültig.",
      "Bereich unbekannt.",
      "Text fehlt.",
      "Ungültig.",
      "Gruppe unbekannt.",
    ]) {
      expect(await screen.findAllByText(message)).not.toHaveLength(0);
    }
  });

  it("copes with a post that has no section, text or groups", async () => {
    detailReturns({
      title: "",
      website_text: "",
      detailed: false,
      section: null,
      section_id: null,
      groups: [],
      group_ids: [],
      date: null,
    });
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    // Clearing the (optional) section select sends null rather than 0.
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    expect(panel.textContent).toContain("—");
  });

  it("reports a rejected save without leaving edit mode", async () => {
    detailReturns();
    server.use(
      http.put(api("/api/startpage/posts/5"), () =>
        new HttpResponse("<html>500</html>", { status: 500 }),
      ),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();
  });

  it("shows an em dash for an image without a name and a person group without members", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/startpage/images"), () =>
        HttpResponse.json([{ id: 11, post_id: 5, name: "", f: null }]),
      ),
      http.get(api("/api/startpage/member-on-posts"), () =>
        HttpResponse.json([{ id: 21, post_id: 5, tag: "" }]),
      ),
      http.get(api("/api/startpage/member-on-posts/21"), () =>
        HttpResponse.json({ id: 21, post_id: 5, tag: null, description: null, members: [] }),
      ),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("tab", { name: "Bilder" }));
    let panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));

    await user.click(screen.getByRole("tab", { name: "Personen" }));
    panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));
  });

  it("clears a chosen image file again", async () => {
    detailReturns();
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Bilder" }));
    await user.click(await screen.findByRole("button", { name: "+ Bild" }));

    const dialog = within(await screen.findByRole("dialog"));
    const input = dialog.getByLabelText(/Bilddatei/);
    await user.upload(input, new File(["x"], "bild.png", { type: "image/png" }));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeEnabled();
    await user.upload(input, []);
    await waitFor(() =>
      expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled(),
    );
  });

  it("filters the posts down to those without a section", async () => {
    listReturns([
      POST_BRIEF,
      { ...POST_BRIEF, id: 6, title: "Ohne Bereich", section_id: null, section_title: null },
    ]);
    const { user } = renderRoute("/app/cms/posts");
    await screen.findByText("Skifreizeit");
    // The section filter's options come from the rows, so a row without one is
    // matched by the empty value rather than dropping out of the list.
    await user.click(screen.getByRole("button", { name: /Bereich:/ }));
    await user.click(dropdown().getByRole("button", { name: "Berichte" }));
    await waitFor(() => expect(screen.queryByText("Ohne Bereich")).not.toBeInTheDocument());
  });

  it("links the detail page to the public post", async () => {
    detailReturns();
    renderRoute("/app/cms/posts/5");
    expect(
      await screen.findByRole("link", { name: "/beitrag/berichte/skifreizeit" }),
    ).toHaveAttribute("href", "/beitrag/berichte/skifreizeit");
  });

  it("shows an em dash instead of a broken public link", async () => {
    detailReturns({ urlname: "", section: null });
    renderRoute("/app/cms/posts/5");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.queryByRole("link", { name: /beitrag/ })).not.toBeInTheDocument();
  });

  it("clears the date to null rather than sending an empty string", async () => {
    detailReturns();
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/startpage/posts/5"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(POST);
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.clear(screen.getByDisplayValue("2026-02-20"));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({ date: null });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("stages an image and uploads it only on save", async () => {
    detailReturns();
    let uploaded: string | undefined;
    let fields: Record<string, string> = {};
    server.use(
      http.put(api("/api/startpage/posts/5"), () => HttpResponse.json(POST)),
      http.post(api("/api/startpage/images"), async ({ request }) => {
        const clone = request.clone();
        [uploaded] = await multipartFilenames(request);
        fields = await multipartFields(clone);
        return HttpResponse.json({ id: 11, post_id: 5, name: "bild.png", f: "/media/bild.png" });
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Bilder" }));
    await user.click(await screen.findByRole("button", { name: "+ Bild" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.upload(
      dialog.getByLabelText(/Bilddatei/),
      new File(["x"], "bild.png", { type: "image/png" }),
    );
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    // Staged only.
    expect(uploaded).toBeUndefined();
    expect(screen.getByText("(neu)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(uploaded).toBe("bild.png"));
    expect(fields.post_id).toBe("5");
  });

  it("removes an existing image on save", async () => {
    detailReturns();
    let deleted = 0;
    server.use(
      http.get(api("/api/startpage/images"), () =>
        HttpResponse.json([{ id: 11, post_id: 5, name: "alt.png", f: "/media/alt.png" }]),
      ),
      http.put(api("/api/startpage/posts/5"), () => HttpResponse.json(POST)),
      http.delete(api("/api/startpage/images/11"), () => {
        deleted += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Bilder" }));

    expect(await screen.findByRole("link", { name: "Öffnen" })).toHaveAttribute(
      "href",
      "http://localhost:8000/media/alt.png",
    );
    await user.click(screen.getByRole("button", { name: "Entfernen" }));
    expect(deleted).toBe(0);

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(1));
  });

  it("adds a person group, requiring at least one member", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/startpage/posts/5"), () => HttpResponse.json(POST)),
      http.post(api("/api/startpage/member-on-posts"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 21 });
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Personen" }));
    await user.click(await screen.findByRole("button", { name: "+ Person" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();

    await user.click(dialog.getByRole("button", { name: "Teilnehmende" }));
    await user.click(dropdown().getByRole("button", { name: "Hannah Beckers" }));
    await user.type(dialog.getByLabelText("Beschreibung"), "Hat geleitet.");
    await user.type(dialog.getByLabelText(/^Tag/), "Jugendleitung");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(created).not.toBeNull());
    expect(created).toEqual({
      post_id: 5,
      member_ids: [7],
      description: "Hat geleitet.",
      tag: "Jugendleitung",
    });
  });

  it("edits an existing person group in place", async () => {
    detailReturns();
    let put: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/startpage/member-on-posts"), () =>
        HttpResponse.json([{ id: 21, post_id: 5, tag: "Jugendleitung" }]),
      ),
      http.get(api("/api/startpage/member-on-posts/21"), () =>
        HttpResponse.json({
          id: 21,
          post_id: 5,
          tag: "Jugendleitung",
          description: "Alt",
          members: [{ id: 7, name: "Hannah Beckers" }],
        }),
      ),
      http.put(api("/api/startpage/posts/5"), () => HttpResponse.json(POST)),
      http.put(api("/api/startpage/member-on-posts/21"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 21 });
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Personen" }));

    const description = await screen.findByDisplayValue("Alt");
    await user.clear(description);
    await user.type(description, "Neu");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({ description: "Neu", member_ids: [7] });
  });

  it("removes a person group on save", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/startpage/member-on-posts"), () =>
        HttpResponse.json([{ id: 21, post_id: 5, tag: "Jugendleitung" }]),
      ),
      http.get(api("/api/startpage/member-on-posts/21"), () =>
        HttpResponse.json({
          id: 21,
          post_id: 5,
          tag: "Jugendleitung",
          description: "Alt",
          members: [{ id: 7, name: "Hannah Beckers" }],
        }),
      ),
      http.put(api("/api/startpage/posts/5"), () => HttpResponse.json(POST)),
      http.delete(api("/api/startpage/member-on-posts/21"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Personen" }));
    // The row's own remove button, not the badge remove inside its MultiSelect.
    const removeCell = (await screen.findAllByRole("row"))
      .map((r) => r.querySelector("td.inline-actions button"))
      .find(Boolean) as HTMLElement;
    await user.click(removeCell);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(deleted).toBe(true));
  });

  it("shows the read-only person summary outside edit mode", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/startpage/member-on-posts"), () =>
        HttpResponse.json([{ id: 21, post_id: 5, tag: "" }]),
      ),
      http.get(api("/api/startpage/member-on-posts/21"), () =>
        HttpResponse.json({
          id: 21,
          post_id: 5,
          tag: null,
          description: null,
          members: [{ id: 9, name: "Tobias Werner" }],
        }),
      ),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("tab", { name: "Personen" }));

    expect(await screen.findByText("Tobias Werner")).toBeInTheDocument();
    // Empty description and tag read as an em dash, not as blank cells.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("deletes a post once confirmed", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/startpage/posts"), () => HttpResponse.json([])),
      http.delete(api("/api/startpage/posts/5"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Beitrag gelöscht.")).toBeInTheDocument();
  });

  it("reports a rejected save with the field named", async () => {
    detailReturns();
    server.use(
      http.put(api("/api/startpage/posts/5"), () =>
        djangoValidation({ urlname: ["Dieses Kürzel ist vergeben."] }),
      ),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Dieses Kürzel ist vergeben.")).not.toHaveLength(0);
  });
});

/* --- exhaustive field passes ---------------------------------------------- */

describe("cms — every field", () => {
  it("Beitrag: carries every edited field into the PUT", async () => {
    server.use(
      http.get(api("/api/startpage/posts/5"), () => HttpResponse.json(POST)),
      http.get(api("/api/startpage/sections"), () => HttpResponse.json([SECTION])),
      http.get(api("/api/members/groups"), () =>
        HttpResponse.json([{ id: 5, name: "Klettergruppe" }]),
      ),
      http.get(api("/api/startpage/images"), () => HttpResponse.json([])),
      http.get(api("/api/startpage/member-on-posts"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([{ id: 7, name: "Hannah Beckers" }])),
    );
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/startpage/posts/5"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(POST);
      }),
    );
    const { user } = renderRoute("/app/cms/posts/5");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await fillEveryField(user, panel);
    await pickEverySelect(user, panel);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({
      title: "Text",
      urlname: "Text",
      website_text: "Text",
      date: "2026-03-04",
      detailed: true,
      // The optional section select clears on its first option.
      section_id: null,
      group_ids: [5],
    });
  });

  it("Bereich: carries every edited field into the PUT", async () => {
    server.use(
      http.get(api("/api/startpage/sections/2"), () => HttpResponse.json(SECTION)),
    );
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/startpage/sections/2"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(SECTION);
      }),
    );
    const { user } = renderRoute("/app/cms/sections/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await fillEveryField(user, document.querySelector("form") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toEqual({
      title: "Text",
      urlname: "Text",
      website_text: "Text",
      show_in_navigation: false,
    });
  });

  it("Link: carries every edited field into the PUT", async () => {
    server.use(http.get(api("/api/startpage/links/3"), () => HttpResponse.json(LINK)));
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/startpage/links/3"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(LINK);
      }),
    );
    const { user } = renderRoute("/app/cms/links/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    // The icon field is a file input, which fillEveryField deliberately skips.
    await fillEveryField(user, document.querySelector("form") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toEqual({
      title: "Text",
      url: "Text",
      description: "Text",
      visible: false,
    });
  });

  it("FAQ: carries every edited field into the PUT", async () => {
    server.use(http.get(api("/api/startpage/faqs/1"), () => HttpResponse.json(FAQ)));
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/startpage/faqs/1"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(FAQ);
      }),
    );
    const { user } = renderRoute("/app/cms/faqs/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await fillEveryField(user, document.querySelector("form") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).toEqual({ question: "Text", answer: "Text" }));
  });

  it("fills every field of each create form", async () => {
    useMe({
      permissions: [
        "startpage.add_post",
        "startpage.add_section",
        "startpage.add_link",
        "startpage.add_faq",
      ],
    });
    server.use(
      http.get(api("/api/startpage/posts"), () => HttpResponse.json([])),
      http.get(api("/api/startpage/sections"), () => HttpResponse.json([SECTION])),
      http.get(api("/api/members/groups"), () =>
        HttpResponse.json([{ id: 5, name: "Klettergruppe" }]),
      ),
    );
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.post(api("/api/startpage/posts"), async ({ request }) => {
        bodies.push((await request.json()) as Record<string, unknown>);
        return djangoValidation({ title: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/cms/posts");
    await user.click(await screen.findByRole("button", { name: "Neuer Beitrag" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      title: "Text",
      urlname: "Text",
      website_text: "Text",
      date: "2026-03-04",
      detailed: true,
      group_ids: [5],
    });
  });
});
