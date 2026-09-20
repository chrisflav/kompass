import "@testing-library/jest-dom/vitest";

// jsdom installs its own URLSearchParams, while MSW's request interceptor
// validates a form body against Node's. The two are different realms, so a
// `URLSearchParams` body (which is how the login posts its OAuth grant) is
// rejected before any handler sees it. Align the global with Node's before MSW
// is set up.
import { URLSearchParams as NodeURLSearchParams } from "node:url";
import nodeMultipart from "./nodeMultipart";

Object.defineProperty(globalThis, "URLSearchParams", {
  configurable: true,
  writable: true,
  value: NodeURLSearchParams,
});

// Same realm split for multipart uploads: jsdom installs its own FormData/File/
// Blob, and a body built from those never finishes being read on MSW's Node
// side — an upload test would hang rather than fail. Node's own implementations
// are already global here, so restore them over jsdom's.
for (const name of ["FormData", "File", "Blob"] as const) {
  const impl = nodeMultipart[name];
  Object.defineProperty(globalThis, name, { configurable: true, writable: true, value: impl });
  // jsdom exposes `window` separately; keep the two in step.
  Object.defineProperty(window, name, { configurable: true, writable: true, value: impl });
}

import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { server } from "./server";

// testing-library budgets `findBy*`/`waitFor` from its own 1s default, which
// the generous `testTimeout` in the vitest config does not raise. One scheduler
// stall over a second on a loaded machine — a CI runner, say — is then enough
// to fail a query that would have resolved, so give the async utilities a
// budget that still sits well inside the test timeout.
configure({ asyncUtilTimeout: 5000 });

// A request no handler covers is a bug in the test, not something to silently
// pass through to a real backend.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  cleanup();
  server.resetHandlers();
  localStorage.clear();
  sessionStorage.clear();
});

afterAll(() => server.close());

// jsdom implements neither of these, and the UI kit uses both.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}
if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}
