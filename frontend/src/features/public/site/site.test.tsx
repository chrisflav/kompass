import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, http, HttpResponse, server } from "../../../test/server";
import { renderRoute, renderWithApp } from "../../../test/utils";
import { PublicFaq } from "./Faq";
import { PublicGruppeDetail } from "./GruppeDetail";
import { PublicGruppen } from "./Gruppen";
import { PublicImpressum } from "./Impressum";
import { PublicIndex } from "./Index";
import { PublicPost } from "./Post";
import { PublicSection } from "./Section";
import { PublicAktuelles, PublicBerichte } from "./SectionPosts";
import { excerpt, formatDate, Prose, PostTeaser } from "./shared";

const POST = {
  id: 1,
  title: "Skifreizeit 2026",
  urlname: "skifreizeit-2026",
  section_urlname: "berichte",
  date: "2026-02-20",
  detailed: false,
  website_text: "Wir waren **oben**. [Bericht](https://example.org) mit ![Bild](x.png)",
};

const anon = { authenticated: false } as const;

describe("shared helpers", () => {
  it("formats an ISO date in long German form", () => {
    expect(formatDate("2026-02-20")).toBe("20. Februar 2026");
  });

  it("returns an empty string for no date and passes junk through", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate(undefined)).toBe("");
    expect(formatDate("irgendwann")).toBe("irgendwann");
  });

  it("strips Markdown down to a readable teaser", () => {
    expect(excerpt("# Titel\n\nEin *toller* [Link](https://x) und ![Bild](y.png).")).toBe(
      "Titel Ein toller Link und .",
    );
  });

  it("returns an empty teaser for missing text", () => {
    expect(excerpt(null)).toBe("");
    expect(excerpt(undefined)).toBe("");
    expect(excerpt("")).toBe("");
  });

  it("cuts a long teaser at a word boundary", () => {
    const text = `${"wort ".repeat(100)}ende`;
    const short = excerpt(text, 40);
    expect(short.endsWith("…")).toBe(true);
    expect(short.length).toBeLessThanOrEqual(41);
    // Never cuts mid-word.
    expect(short.slice(0, -1).endsWith(" ")).toBe(false);
    expect(short).toMatch(/wort…$/);
  });

  it("cuts hard when the text has no space to break at", () => {
    expect(excerpt("a".repeat(50), 10)).toBe(`${"a".repeat(10)}…`);
  });

  it("renders Markdown as rich text and nothing at all when empty", () => {
    const { container } = renderWithApp(<Prose text="Ein **fetter** Absatz." />, anon);
    expect(container.querySelector("strong")).toHaveTextContent("fetter");

    const empty = renderWithApp(<Prose text={null} />, anon);
    expect(empty.container.querySelector(".prose")).toBeNull();
  });

  it("links a teaser to its post via section and post urlname", () => {
    renderWithApp(<PostTeaser post={POST} />, anon);
    expect(screen.getByRole("link", { name: /Skifreizeit 2026/ })).toHaveAttribute(
      "href",
      "/beitrag/berichte/skifreizeit-2026",
    );
    expect(screen.getByText("20. Februar 2026")).toBeInTheDocument();
  });

  it("omits the date line for a post without one", () => {
    renderWithApp(<PostTeaser post={{ ...POST, date: null }} />, anon);
    expect(screen.queryByText(/Februar/)).not.toBeInTheDocument();
  });
});

describe("public index", () => {
  it("shows the hero plus the newest posts and reports", async () => {
    server.use(
      http.get(api("/api/startpage/public/index"), () =>
        HttpResponse.json({
          recent_posts: [POST],
          reports: [{ ...POST, id: 2, title: "Sommerfahrt", urlname: "sommerfahrt" }],
        }),
      ),
    );
    renderWithApp(<PublicIndex />, anon);

    expect(screen.getByRole("heading", { name: "JDAV Ludwigsburg" })).toBeInTheDocument();
    expect(await screen.findByText("Skifreizeit 2026")).toBeInTheDocument();
    expect(screen.getByText("Sommerfahrt")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alle Neuigkeiten →" })).toHaveAttribute(
      "href",
      "/aktuelles",
    );
    expect(screen.getByRole("link", { name: "Alle Berichte →" })).toHaveAttribute(
      "href",
      "/berichte",
    );
  });

  it("says both sections are empty rather than showing bare headings", async () => {
    server.use(
      http.get(api("/api/startpage/public/index"), () =>
        HttpResponse.json({ recent_posts: [], reports: [] }),
      ),
    );
    renderWithApp(<PublicIndex />, anon);
    expect(await screen.findByText("Keine aktuellen Beiträge.")).toBeInTheDocument();
    expect(screen.getByText("Keine Berichte.")).toBeInTheDocument();
  });
});

