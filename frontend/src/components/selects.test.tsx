import { screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { api, http, HttpResponse, server } from "../test/server";
import { renderWithApp } from "../test/utils";
import { InlineTable } from "./inline";
import { DownloadButton, MultiSelect, SearchableSelect, Select } from "./ui";

const OPTIONS = [
  { value: 1, label: "Klettergruppe" },
  { value: 2, label: "Jugendleiter" },
  { value: 3, label: "Bouldergruppe" },
];

/** The dropdown panel these three widgets share. */
const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

describe("MultiSelect", () => {
  function Harness({ initial = [] as number[] }) {
    const [selected, setSelected] = useState(initial);
    return (
      <>
        <span data-testid="value">{selected.join(",")}</span>
        <MultiSelect options={OPTIONS} selected={selected} onChange={setSelected} />
      </>
    );
  }

  it("adds and removes values through the dropdown", async () => {
    const { user } = renderWithApp(<Harness />, { authenticated: false });

    await user.click(screen.getByRole("button", { name: "+ Auswählen…" }));
    await user.click(dropdown().getByRole("button", { name: "Jugendleiter" }));
    expect(screen.getByTestId("value")).toHaveTextContent("2");

    // The dropdown stays open for a second pick, and a selected entry is ticked
    // and toggles back off.
    expect(dropdown().getByRole("button", { name: /Jugendleiter/ }).textContent).toContain("✓");
    await user.click(dropdown().getByRole("button", { name: /Jugendleiter/ }));
    expect(screen.getByTestId("value")).toHaveTextContent("");
  });

  it("removes a value from its badge", async () => {
    const { user } = renderWithApp(<Harness initial={[1, 2]} />, { authenticated: false });
    const badge = screen.getByText("Klettergruppe").closest(".ms-badge") as HTMLElement;
    await user.click(within(badge).getByRole("button"));
    expect(screen.getByTestId("value")).toHaveTextContent("2");
  });

  it("shows the raw id for a value the options no longer contain", () => {
    renderWithApp(
      <MultiSelect options={OPTIONS} selected={[99]} onChange={vi.fn()} />,
      { authenticated: false },
    );
    // A group the user may not see is still shown as selected, not dropped.
    expect(screen.getByText("99")).toBeInTheDocument();
  });

  it("filters the options and says so when nothing matches", async () => {
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: "+ Auswählen…" }));

    await user.type(dropdown().getByPlaceholderText("Suchen…"), "boulder");
    expect(dropdown().getByRole("button", { name: "Bouldergruppe" })).toBeInTheDocument();
    expect(dropdown().queryByRole("button", { name: "Jugendleiter" })).not.toBeInTheDocument();

    await user.clear(dropdown().getByPlaceholderText("Suchen…"));
    await user.type(dropdown().getByPlaceholderText("Suchen…"), "gibtesnicht");
    expect(dropdown().getByText("Keine Einträge.")).toBeInTheDocument();
  });

  it("closes on a click outside", async () => {
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: "+ Auswählen…" }));
    expect(document.querySelector(".ms-dropdown")).toBeInTheDocument();
    await user.click(document.body);
    await waitFor(() => expect(document.querySelector(".ms-dropdown")).toBeNull());
  });
});

describe("SearchableSelect (list filter)", () => {
  function Harness() {
    const [value, setValue] = useState("");
    return (
      <>
        <span data-testid="value">{value}</span>
        <SearchableSelect
          label="Gruppe"
          value={value}
          onChange={setValue}
          options={OPTIONS.map((o) => ({ value: String(o.value), label: o.label }))}
        />
      </>
    );
  }

  it("reads 'alle' until something is picked", async () => {
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    const trigger = screen.getByRole("button", { name: /Gruppe:/ });
    expect(trigger).toHaveTextContent("alle");
    expect(trigger).not.toHaveClass("active");

    await user.click(trigger);
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    expect(screen.getByTestId("value")).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: /Gruppe:/ })).toHaveClass("active");
  });

  it("clears back to 'alle' through the first option", async () => {
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: /Gruppe:/ }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));

    await user.click(screen.getByRole("button", { name: /Gruppe:/ }));
    await user.click(dropdown().getByRole("button", { name: /alle/ }));
    expect(screen.getByTestId("value")).toHaveTextContent("");
  });

  it("forgets the search term when the dropdown is reopened", async () => {
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: /Gruppe:/ }));
    await user.type(dropdown().getByPlaceholderText("Suchen…"), "boulder");
    await user.click(dropdown().getByRole("button", { name: "Bouldergruppe" }));

    await user.click(screen.getByRole("button", { name: /Gruppe:/ }));
    expect(dropdown().getByPlaceholderText("Suchen…")).toHaveValue("");
    expect(dropdown().getByRole("button", { name: /Jugendleiter/ })).toBeInTheDocument();
  });
});

