import { render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { renderWithApp } from "../test/utils";
import {
  Breadcrumbs,
  DataTable,
  DetailList,
  DownloadButton,
  EditableDetail,
  ErrorState,
  QueryBoundary,
  Select,
  Tabs,
  useConfirmDialog,
  useDocumentTitle,
  useToast,
} from "./ui";

describe("ErrorState", () => {
  it("falls back to a generic message for something that is not an Error", () => {
    // A query can reject with a string; the screen must not print "undefined".
    renderWithApp(<ErrorState error="kaputt" />, { authenticated: false });
    expect(screen.getByRole("alert")).toHaveTextContent("Ein Fehler ist aufgetreten.");
  });

  it("shows a real Error's own message", () => {
    renderWithApp(<ErrorState error={new Error("Nicht erreichbar")} />, { authenticated: false });
    expect(screen.getByRole("alert")).toHaveTextContent("Nicht erreichbar");
  });
});

describe("QueryBoundary", () => {
  const base = { isLoading: false, error: null };

  it("shows the spinner while loading", () => {
    renderWithApp(
      <QueryBoundary query={{ ...base, isLoading: true }}>{() => <p>nie</p>}</QueryBoundary>,
      { authenticated: false },
    );
    expect(screen.getByRole("status")).toHaveTextContent("Lädt…");
  });

  it("treats a settled query with no data as an error, not as empty", () => {
    // Otherwise the page would render its children against `undefined`.
    renderWithApp(
      <QueryBoundary query={{ ...base, data: undefined }}>{() => <p>nie</p>}</QueryBoundary>,
      { authenticated: false },
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Keine Daten.");
    expect(screen.queryByText("nie")).not.toBeInTheDocument();
  });

  it("shows the caller's empty text for an empty list", () => {
    renderWithApp(
      <QueryBoundary query={{ ...base, data: [] }} empty="Nichts da.">
        {() => <p>nie</p>}
      </QueryBoundary>,
      { authenticated: false },
    );
    expect(screen.getByText("Nichts da.")).toBeInTheDocument();
  });

  it("renders the children for a non-empty result", () => {
    renderWithApp(
      <QueryBoundary query={{ ...base, data: [1] }} empty="Nichts da.">
        {(rows: number[]) => <p>{rows.length} Zeile</p>}
      </QueryBoundary>,
      { authenticated: false },
    );
    expect(screen.getByText("1 Zeile")).toBeInTheDocument();
  });
});

describe("DataTable column widths", () => {
  it("applies an explicit column width", () => {
    renderWithApp(
      <DataTable
        rows={[{ id: 1 }]}
        rowKey={(r) => r.id}
        columns={[
          { header: "Schmal", cell: () => "x", width: "6rem" },
          { header: "Rest", cell: () => "y" },
        ]}
      />,
      { authenticated: false },
    );
    expect(screen.getByRole("columnheader", { name: "Schmal" })).toHaveStyle({ width: "6rem" });
    expect(screen.getByRole("columnheader", { name: "Rest" })).not.toHaveAttribute("style");
  });
});

describe("Tabs", () => {
  it("renders nothing selectable when given no tabs", () => {
    renderWithApp(<Tabs tabs={[]} />, { authenticated: false });
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });

  it("falls back to the first tab when the active one disappears", async () => {
    function Harness() {
      const [many, setMany] = useState(true);
      return (
        <>
          <button type="button" onClick={() => setMany(false)}>
            Kürzen
          </button>
          <Tabs
            tabs={
              many
                ? [
                    { id: "a", label: "A", content: <p>Inhalt A</p> },
                    { id: "b", label: "B", content: <p>Inhalt B</p> },
                  ]
                : [{ id: "b", label: "B", content: <p>Inhalt B</p> }]
            }
          />
        </>
      );
    }
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    expect(screen.getByRole("tab", { name: "A" })).toHaveAttribute("aria-selected", "true");

    await user.click(screen.getByRole("button", { name: "Kürzen" }));
    expect(screen.getByRole("tab", { name: "B" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("detail lists", () => {
  it("renders an em dash for a missing value", () => {
    renderWithApp(<DetailList items={[["Ort", null]]} />, { authenticated: false });
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders an em dash for a missing editable value too", () => {
    renderWithApp(
      <EditableDetail rows={[{ label: "Ort", value: null }]} editing={false} />,
      { authenticated: false },
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows a field hint only while that field is being edited", () => {
    const rows = [
      { label: "Ort", value: "Ludwigsburg", field: "town", edit: <input />, hint: "Wohnort" },
    ];
    const read = renderWithApp(<EditableDetail rows={rows} editing={false} />, {
      authenticated: false,
    });
    expect(screen.queryByText("Wohnort")).not.toBeInTheDocument();
    read.unmount();

    renderWithApp(<EditableDetail rows={rows} editing />, { authenticated: false });
    expect(screen.getByText("Wohnort")).toBeInTheDocument();
  });
});

describe("useDocumentTitle", () => {
  function Harness({ title }: { title?: string }) {
    useDocumentTitle(title);
    return null;
  }

  it("suffixes the page name with the product name", () => {
    renderWithApp(<Harness title="Teilnehmende" />, { authenticated: false });
    expect(document.title).toBe("Teilnehmende · Kompass");
  });

  it("falls back to the bare product name", () => {
    renderWithApp(<Harness />, { authenticated: false });
    expect(document.title).toBe("Kompass");
  });
});

describe("Breadcrumbs", () => {
  it("renders a middle crumb without a link as plain text", () => {
    renderWithApp(
      <Breadcrumbs
        items={[
          { label: "Ausfahrten", to: "/kompass/excursions" },
          { label: "Archiv" },
          { label: "F26-01" },
        ]}
      />,
      { authenticated: false },
    );
    expect(screen.getByRole("link", { name: "Ausfahrten" })).toBeInTheDocument();
    // Only the last crumb is marked as the current page.
    expect(screen.getByText("Archiv")).not.toHaveClass("crumb-current");
    expect(screen.getByText("F26-01")).toHaveClass("crumb-current");
    expect(screen.getAllByText("/")).toHaveLength(2);
  });
});

describe("Select with a preselected value", () => {
  it("ticks the current option and offers the clear entry untick", async () => {
    function Harness() {
      const [value, setValue] = useState("2");
      return (
        <Select
          value={value}
          onChange={setValue}
          options={[
            { value: 1, label: "Eins" },
            { value: 2, label: "Zwei" },
          ]}
          allowEmpty
          emptyLabel="— keine —"
        />
      );
    }
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: /Zwei/ }));

    const opts = document.querySelectorAll(".ms-opt");
    // The clear entry is present but not selected; "Zwei" is.
    expect(opts[0].className).toBe("ms-opt");
    expect(opts[2].className).toBe("ms-opt selected");
    expect(opts[2].textContent).toContain("✓");
  });
});

describe("provider guards", () => {
  it("useConfirmDialog refuses to run outside its provider", () => {
    function Bad() {
      useConfirmDialog();
      return null;
    }
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Bad />)).toThrow(/ConfirmProvider/);
    quiet.mockRestore();
  });

  it("useToast refuses to run outside its provider", () => {
    function Bad() {
      useToast();
      return null;
    }
    const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Bad />)).toThrow(/ToastProvider/);
    quiet.mockRestore();
  });
});

describe("useConfirmDialog shorthand", () => {
  it("accepts a bare message string and defaults the confirm label", async () => {
    function Harness() {
      const confirm = useConfirmDialog();
      const [answer, setAnswer] = useState<string>("");
      return (
        <>
          <span data-testid="answer">{answer}</span>
          <button
            type="button"
            onClick={async () => setAnswer(String(await confirm("Wirklich fortfahren?")))}
          >
            Los
          </button>
        </>
      );
    }
    const { user } = renderWithApp(<Harness />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: "Los" }));

    expect(screen.getByText("Wirklich fortfahren?")).toBeInTheDocument();
    // No confirmLabel given → the neutral default.
    await user.click(screen.getByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(screen.getByTestId("answer")).toHaveTextContent("true"));
  });
});

describe("DownloadButton", () => {
  it("reports a rejection that is not an Error as a generic failure", async () => {
    const realFetch = globalThis.fetch;
    globalThis.fetch = (() => Promise.reject("abgebrochen")) as typeof fetch;
    try {
      const { user } = renderWithApp(
        <DownloadButton path="/api/x">Herunterladen</DownloadButton>,
      );
      await user.click(screen.getByRole("button", { name: "Herunterladen" }));
      expect(await screen.findByText("Download fehlgeschlagen.")).toBeInTheDocument();
    } finally {
      globalThis.fetch = realFetch;
    }
  });
});