describe("section listings", () => {
  it("titles Aktuelles from the section itself", async () => {
    server.use(
      http.get(api("/api/startpage/public/aktuelles"), () =>
        HttpResponse.json({
          section: { title: "Neues aus der Jugend", website_text: "Einleitung *hier*." },
          posts: [POST],
        }),
      ),
    );
    renderWithApp(<PublicAktuelles />, anon);

    expect(await screen.findByRole("heading", { name: "Neues aus der Jugend" })).toBeInTheDocument();
    // The intro is rendered as Markdown, so the emphasis is its own element.
    expect(screen.getByText("hier", { selector: "em" })).toBeInTheDocument();
    expect(screen.getByText("Skifreizeit 2026")).toBeInTheDocument();
    expect(document.title).toBe("Neues aus der Jugend · Kompass");
  });

  it("falls back to the built-in title when the section has none", async () => {
    server.use(
      http.get(api("/api/startpage/public/berichte"), () =>
        HttpResponse.json({ section: { title: "", website_text: null }, posts: [] }),
      ),
    );
    renderWithApp(<PublicBerichte />, anon);
    expect(await screen.findByRole("heading", { name: "Berichte" })).toBeInTheDocument();
    expect(screen.getByText("Keine Beiträge vorhanden.")).toBeInTheDocument();
  });
});