describe("Select (form single-select)", () => {
  function Harness({ allowEmpty = false }) {
    const [value, setValue] = useState("");
    return (
      <>
        <span data-testid="value">{value}</span>
        <Select
          value={value}
          onChange={setValue}
          options={OPTIONS}
          placeholder="— keine —"
          allowEmpty={allowEmpty}
          emptyLabel="— keine —"
        />
      </>
    );
  }

  it("shows the placeholder until a value is picked", async () => {
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    expect(screen.getByRole("button", { name: /— keine —/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /— keine —/ }));
    await user.click(dropdown().getByRole("button", { name: "Jugendleiter" }));

    // Numeric option values are handed back as strings, like a native <select>.
    expect(screen.getByTestId("value")).toHaveTextContent("2");
    expect(screen.getByRole("button", { name: /Jugendleiter/ })).toBeInTheDocument();
  });

  it("offers a clear option only when allowEmpty is set", async () => {
    const plain = renderWithApp(<Harness />, { authenticated: false });
    await plain.user.click(screen.getByRole("button", { name: /— keine —/ }));
    expect(dropdown().getAllByRole("button")).toHaveLength(OPTIONS.length);
    plain.unmount();

    const { user } = renderWithApp(<Harness allowEmpty />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: /— keine —/ }));
    await user.click(dropdown().getAllByRole("button")[0]);
    expect(screen.getByTestId("value")).toHaveTextContent("");
  });

  it("filters its options too", async () => {
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: /— keine —/ }));
    await user.type(dropdown().getByPlaceholderText("Suchen…"), "jugend");
    expect(dropdown().getAllByRole("button")).toHaveLength(1);
  });
});

describe("InlineTable", () => {
  const rows = [{ id: 1, name: "Erika" }];
  const columns = [{ header: "Name", cell: (r: (typeof rows)[number]) => r.name }];

  it("lists rows read-only until the parent is in edit mode", () => {
    renderWithApp(
      <InlineTable
        title="Notfallkontakte"
        rows={rows}
        columns={columns}
        rowKey={(r) => r.id}
        editing={false}
        onDelete={vi.fn()}
        onAdd={vi.fn()}
      />,
      { authenticated: false },
    );
    expect(screen.getByRole("heading", { name: "Notfallkontakte" })).toBeInTheDocument();
    expect(screen.getByText("Erika")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Entfernen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Hinzufügen/ })).not.toBeInTheDocument();
  });

  it("shows the add and remove actions while editing", async () => {
    const onDelete = vi.fn();
    const onAdd = vi.fn();
    const { user } = renderWithApp(
      <InlineTable
        title="Notfallkontakte"
        rows={rows}
        columns={columns}
        rowKey={(r) => r.id}
        editing
        onDelete={onDelete}
        onAdd={onAdd}
        addLabel="Notfallkontakt"
      />,
      { authenticated: false },
    );
    await user.click(screen.getByRole("button", { name: "+ Notfallkontakt" }));
    expect(onAdd).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Entfernen" }));
    expect(onDelete).toHaveBeenCalledWith(rows[0]);
  });

  it("renders the legacy inline add area below the table", () => {
    renderWithApp(
      <InlineTable
        title="Belege"
        rows={rows}
        columns={columns}
        rowKey={(r) => r.id}
        editing
        renderAdd={() => <p>Neuer Beleg</p>}
      />,
      { authenticated: false },
    );
    expect(screen.getByText("Neuer Beleg")).toBeInTheDocument();
    // No onDelete → no actions column at all.
    expect(screen.queryByRole("button", { name: "Entfernen" })).not.toBeInTheDocument();
  });

  it("shows its own empty text instead of a header-only table", () => {
    renderWithApp(
      <InlineTable
        title="Ausbildungen"
        rows={[]}
        columns={columns}
        rowKey={(r: { id: number }) => r.id}
        editing={false}
        empty="Keine Ausbildungen erfasst."
      />,
      { authenticated: false },
    );
    expect(screen.getByText("Keine Ausbildungen erfasst.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("DownloadButton", () => {
  it("reports a failed download as a toast rather than silently doing nothing", async () => {
    server.use(
      http.get(api("/api/members/documents/groups/5/checklist"), () =>
        HttpResponse.json({ detail: "members.view_group" }, { status: 403 }),
      ),
    );
    const { user } = renderWithApp(
      <DownloadButton path="/api/members/documents/groups/5/checklist">
        Checkliste (pdf)
      </DownloadButton>,
    );

    await user.click(screen.getByRole("button", { name: "Checkliste (pdf)" }));
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
    // The button becomes usable again once the attempt is over.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Checkliste (pdf)" })).toBeEnabled(),
    );
  });

  it("posts the body it was given for a generated document", async () => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: () => "blob:x",
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: () => {},
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    let body: unknown = null;
    server.use(
      http.post(api("/api/members/documents/members/list"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    const { user } = renderWithApp(
      <DownloadButton
        path="/api/members/documents/members/list"
        method="POST"
        body={{ ids: [1] }}
        filename="Liste.pdf"
      >
        Liste (pdf)
      </DownloadButton>,
    );

    await user.click(screen.getByRole("button", { name: "Liste (pdf)" }));
    await waitFor(() => expect(body).toEqual({ ids: [1] }));
  });
});
