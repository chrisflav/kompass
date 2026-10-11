import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Prose } from "../features/public/site/shared";
import { renderRoute, renderWithApp } from "../test/utils";
import { handlePreloadError, reloadOnce } from "./ChunkBoundary";

// What a tab left open across a deploy sees: the chunks it was built against
// are gone, so every lazy import rejects. (Inline: vi.mock is hoisted above
// anything the factories could share.)
vi.mock("../features/public/site/Markdown", () => {
  throw new Error("Failed to fetch dynamically imported module");
});
vi.mock("../kompassRoutes", () => {
  throw new Error("Failed to fetch dynamically imported module");
});

const realLocation = window.location;
let reload: ReturnType<typeof vi.fn>;

beforeEach(() => {
  reload = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: { ...realLocation, reload },
  });
  // React reports every caught render error; that is the point of these tests.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: realLocation,
  });
});

describe("a chunk that no longer exists", () => {
  it("offers a reload in place of a post body instead of a blank page", async () => {
    const { user } = renderWithApp(<Prose text="Ein **fetter** Absatz." />, {
      authenticated: false,
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("Neue Version verfügbar");
    await user.click(screen.getByRole("button", { name: "Neu laden" }));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("offers a reload in place of the workspace", async () => {
    renderRoute("/kompass");
    expect(await screen.findByRole("alert")).toHaveTextContent("Neue Version verfügbar");
    expect(screen.getByRole("button", { name: "Neu laden" })).toBeInTheDocument();
  });
});

describe("reloading for a new build", () => {
  it("reloads once and swallows the error, then lets it through", () => {
    const first = new Event("vite:preloadError", { cancelable: true });
    handlePreloadError(first, reload);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(first.defaultPrevented).toBe(true);

    // Straight after a reload the new build failed too: no loop, the boundary
    // takes over.
    const second = new Event("vite:preloadError", { cancelable: true });
    handlePreloadError(second, reload);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(second.defaultPrevented).toBe(false);
  });

  it("allows a later deploy its own reload", () => {
    vi.spyOn(Date, "now").mockReturnValue(1_000_000);
    expect(reloadOnce(reload)).toBe(true);
    vi.spyOn(Date, "now").mockReturnValue(1_000_000 + 60_000);
    expect(reloadOnce(reload)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("reloads the page itself by default", () => {
    expect(reloadOnce()).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("does not reload where session storage is refused", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(reloadOnce(reload)).toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});
