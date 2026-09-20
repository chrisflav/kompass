import { act, render, renderHook, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  ConfirmProvider,
  DataTable,
  formatDate,
  Modal,
  useConfirmDialog,
  useRowSelection,
} from "./ui";

describe("formatDate", () => {
  it("renders an ISO date in German", () => {
    expect(formatDate("2011-05-04")).toBe("4.5.2011");
  });

  it("renders an em dash for a missing value", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("")).toBe("—");
  });

  it("passes an unparseable value through rather than showing 'Invalid Date'", () => {
    expect(formatDate("nicht-ein-datum")).toBe("nicht-ein-datum");
  });

  it("handles a full timestamp", () => {
    expect(formatDate("2026-08-30T10:15:00Z")).toBe("30.8.2026");
  });
});

describe("useRowSelection", () => {
  it("starts empty", () => {
    const { result } = renderHook(() => useRowSelection<number>());
    expect(result.current.count).toBe(0);
  });

  it("toggles a single key on and off", () => {
    const { result } = renderHook(() => useRowSelection<number>());
    act(() => result.current.toggle(1));
    expect(result.current.selected.has(1)).toBe(true);
    act(() => result.current.toggle(1));
    expect(result.current.selected.has(1)).toBe(false);
  });

  it("selects all, then clears all on a second toggle", () => {
    const { result } = renderHook(() => useRowSelection<number>());
    act(() => result.current.toggleAll([1, 2, 3]));
    expect(result.current.count).toBe(3);
    act(() => result.current.toggleAll([1, 2, 3]));
    expect(result.current.count).toBe(0);
  });

  it("selects all when only some are already selected", () => {
    const { result } = renderHook(() => useRowSelection<number>());
    act(() => result.current.toggle(2));
    act(() => result.current.toggleAll([1, 2, 3]));
    expect(result.current.count).toBe(3);
  });

  it("clears the selection outright", () => {
    const { result } = renderHook(() => useRowSelection<number>());
    act(() => result.current.toggleAll([1, 2]));
    act(() => result.current.clear());
    expect(result.current.count).toBe(0);
  });
});

describe("DataTable selection", () => {
  const rows = [
    { id: 1, name: "Anna" },
    { id: 2, name: "Bernd" },
  ];
  const columns = [{ header: "Name", cell: (r: (typeof rows)[number]) => r.name }];

  function Harness({ onRowClick }: { onRowClick?: (r: (typeof rows)[number]) => void }) {
    const selection = useRowSelection<number>();
    return (
      <>
        <span data-testid="count">{selection.count}</span>
        <DataTable
          rows={rows}
          rowKey={(r) => r.id}
          columns={columns}
          onRowClick={onRowClick}
          selection={{
            selected: selection.selected as Set<string | number>,
            onToggle: (k) => selection.toggle(Number(k)),
            onToggleAll: (keys) => selection.toggleAll(keys.map(Number)),
          }}
        />
      </>
    );
  }

  it("renders no checkbox column when selection is not configured", () => {
    render(<DataTable rows={rows} rowKey={(r) => r.id} columns={columns} />);
    expect(screen.queryByLabelText("Zeile auswählen")).not.toBeInTheDocument();
  });

  it("selects a row without opening it", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    render(<Harness onRowClick={onRowClick} />);

    await user.click(screen.getAllByLabelText("Zeile auswählen")[0]);

    expect(screen.getByTestId("count")).toHaveTextContent("1");
    // Clicking the checkbox must not also navigate into the row.
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it("select-all ticks every row checkbox", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByLabelText("Alle auswählen"));
    expect(screen.getByTestId("count")).toHaveTextContent("2");
    for (const box of screen.getAllByLabelText("Zeile auswählen")) {
      expect(box).toBeChecked();
    }
  });

  it("shows the empty state instead of a header-only table", () => {
    render(<DataTable rows={[]} rowKey={(r: { id: number }) => r.id} columns={[]} empty="Nichts da." />);
    expect(screen.getByText("Nichts da.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("Modal", () => {
  it("closes on a backdrop click but not on a click inside the dialog", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { container } = render(
      <Modal title="Titel" onClose={onClose}>
        <p>Inhalt</p>
      </Modal>,
    );
    // Rendered through a portal, so it is not inside `container`.
    expect(container).toBeEmptyDOMElement();

    await user.click(screen.getByText("Inhalt"));
    expect(onClose).not.toHaveBeenCalled();

    await user.click(document.querySelector(".modal-backdrop")!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("exposes a labelled dialog and a close button", () => {
    render(
      <Modal title="Neue Gruppe" onClose={vi.fn()}>
        <p>x</p>
      </Modal>,
    );
    expect(screen.getByRole("dialog", { name: "Neue Gruppe" })).toBeInTheDocument();
    expect(screen.getByLabelText("Schließen")).toBeInTheDocument();
  });

  it("does not submit the page form it is rendered from", async () => {
    const user = userEvent.setup();
    const outer = vi.fn((e: React.FormEvent) => e.preventDefault());
    const inner = vi.fn((e: React.FormEvent) => e.preventDefault());
    // Several detail pages render a modal from inside their own <form>. The
    // portal breaks the DOM nesting, but React still replays events along the
    // component tree — so submitting the dialog used to also save the page.
    render(
      <form onSubmit={outer}>
        <Modal title="Passwort setzen" onClose={vi.fn()}>
          <form onSubmit={inner}>
            <button type="submit">Speichern</button>
          </form>
        </Modal>
      </form>,
    );

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(inner).toHaveBeenCalledTimes(1);
    expect(outer).not.toHaveBeenCalled();
  });
});

describe("useConfirmDialog", () => {
  function Harness({ onResult }: { onResult: (v: boolean) => void }) {
    const confirm = useConfirmDialog();
    return (
      <button
        type="button"
        onClick={async () =>
          onResult(await confirm({ message: "Wirklich löschen?", confirmLabel: "Löschen", danger: true }))
        }
      >
        Löschen
      </button>
    );
  }

  it("resolves true when confirmed", async () => {
    const user = userEvent.setup();
    const onResult = vi.fn();
    render(
      <ConfirmProvider>
        <Harness onResult={onResult} />
      </ConfirmProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    expect(screen.getByText("Wirklich löschen?")).toBeInTheDocument();

    // Both the trigger and the dialog's confirm read "Löschen", so scope the
    // query to the dialog.
    const dialog = within(screen.getByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Löschen" }));
    await vi.waitFor(() => expect(onResult).toHaveBeenCalledWith(true));
  });

  it("resolves false when cancelled, and closes", async () => {
    const user = userEvent.setup();
    const onResult = vi.fn();
    render(
      <ConfirmProvider>
        <Harness onResult={onResult} />
      </ConfirmProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(onResult).toHaveBeenCalledWith(false);
    expect(screen.queryByText("Wirklich löschen?")).not.toBeInTheDocument();
  });
});
