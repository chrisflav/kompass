import { useEffect, useRef, useState } from "react";
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
  const code = params.get("code");
  const state = params.get("state");
  const denied = params.get("error");

  // What the provider sent back can be judged without asking it anything, so
  // judge it while rendering. An initializer, not an effect: the redirect below
  // is reached on the first paint, and a holder of a stale token would be sent
  // to the dashboard before an effect had run to say the login was refused.
  const [error, setError] = useState<string | null>(() => {
    if (denied) return "Die Anmeldung wurde abgebrochen.";
    if (!code || !state) {
      return "Die Antwort der Anmeldung war unvollständig. Bitte versuche es erneut.";
    }
    return null;
  });
  const [target, setTarget] = useState<string | null>(null);

  // The exchange is the opposite case: it spends the PKCE verifier held in
  // sessionStorage and the authorization code at the provider, so it belongs in
  // an effect and must run exactly once. The guard is a ref rather than state
  // because StrictMode invokes the render function twice per pass and replays
  // mount effects, and a second run would find the verifier already cleared and
  // report the login as unassignable.
  const exchanged = useRef(false);

  useEffect(() => {
    if (exchanged.current || !code || !state || denied) return;
    exchanged.current = true;
    completeLogin(code, state)
      .then(setTarget)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Anmeldung fehlgeschlagen."),
      );
    // Runs once for the callback the browser landed on; the ref, not the
    // dependency list, is what keeps it to one attempt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