describe("Gruppen", () => {
  it("lists the public groups and opens one", async () => {
    server.use(
      http.get(api("/api/startpage/public/groups"), () =>
        HttpResponse.json([{ id: 5, name: "Klettergruppe" }]),
      ),
      http.get(api("/api/startpage/public/groups/Klettergruppe"), () =>
        HttpResponse.json({
          id: 5,
          name: "Klettergruppe",
          description: "",
          age_info: "",
          has_age_info: false,
          show_website_year: false,
          show_website_weekday: false,
          show_website_time: false,
          show_website_contact_email: false,
          weekday_display: null,
          time_slot: null,
          contact_email: null,
          has_registration_password: false,
          people: [],
        }),
      ),
    );
    server.use(
      http.get(api("/api/startpage/public/navigation"), () =>
        HttpResponse.json({ root_section: null, sections: [], groups: [] }),
      ),
    );
    // Through the real route tree, so the card actually navigates.
    const { user } = renderRoute("/gruppen", { authenticated: false });

    await user.click(await screen.findByRole("button", { name: "Klettergruppe" }));
    expect(await screen.findByRole("heading", { name: "Klettergruppe" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Alle Gruppen" })).toBeInTheDocument();
  });

  it("says so when no group is published", async () => {
    server.use(http.get(api("/api/startpage/public/groups"), () => HttpResponse.json([])));
    renderWithApp(<PublicGruppen />, anon);
    expect(
      await screen.findByText("Zurzeit sind keine Gruppen öffentlich gelistet."),
    ).toBeInTheDocument();
  });
});

describe("Gruppe detail", () => {
  const GROUP = {
    id: 5,
    name: "Klettergruppe",
    description: "Wir klettern **viel**.",
    age_info: "Jahrgang 2010–2013",
    has_age_info: true,
    show_website_year: true,
    show_website_weekday: true,
    show_website_time: true,
    show_website_contact_email: true,
    weekday_display: "Montag",
    time_slot: "18:00–20:00",
    contact_email: "kletter@example.org",
    has_registration_password: true,
    people: [
      { id: 7, name: "Hannah Beckers", image: "/media/hannah.jpg" },
      { id: 8, name: "Tobias Werner", image: null },
    ],
  };

  function groupReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/startpage/public/groups/Klettergruppe"), () =>
        HttpResponse.json({ ...GROUP, ...overrides }),
      ),
    );
  }

  it("shows every detail the group opted into publishing", async () => {
    groupReturns();
    renderWithApp(<PublicGruppeDetail />, {
      ...anon,
      route: "/gruppe/Klettergruppe",
      path: "/gruppe/:name",
    });

    expect(await screen.findByRole("heading", { name: "Klettergruppe" })).toBeInTheDocument();
    expect(screen.getByText("Jahrgang 2010–2013")).toBeInTheDocument();
    expect(screen.getByText("Montag")).toBeInTheDocument();
    expect(screen.getByText("18:00–20:00")).toBeInTheDocument();
    expect(screen.getByText("kletter@example.org")).toBeInTheDocument();
    expect(screen.getByText(/Anmeldung mit Passwort möglich/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Hannah Beckers" })).toBeInTheDocument();
    // A leader without a photo is still listed, just without an image.
    expect(screen.getByText("Tobias Werner")).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(1);
  });

  it("publishes nothing the group kept private", async () => {
    groupReturns({
      show_website_year: false,
      show_website_weekday: false,
      show_website_time: false,
      show_website_contact_email: false,
      has_registration_password: false,
      people: [],
    });
    renderWithApp(<PublicGruppeDetail />, {
      ...anon,
      route: "/gruppe/Klettergruppe",
      path: "/gruppe/:name",
    });

    await screen.findByRole("heading", { name: "Klettergruppe" });
    expect(screen.queryByText("Jahrgang 2010–2013")).not.toBeInTheDocument();
    expect(screen.queryByText("kletter@example.org")).not.toBeInTheDocument();
    expect(screen.queryByText(/Anmeldung mit Passwort/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Jugendleiter:innen" })).not.toBeInTheDocument();
  });

  it("offers the way back to the group list", async () => {
    groupReturns();
    renderWithApp(<PublicGruppeDetail />, {
      ...anon,
      route: "/gruppe/Klettergruppe",
      path: "/gruppe/:name",
    });
    expect(screen.getByRole("link", { name: "← Alle Gruppen" })).toHaveAttribute(
      "href",
      "/gruppen",
    );
  });
});

describe("FAQ", () => {
  it("lists question and answer pairs", async () => {
    server.use(
      http.get(api("/api/startpage/public/faqs"), () =>
        HttpResponse.json([
          { id: 1, question: "Was kostet das?", answer: "Der Beitrag ist **frei**." },
        ]),
      ),
    );
    renderWithApp(<PublicFaq />, anon);
    expect(await screen.findByRole("heading", { name: "Was kostet das?" })).toBeInTheDocument();
    expect(screen.getByText("frei")).toBeInTheDocument();
  });

  it("says so when nothing is answered yet", async () => {
    server.use(http.get(api("/api/startpage/public/faqs"), () => HttpResponse.json([])));
    renderWithApp(<PublicFaq />, anon);
    expect(
      await screen.findByText("Es sind noch keine Fragen hinterlegt."),
    ).toBeInTheDocument();
  });
});

describe("Impressum", () => {
  it("renders the static imprint", () => {
    renderWithApp(<PublicImpressum />, anon);
    expect(screen.getByRole("heading", { name: "Impressum" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Angaben gemäß § 5 TMG" })).toBeInTheDocument();
    expect(document.title).toBe("Impressum · Kompass");
  });
});

describe("custom section page", () => {
  it("renders the section's own title and body", async () => {
    server.use(
      http.get(api("/api/startpage/public/sections/ausbildung"), () =>
        HttpResponse.json({ title: "Ausbildung", website_text: "Werde *Jugendleiter*." }),
      ),
    );
    renderWithApp(<PublicSection />, {
      ...anon,
      route: "/bereich/ausbildung",
      path: "/bereich/:section",
    });
    expect(await screen.findByRole("heading", { name: "Ausbildung" })).toBeInTheDocument();
    expect(screen.getByText("Jugendleiter")).toBeInTheDocument();
  });
});

describe("post detail", () => {
  const DETAIL = {
    id: 1,
    title: "Skifreizeit 2026",
    date: "2026-02-20",
    website_text: "Wir waren **oben**.",
    people_on_post: [
      {
        id: 10,
        tag: "Jugendleitung",
        description: "Hat die Fahrt geleitet.",
        members: [{ id: 7, name: "Hannah Beckers", image: "/media/hannah.jpg" }],
      },
      { id: 11, tag: "", description: null, members: [{ id: 8, name: "Tobias", image: null }] },
    ],
    people: [{ id: 9, name: "Anna Ärmel", image: null }],
  };

  function postReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(
        api("/api/startpage/public/sections/berichte/posts/skifreizeit-2026"),
        () => HttpResponse.json({ ...DETAIL, ...overrides }),
      ),
    );
  }

  const route = {
    ...anon,
    route: "/beitrag/berichte/skifreizeit-2026",
    path: "/beitrag/:section/:post",
  };

  it("shows the post with its date, body and the people on it", async () => {
    postReturns();
    renderWithApp(<PublicPost />, route);

    expect(await screen.findByRole("heading", { name: "Skifreizeit 2026" })).toBeInTheDocument();
    expect(screen.getByText("20. Februar 2026")).toBeInTheDocument();
    expect(screen.getByText("oben")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Jugendleitung" })).toBeInTheDocument();
    expect(screen.getByText("Hat die Fahrt geleitet.")).toBeInTheDocument();
    // A group without a tag gets a neutral heading rather than an empty one.
    expect(screen.getByRole("heading", { name: "Beteiligte" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Gruppenmitglieder" })).toBeInTheDocument();
  });

  it("omits the date line and the member section when there are none", async () => {
    postReturns({ date: null, people: [], people_on_post: [] });
    renderWithApp(<PublicPost />, route);

    await screen.findByRole("heading", { name: "Skifreizeit 2026" });
    expect(screen.queryByText(/Februar/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Gruppenmitglieder" })).not.toBeInTheDocument();
  });
});
