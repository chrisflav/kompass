import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { API_BASE } from "./api/client";
import { setUnauthorizedHandler } from "./api/http";

const TOKEN_KEY = "kompass_token";
const VERIFIER_KEY = "kompass_pkce_verifier";
const STATE_KEY = "kompass_pkce_state";
const RETURN_KEY = "kompass_pkce_return";

/* --- the automatic login's loop guard ------------------------------------
 *
 * /login leaves for the provider on its own when a page needs a login. A token
 * the API rejects straight after it was issued would then bounce login →
 * provider → callback → login forever, as the provider's session lets the user
 * through without a form. So every start is recorded, and only a request that
 * went through signed in (`/members/me`) clears the record; until then, and
 * after a refused callback or a sign-out, /login waits for a click.
 */
const AUTOSTART_KEY = "kompass_login_autostart";
const FAILED_KEY = "kompass_login_failed";
const LOGGED_OUT_KEY = "kompass_logged_out";
const AUTOSTART_WINDOW_MS = 60_000;

/** Whether /login may leave for the provider without a click: "held" after a
 *  recent unconfirmed start or a refused callback, "loggedOut" after signing
 *  out, "unknown" when storage cannot be read. Only "go" starts on its own. */
export function autostartVerdict(): "go" | "held" | "loggedOut" | "unknown" {
  try {
    if (sessionStorage.getItem(LOGGED_OUT_KEY)) return "loggedOut";
    if (sessionStorage.getItem(FAILED_KEY)) return "held";
    const last = Number(sessionStorage.getItem(AUTOSTART_KEY));
    return last && Date.now() - last < AUTOSTART_WINDOW_MS ? "held" : "go";
  } catch {
    return "unknown";
  }
}

/** Records an attempt to leave for the provider; false if it cannot be
 *  recorded, since an unrecorded start could not be told apart from a loop. */
export function markLoginStart(): boolean {
  try {
    sessionStorage.setItem(AUTOSTART_KEY, String(Date.now()));
    sessionStorage.removeItem(FAILED_KEY);
    sessionStorage.removeItem(LOGGED_OUT_KEY);
    return true;
  } catch {
    return false;
  }
}

function writeGuard(update: (storage: Storage) => void) {
  try {
    update(sessionStorage);
  } catch {
    // Without storage nothing is recorded, and /login falls back to its button.
  }
}

/** The callback came back refusing. */
export function markLoginFailed() {
  writeGuard((storage) => storage.setItem(FAILED_KEY, "1"));
}

/** A request went through with the token: the login worked, so the next
 *  expired session may start one on its own again. */
export function markSignedIn() {
  writeGuard((storage) => {
    storage.removeItem(AUTOSTART_KEY);
    storage.removeItem(FAILED_KEY);
  });
}

function markLoggedOut() {
  writeGuard((storage) => storage.setItem(LOGGED_OUT_KEY, "1"));
}

/** Ends the sign-in at the backend: the token is revoked, and the provider's
 *  session, which would otherwise let the next login through without asking,
 *  is ended with it. The session cookie travels only to an API on the same
 *  origin, as in production; a cross-origin development API still revokes the
 *  token. Best effort: signing out must not hang on an unreachable server. */
async function endSession(token: string) {
  try {
    await fetch(`${API_BASE}/api/logindata/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // The token is dropped here regardless.
  }
}

// Registered with the project's OAuth2 provider as a *public* client (no
// secret: a browser app cannot keep one). Set at build time so a deployment can
// register its own application rather than sharing the development one.
const CLIENT_ID = import.meta.env.VITE_OAUTH_CLIENT_ID ?? "kompass-frontend-dev";

/** Where the provider sends the browser back to. Must match the redirect URI
 *  registered on the OAuth application, so it is derived from the live origin
 *  rather than baked in — the same build then works on any host. */
export function redirectUri(): string {
  return `${window.location.origin}/callback`;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/** URL-safe base64 without padding, as RFC 7636 requires for the challenge. */
function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomToken(): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(32)));
}

async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64Url(new Uint8Array(digest));
}

interface AuthContextValue {
  token: string | null;
  /** Starts the Authorization-Code + PKCE flow by leaving for the provider. */
  beginLogin: (returnTo?: string) => Promise<void>;
  /** Finishes the flow from the callback route; resolves to where to go next. */
  completeLogin: (code: string, state: string) => Promise<string>;
  /** Signs out at the backend too, then leaves for the public start page. */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(getToken());

  // Authorization Code + PKCE. The password never reaches the SPA: credentials
  // are entered on the provider's own page, and this app only ever sees a
  // single-use code that is worthless without the verifier held here.
  async function beginLogin(returnTo = "/kompass") {
    const verifier = randomToken();
    const state = randomToken();
    // sessionStorage, not localStorage: the verifier is good for one exchange
    // in one tab, and must not outlive the tab that started the flow.
    sessionStorage.setItem(VERIFIER_KEY, verifier);
    sessionStorage.setItem(STATE_KEY, state);
    sessionStorage.setItem(RETURN_KEY, returnTo);
    const params = new URLSearchParams({
      response_type: "code",
      client_id: CLIENT_ID,
      redirect_uri: redirectUri(),
      state,
      code_challenge: await challengeFor(verifier),
      code_challenge_method: "S256",
      // Deliberately not `openid`: the SPA wants a bearer token for the API,
      // not an id_token, and asking for one makes the provider sign a JWT
      // with a key a deployment need not have configured.
      scope: "profile email",
    });
    window.location.assign(`${API_BASE}/o/authorize/?${params}`);
  }

  async function completeLogin(code: string, state: string): Promise<string> {
    const verifier = sessionStorage.getItem(VERIFIER_KEY);
    const expectedState = sessionStorage.getItem(STATE_KEY);
    const returnTo = sessionStorage.getItem(RETURN_KEY) ?? "/kompass";
    sessionStorage.removeItem(VERIFIER_KEY);
    sessionStorage.removeItem(STATE_KEY);
    sessionStorage.removeItem(RETURN_KEY);

    // A mismatch means this callback did not come from the flow this tab
    // started — the case `state` exists to catch. Refuse rather than exchange.
    if (!verifier || !expectedState || state !== expectedState) {
      throw new Error("Die Anmeldung konnte nicht zugeordnet werden. Bitte versuche es erneut.");
    }

    const body = new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri(),
      client_id: CLIENT_ID,
      code_verifier: verifier,
    });
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/o/token/`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
    } catch {
      throw new Error("Der Server ist nicht erreichbar. Bitte versuche es später erneut.");
    }
    if (!res.ok) {
      throw new Error("Anmeldung derzeit nicht möglich. Bitte wende dich an die Administration.");
    }
    const data = (await res.json()) as { access_token: string };
    localStorage.setItem(TOKEN_KEY, data.access_token);
    setToken(data.access_token);
    return returnTo;
  }

  const dropToken = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }, []);

  async function logout() {
    // Before anything else, so no page reached from here on starts a login.
    markLoggedOut();
    const current = getToken();
    if (current) await endSession(current);
    // A full page load rather than an in-app navigation: it also drops every
    // answer cached for the user who just left. The token goes from storage
    // only, so the page does not flash the login screen while it unloads.
    localStorage.removeItem(TOKEN_KEY);
    window.location.assign("/");
  }

  // An expired token makes every request 401; drop it once, centrally, so the
  // route guard sends the user to the login screen instead of each page
  // rendering its own "not authorised" state.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (getToken()) dropToken();
    });
    return () => setUnauthorizedHandler(null);
  }, [dropToken]);

  return (
    <AuthContext.Provider value={{ token, beginLogin, completeLogin, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
