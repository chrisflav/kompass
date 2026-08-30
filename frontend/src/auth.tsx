import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { API_BASE } from "./api/client";
import { setUnauthorizedHandler } from "./api/http";

const TOKEN_KEY = "kompass_token";
const CLIENT_ID = "kompass-frontend-dev";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

interface AuthContextValue {
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(getToken());

  async function login(username: string, password: string) {
    // Resource-Owner-Password-Credentials grant against the project's own
    // OAuth2 provider. (Production would use Authorization-Code + PKCE.)
    const body = new URLSearchParams({
      grant_type: "password",
      username,
      password,
      client_id: CLIENT_ID,
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
      // 400 with invalid_grant is the wrong-credentials case; anything else is
      // a server/configuration problem the user cannot act on.
      const isCredentials = res.status === 400 || res.status === 401;
      throw new Error(
        isCredentials
          ? "Benutzername oder Passwort ist falsch."
          : "Anmeldung derzeit nicht möglich. Bitte wende dich an die Administration.",
      );
    }
    const data = (await res.json()) as { access_token: string };
    localStorage.setItem(TOKEN_KEY, data.access_token);
    setToken(data.access_token);
  }

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }, []);

  // An expired token makes every request 401; drop it once, centrally, so the
  // route guard sends the user to the login screen instead of each page
  // rendering its own "not authorised" state.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (getToken()) logout();
    });
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  return <AuthContext.Provider value={{ token, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
