import { useState } from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";

import { useAuth } from "../auth";
import { ContourField, KompassMark } from "../components/Contour";
import { Button, useDocumentTitle } from "../components/ui";

export function Login() {
  useDocumentTitle("Anmelden");
  const { token, beginLogin } = useAuth();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (token) return <Navigate to="/kompass" replace />;

  // Deliberately a button rather than an automatic redirect: a token that is
  // rejected the moment it is used would otherwise bounce login → provider →
  // callback → login forever, with nothing on screen to say why.
  async function onLogin() {
    setError(null);
    setBusy(true);
    try {
      const returnTo = (location.state as { from?: string } | null)?.from ?? "/kompass";
      await beginLogin(returnTo);
    } catch {
      setError("Anmeldung derzeit nicht möglich. Bitte wende dich an die Administration.");
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <ContourField />
      <div className="card">
        <span className="login-eyebrow">JDAV Ludwigsburg</span>
        <div className="login-brand">
          <KompassMark size={34} />
          <h1>Kompass</h1>
        </div>
        <p className="muted">Bitte anmelden, um den Verwaltungsbereich zu öffnen.</p>
        {error && <p className="error">{error}</p>}
        <Button onClick={onLogin} busy={busy}>
          Anmelden
        </Button>
      </div>
    </div>
  );
}

/** Lands here from the provider with `?code=&state=`, trades them for a token. */
export function AuthCallback() {
  useDocumentTitle("Anmeldung");
  const { token, completeLogin } = useAuth();
  const [params] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  const code = params.get("code");
  const state = params.get("state");
  const denied = params.get("error");

  if (!started) {
    setStarted(true);
    if (denied) {
      setError("Die Anmeldung wurde abgebrochen.");
    } else if (!code || !state) {
      setError("Die Antwort der Anmeldung war unvollständig. Bitte versuche es erneut.");
    } else {
      completeLogin(code, state)
        .then(setTarget)
        .catch((err: unknown) =>
          setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen."),
        );
    }
  }

  if (target) return <Navigate to={target} replace />;
  // A token without a target means the exchange finished on an earlier render.
  if (token && !error) return <Navigate to="/kompass" replace />;

  return (
    <div className="login">
      <ContourField />
      <div className="card">
        <div className="login-brand">
          <KompassMark size={34} />
          <h1>Kompass</h1>
        </div>
        {error ? (
          <>
            <p className="error">{error}</p>
            <Button onClick={() => window.location.assign("/login")}>Zurück zur Anmeldung</Button>
          </>
        ) : (
          <p className="muted">Anmeldung wird abgeschlossen …</p>
        )}
      </div>
    </div>
  );
}
