import { createContext, useContext, useState, type ReactNode } from "react";

import { API_BASE } from "./api/client";

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
    const res = await fetch(`${API_BASE}/o/token/`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) {
      throw new Error("Login failed — check credentials and that the dev OAuth app exists.");
    }
    const data = (await res.json()) as { access_token: string };
    localStorage.setItem(TOKEN_KEY, data.access_token);
    setToken(data.access_token);
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
  }

  return <AuthContext.Provider value={{ token, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
