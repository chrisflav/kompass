import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "../auth";
import { ConfirmProvider, ToastProvider } from "../components/ui";
import { AppRoutes } from "../routes";

/**
 * A fresh client per test: retries off so a mocked 4xx surfaces immediately,
 * and no cache carried between tests.
 */
function testQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

/** The provider stack from `main.tsx`, minus the browser router. */
function Providers({ children, route }: { children: ReactNode; route: string }) {
  return (
    <QueryClientProvider client={testQueryClient()}>
      <AuthProvider>
        <ToastProvider>
          <ConfirmProvider>
            <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
          </ConfirmProvider>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export interface RenderOptions {
  /** Initial location; also what `useParams` resolves against when `path` is set. */
  route?: string;
  /** Route pattern to mount `ui` under, e.g. "/kompass/members/:id". */
  path?: string;
  /** Whether a token is present (components behind `ProtectedRoute` need one). */
  authenticated?: boolean;
}

/**
 * Render a component the way the app renders it: inside the real providers, at a
 * real location, with a token in place so `useMe` and the API client behave as
 * they do in the browser.
 */
export function renderWithApp(
  ui: ReactElement,
  { route = "/", path, authenticated = true }: RenderOptions = {},
): RenderResult & { user: ReturnType<typeof userEvent.setup> } {
  if (authenticated) localStorage.setItem("kompass_token", "test-token");
  // `delay: null` drops user-event's per-keystroke timer. These are integration
  // tests with long forms; the default 0ms-but-real delay makes them minutes
  // slower without testing anything the instant path does not.
  const user = userEvent.setup({ delay: null });
  const result = render(
    <Providers route={route}>
      {path ? (
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      ) : (
        ui
      )}
    </Providers>,
  );
  return { ...result, user };
}

/** Render a hook inside the same providers (for hooks that query the API). */
export function renderHookWithApp<T>(
  useHook: () => T,
  route = "/",
  { authenticated = true }: { authenticated?: boolean } = {},
) {
  // `useMe` (and therefore `usePermissions`) only fetches when a token exists.
  if (authenticated) localStorage.setItem("kompass_token", "test-token");
  const captured: { current: T | undefined } = { current: undefined };
  function Probe() {
    captured.current = useHook();
    return null;
  }
  const result = render(
    <Providers route={route}>
      <Probe />
    </Providers>,
  );
  return { ...result, captured };
}

/**
 * Mount the app's real route tree at `route`, so a test drives the same layout,
 * route guard and page the browser would. Preferred over rendering a page
 * component directly: it also covers routing and the surrounding chrome.
 */
export function renderRoute(route: string, { authenticated = true } = {}) {
  return renderWithApp(<AppRoutes />, { route, authenticated });
}

type User = ReturnType<typeof userEvent.setup>;

/**
 * Type a value into every editable field inside `scope`, toggle every checkbox
 * and pick something in every custom select.
 *
 * The detail forms carry dozens of fields whose only behaviour is "write this
 * key into the draft"; driving each one in its own test would say nothing that
 * this does not. Search inputs and file pickers are skipped — they belong to the
 * list toolbar and to the upload flows, which have their own tests.
 */
export async function fillEveryField(user: User, scope: HTMLElement): Promise<void> {
  const fields = [...scope.querySelectorAll("input, textarea")] as HTMLInputElement[];
  for (const el of fields) {
    if (el.disabled || el.readOnly) continue;
    const type = (el.getAttribute("type") ?? "text").toLowerCase();
    if (type === "checkbox" || type === "radio") {
      await user.click(el);
      continue;
    }
    if (type === "file" || type === "search") continue;
    await user.clear(el);
    if (type === "date") await user.type(el, "2026-03-04");
    else if (type === "datetime-local") await user.type(el, "2026-03-04T10:00");
    else if (type === "time") await user.type(el, "17:30");
    else if (type === "number") await user.type(el, "3");
    else if (type === "email") await user.type(el, "test@example.org");
    else await user.type(el, "Text");
  }
}

/** Open every Select / MultiSelect inside `scope` and take its first option. */
export async function pickEverySelect(user: User, scope: HTMLElement): Promise<void> {
  const triggers = [...scope.querySelectorAll(".ss-trigger, .ms-toggle")] as HTMLElement[];
  for (const trigger of triggers) {
    await user.click(trigger);
    const option = document.querySelector<HTMLElement>(".ms-dropdown .ms-opt");
    if (option) await user.click(option);
    else await user.click(trigger);
  }
}

/**
 * Click every sortable column header twice, so each sort accessor runs in both
 * directions. The admin's list_display is wide; asserting each column's ordering
 * separately would restate the same one-line accessor over and over.
 */
export async function sortByEveryColumn(user: User): Promise<void> {
  const headers = [...document.querySelectorAll<HTMLElement>(".th-sort")];
  for (const header of headers) {
    await user.click(header);
    await user.click(header);
  }
}
