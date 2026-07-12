import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../auth";
import { ContourField, KompassMark } from "../components/Contour";
import { Button, Field } from "../components/ui";

export function Login() {
  const { token, login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (token) return <Navigate to="/app" replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <ContourField />
      <form className="card" onSubmit={onSubmit}>
        <span className="login-eyebrow">JDAV Ludwigsburg</span>
        <div className="login-brand">
          <KompassMark size={34} />
          <h1>Kompass</h1>
        </div>
        <p className="muted">Bitte anmelden, um den Verwaltungsbereich zu öffnen.</p>
        <Field label="Benutzername">
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </Field>
        <Field label="Passwort">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {error && <p className="error">{error}</p>}
        <Button type="submit" busy={busy}>
          Anmelden
        </Button>
      </form>
    </div>
  );
}
