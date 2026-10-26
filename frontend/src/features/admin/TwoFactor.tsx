import { useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useRef, useState } from "react";

import { ApiError, client, unwrap } from "../../api/http";
import { ChunkBoundary } from "../../components/ChunkBoundary";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  Spinner,
  formatDate,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";
import { createCredential, getCredential, webauthnSupported } from "./webauthn";

type TwoFactorStatus = components["schemas"]["TwoFactorStatus"];
type FactorOut = components["schemas"]["FactorOut"];
type FactorAdded = components["schemas"]["FactorAdded"];
type TOTPSetup = components["schemas"]["TOTPSetup"];

const QRCodeSVG = lazy(() => import("qrcode.react").then((m) => ({ default: m.QRCodeSVG })));

const STATUS_KEY = ["auth", "two-factor"];

function kindLabel(f: FactorOut) {
  return <Badge tone="info">{f.kind === "totp" ? "Authenticator-App" : "Sicherheitsschlüssel"}</Badge>;
}

function errorsOf(e: Error): Record<string, string[]> {
  return e instanceof ApiError ? e.fieldErrors : {};
}

function FieldError({ errors }: { errors?: string[] }) {
  return errors ? <div className="field-error">{errors.join(" ")}</div> : null;
}

/**
 * Report a failed change; a refusal (403) means the confirmation ran out, so
 * the status is fetched again and the page asks for it anew.
 */
function useFail(setErrors?: (e: Record<string, string[]>) => void) {
  const toast = useToast();
  const qc = useQueryClient();
  return (e: Error) => {
    setErrors?.(errorsOf(e));
    toast.error(e.message);
    if (e instanceof ApiError && e.status === 403) qc.invalidateQueries({ queryKey: STATUS_KEY });
  };
}

function isElevated(status: TwoFactorStatus): boolean {
  return !!status.elevated_until && new Date(status.elevated_until) > new Date();
}

/**
 * The signed-in user's second factors: authenticator apps, security keys and
 * the recovery codes for when neither is at hand. The page first asks who is
 * there — with a second factor, or the password while there is none — and
 * then allows changes for ten minutes before asking again.
 */
export function TwoFactorPage() {
  // No retries: the library holds them back while the tab is in the background,
  // which left a failing status on the spinner instead of its error.
  const query = useApiQuery(STATUS_KEY, () => unwrap(client.GET("/api/logindata/two-factor")), {
    retry: false,
  });
  const qc = useQueryClient();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const close = () => setDialog(null);
  const showCodes = (codes: string[]) => setDialog(codes.length ? { kind: "codes", codes } : null);
  const added = (result: FactorAdded) =>
    result.factor.kind === "webauthn" && !result.factor.passwordless
      ? setDialog({ kind: "plainKey", codes: result.recovery_codes })
      : showCodes(result.recovery_codes);
  const elevated = !!query.data && query.data.available && isElevated(query.data);

  // When the confirmation runs out, fetch the status again: the page then asks anew.
  const until = query.data?.elevated_until;
  useEffect(() => {
    if (!until) return;
    const timer = setTimeout(
      () => qc.invalidateQueries({ queryKey: STATUS_KEY }),
      Math.max(new Date(until).getTime() - Date.now(), 0) + 500,
    );
    return () => clearTimeout(timer);
  }, [until, qc]);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Zwei-Faktor-Authentifizierung" }]}
        subtitle="Schützt dein Konto, auch wenn jemand dein Passwort kennt."
        actions={
          elevated && <Button onClick={() => setDialog({ kind: "choose" })}>Faktor hinzufügen</Button>
        }
      />
      <p className="fieldset-help">
        Mit einem zweiten Faktor fragt Kompass bei der Anmeldung nach dem Passwort zusätzlich nach
        einem Code aus einer Authenticator-App oder nach einem Sicherheitsschlüssel. Ein Passkey —
        ein Sicherheitsschlüssel, der dich selbst per PIN oder Fingerabdruck prüft — meldet dich
        sogar ganz ohne Passwort an.
      </p>
      <QueryBoundary query={query}>
        {(status: TwoFactorStatus) =>
          !status.available ? (
            <EmptyState>
              Die Anmeldung und ihre Faktoren verwaltet euer Identitätsanbieter, nicht Kompass.
            </EmptyState>
          ) : isElevated(status) ? (
            <TwoFactorBody status={status} onDialog={setDialog} />
          ) : (
            <ConfirmStep status={status} />
          )
        }
      </QueryBoundary>
      {elevated && (
        <>
          {dialog?.kind === "choose" && <ChooseFactorModal onClose={close} onChoose={setDialog} />}
          {dialog?.kind === "totp" && <AddTotpModal onClose={close} onAdded={added} />}
          {dialog?.kind === "key" && <AddKeyModal onClose={close} onAdded={added} />}
          {dialog?.kind === "rename" && <RenameModal factor={dialog.factor} onClose={close} />}
        </>
      )}
      {dialog?.kind === "plainKey" && (
        <PlainKeyModal onClose={() => showCodes(dialog.codes)} />
      )}
      {dialog?.kind === "codes" && <RecoveryCodesModal codes={dialog.codes} onClose={close} />}
    </div>
  );
}

type Dialog =
  | { kind: "choose" }
  | { kind: "totp" }
  | { kind: "key" }
  | { kind: "rename"; factor: FactorOut }
  | { kind: "plainKey"; codes: string[] }
  | { kind: "codes"; codes: string[] };

/**
 * Confirm who is there before the factors are shown: with a second factor where
 * there is one, otherwise with the password. The default factor comes first (a
 * security key is asked at once), the others below; a failed key waits for a
 * click rather than asking again by itself.
 */
function ConfirmStep({ status }: { status: TwoFactorStatus }) {
  const toast = useToast();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const keys = status.has_webauthn && webauthnSupported();
  // The preferred factor where this browser can use it; otherwise the app, or a key.
  const primary =
    status.preferred_method === "webauthn" && keys
      ? "webauthn"
      : status.has_totp
        ? "totp"
        : keys
          ? "webauthn"
          : null;
  const defaultKey = primary === "webauthn" ? (status.preferred_key_id ?? null) : null;
  const [keyFailed, setKeyFailed] = useState(false);
  const [othersOpen, setOthersOpen] = useState(primary === null);
  const confirm = useApiMutation(
    (body: components["schemas"]["ConfirmIn"]) =>
      unwrap(client.POST("/api/logindata/two-factor/confirm", { body })),
    { invalidate: [STATUS_KEY], onError: (e: Error) => toast.error(e.message) },
  );
  const withKey = useApiMutation(
    async (keyId: number | null) => {
      const { options, state } = await unwrap(
        client.POST("/api/logindata/two-factor/confirm/options", {
          params: { query: keyId === null ? {} : { key_id: keyId } },
        }),
      );
      const credential = await getCredential(options);
      return unwrap(
        client.POST("/api/logindata/two-factor/confirm", { body: { credential, state } }),
      );
    },
    {
      invalidate: [STATUS_KEY],
      onError: (e: Error) => {
        setKeyFailed(true);
        setOthersOpen(true);
        toast.error(e instanceof ApiError ? e.message : "Der Sicherheitsschlüssel hat nicht geantwortet.");
      },
    },
  );
  // A security key first is asked once, as the step appears.
  const asked = useRef(false);
  useEffect(() => {
    if (primary !== "webauthn" || asked.current) return;
    asked.current = true;
    withKey.mutate(defaultKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!status.enabled) {
    return (
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          confirm.mutate({ password });
        }}
      >
        <p>Bitte bestätige mit deinem Passwort, dass du es bist.</p>
        <Field label="Dein Passwort *">
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <div className="row-actions">
          <Button type="submit" busy={confirm.isPending}>
            Bestätigen
          </Button>
        </div>
      </form>
    );
  }

  const keyButton = (keyId: number | null, label: string, secondary: boolean) => (
    <div className="row-actions">
      <Button
        type="button"
        variant={secondary ? "ghost" : "primary"}
        busy={withKey.isPending && withKey.variables === keyId}
        onClick={() => withKey.mutate(keyId)}
      >
        {label}
      </Button>
    </div>
  );
  const totpForm = (secondary: boolean) => (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        confirm.mutate({ code });
      }}
    >
      <Field label="Code aus deiner Authenticator-App *">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus={!secondary}
          required
        />
      </Field>
      <div className="row-actions">
        <Button type="submit" variant={secondary ? "ghost" : "primary"} busy={confirm.isPending}>
          Bestätigen
        </Button>
      </div>
    </form>
  );
  return (
    <div className="stack">
      <p>Bitte bestätige mit deinem zweiten Faktor, dass du es bist.</p>
      {primary === "webauthn" &&
        keyButton(defaultKey, keyFailed ? "Erneut versuchen" : "Mit Sicherheitsschlüssel bestätigen", false)}
      {primary === "totp" && totpForm(false)}
      <details open={othersOpen} onToggle={(e) => setOthersOpen(e.currentTarget.open)}>
        <summary>Andere Methode verwenden</summary>
        <div className="stack">
          {primary === "webauthn" && status.has_totp && totpForm(true)}
          {primary === "totp" && keys && keyButton(null, "Mit Sicherheitsschlüssel bestätigen", true)}
          {primary === "webauthn" &&
            defaultKey !== null &&
            keyButton(null, "Anderen Sicherheitsschlüssel verwenden", true)}
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              confirm.mutate({ recovery_code: recoveryCode });
            }}
          >
            <Field label="Wiederherstellungscode *">
              <input
                value={recoveryCode}
                onChange={(e) => setRecoveryCode(e.target.value)}
                autoComplete="off"
                spellCheck={false}
                required
              />
            </Field>
            <div className="row-actions">
              <Button type="submit" variant="ghost" busy={confirm.isPending}>
                Mit Code bestätigen
              </Button>
            </div>
          </form>
        </div>
      </details>
    </div>
  );
}

function TwoFactorBody({
  status,
  onDialog,
}: {
  status: TwoFactorStatus;
  onDialog: (d: Dialog) => void;
}) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const fail = useFail();
  const remove = useApiMutation(
    (factor: FactorOut) =>
      unwrap(
        client.POST("/api/logindata/two-factor/{kind}/{factor_id}/remove", {
          params: { path: { kind: factor.kind, factor_id: factor.id } },
        }),
      ),
    { invalidate: [STATUS_KEY], onSuccess: () => toast.success("Entfernt."), onError: fail },
  );
  const setDefault = useApiMutation(
    (body: DefaultIn) => unwrap(client.PUT("/api/logindata/two-factor/default", { body })),
    { invalidate: [STATUS_KEY], onSuccess: () => toast.success("Gespeichert."), onError: fail },
  );
  const regenerate = useApiMutation(
    () => unwrap(client.POST("/api/logindata/two-factor/recovery-codes")),
    {
      invalidate: [STATUS_KEY],
      onSuccess: (r) => onDialog({ kind: "codes", codes: r.codes }),
      onError: fail,
    },
  );

  if (status.factors.length === 0) {
    return <EmptyState>Du hast noch keinen zweiten Faktor eingerichtet.</EmptyState>;
  }
  return (
    <>
      <DataTable
        rows={status.factors}
        rowKey={(f) => `${f.kind}-${f.id}`}
        columns={[
          {
            header: "Name",
            cell: (f) => (
              <span className="factor-name">
                {f.name}
                {f.passwordless && <Badge tone="success">Passkey</Badge>}
                {f.default && <Badge tone="neutral">Standard</Badge>}
              </span>
            ),
          },
          { header: "Art", cell: kindLabel },
          { header: "Hinzugefügt", cell: (f) => formatDate(f.created) },
          {
            header: "Zuletzt benutzt",
            cell: (f) => (f.last_used ? formatDate(f.last_used) : <span className="muted">nie</span>),
          },
          {
            header: "",
            cell: (f) => (
              <div className="row-actions inline-actions">
                {!f.default && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() =>
                      setDefault.mutate(
                        f.kind === "totp" ? { method: "totp" } : { method: "webauthn", key_id: f.id },
                      )
                    }
                  >
                    Als Standard festlegen
                  </Button>
                )}
                <Button type="button" variant="ghost" onClick={() => onDialog({ kind: "rename", factor: f })}>
                  Umbenennen
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={async () => {
                    if (
                      await confirm({
                        message: `„${f.name}“ entfernen? Danach meldest du dich nicht mehr damit an. Ist es dein letzter zweiter Faktor, verfallen auch deine Wiederherstellungscodes.`,
                        danger: true,
                        confirmLabel: "Entfernen",
                      })
                    )
                      remove.mutate(f);
                  }}
                >
                  Entfernen
                </Button>
              </div>
            ),
          },
        ]}
      />
      <h3 className="fieldset-title">Standardmethode</h3>
      <p className="fieldset-help">
        Diese Methode bietet Kompass bei der Anmeldung zuerst an; ein Sicherheitsschlüssel wird dann
        gleich abgefragt. Ohne Festlegung kommt ein Sicherheitsschlüssel vor der App.
      </p>
      <Field label="Bei der Anmeldung zuerst">
        <select
          value={defaultValue(status)}
          disabled={setDefault.isPending}
          onChange={(e) => setDefault.mutate(parseDefault(e.target.value))}
        >
          <option value="">Keine Festlegung</option>
          {status.has_totp && <option value="totp">Authenticator-App</option>}
          {status.has_webauthn && <option value="webauthn">Sicherheitsschlüssel (beliebiger)</option>}
          {status.factors
            .filter((f) => f.kind === "webauthn")
            .map((f) => (
              <option key={f.id} value={`webauthn:${f.id}`}>
                Sicherheitsschlüssel „{f.name}“
              </option>
            ))}
        </select>
      </Field>
      <h3 className="fieldset-title">Wiederherstellungscodes</h3>
      <p className="fieldset-help">
        Hast du keinen deiner Faktoren zur Hand, meldest du dich mit einem Wiederherstellungscode an.
        Jeder Code gilt nur einmal. Du hast noch <strong>{status.recovery_codes_remaining}</strong>{" "}
        unbenutzte Codes.
      </p>
      <div className="row-actions">
        <Button
          type="button"
          variant="ghost"
          busy={regenerate.isPending}
          onClick={async () => {
            if (
              await confirm({
                message: "Neue Codes erzeugen? Sie ersetzen alle bisherigen; die alten gelten danach nicht mehr.",
                confirmLabel: "Erzeugen",
              })
            )
              regenerate.mutate(undefined);
          }}
        >
          Neue Codes erzeugen
        </Button>
      </div>
    </>
  );
}

type DefaultIn = components["schemas"]["DefaultIn"];

/** The default as the choice's value: "", "totp", "webauthn" or "webauthn:<id>". */
function defaultValue(status: TwoFactorStatus): string {
  if (status.default_method === "webauthn" && status.default_key_id != null) {
    return `webauthn:${status.default_key_id}`;
  }
  return status.default_method ?? "";
}

function parseDefault(value: string): DefaultIn {
  if (value === "") return { method: null };
  if (value === "totp") return { method: "totp" };
  const [, id] = value.split(":");
  return { method: "webauthn", key_id: id ? Number(id) : null };
}

const HINT = { margin: "0.35rem 0 0" };

/** Which kind of factor to add; a security key only where the browser can talk to one. */
function ChooseFactorModal({ onClose, onChoose }: { onClose: () => void; onChoose: (d: Dialog) => void }) {
  return (
    <Modal title="Faktor hinzufügen" onClose={onClose} size="sm">
      <div className="stack">
        <div>
          <Button type="button" onClick={() => onChoose({ kind: "totp" })}>
            Authenticator-App
          </Button>
          <p className="muted small" style={HINT}>
            Ein Code aus einer App wie Aegis oder Google Authenticator.
          </p>
        </div>
        {webauthnSupported() && (
          <div>
            <Button type="button" onClick={() => onChoose({ kind: "key" })}>
              Sicherheitsschlüssel
            </Button>
            <p className="muted small" style={HINT}>
              Ein YubiKey, dein Smartphone oder der Fingerabdrucksensor deines Geräts; als Passkey
              auch ohne Passwort.
            </p>
          </div>
        )}
      </div>
    </Modal>
  );
}

function AddTotpModal({ onClose, onAdded }: { onClose: () => void; onAdded: (r: FactorAdded) => void }) {
  const toast = useToast();
  const [setup, setSetup] = useState<TOTPSetup | null>(null);
  const [name, setName] = useState("Authenticator-App");
  const [code, setCode] = useState("");
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const fail = useFail(setErrors);

  const start = useApiMutation(
    () => unwrap(client.POST("/api/logindata/two-factor/totp/setup")),
    { onSuccess: (s: TOTPSetup) => setSetup(s), onError: fail },
  );
  const confirm = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/logindata/two-factor/totp", {
          body: { name, code, state: setup!.state },
        }),
      ),
    {
      invalidate: [STATUS_KEY],
      onSuccess: (r: FactorAdded) => {
        toast.success("Authenticator-App hinzugefügt.");
        onAdded(r);
      },
      onError: fail,
    },
  );

  return (
    <Modal title="Authenticator-App hinzufügen" onClose={onClose} size="sm">
      {setup === null ? (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            setErrors({});
            start.mutate(undefined);
          }}
        >
          <Field label="Name *" hint="Damit du die App später wiedererkennst.">
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <div className="row-actions">
            <Button type="submit" busy={start.isPending}>
              Weiter
            </Button>
          </div>
        </form>
      ) : (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            setErrors({});
            confirm.mutate(undefined);
          }}
        >
          <p>Scanne den Code mit deiner Authenticator-App, oder gib den Schlüssel von Hand ein.</p>
          <div className="qr-code" aria-label="QR-Code für die Authenticator-App">
            <ChunkBoundary>
              <Suspense fallback={<Spinner />}>
                <QRCodeSVG value={setup.uri} size={180} marginSize={2} />
              </Suspense>
            </ChunkBoundary>
          </div>
          <code className="token-secret">{setup.secret}</code>
          <FieldError errors={errors.name} />
          <Field label="Code aus der App *">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              required
            />
            <FieldError errors={errors.code} />
          </Field>
          <div className="row-actions">
            <Button type="submit" busy={confirm.isPending}>
              Hinzufügen
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function AddKeyModal({ onClose, onAdded }: { onClose: () => void; onAdded: (r: FactorAdded) => void }) {
  const toast = useToast();
  const [name, setName] = useState("Sicherheitsschlüssel");
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const fail = useFail(setErrors);

  const add = useApiMutation(
    async () => {
      const setup = await unwrap(client.POST("/api/logindata/two-factor/webauthn/setup"));
      const credential = await createCredential(setup.options);
      return unwrap(
        client.POST("/api/logindata/two-factor/webauthn", {
          body: { name, credential, state: setup.state },
        }),
      );
    },
    {
      invalidate: [STATUS_KEY],
      onSuccess: (r: FactorAdded) => {
        toast.success("Sicherheitsschlüssel hinzugefügt.");
        onAdded(r);
      },
      onError: (e: Error) =>
        // The browser's own errors (cancelled, timed out) are not for reading.
        fail(e instanceof ApiError ? e : new Error("Der Sicherheitsschlüssel hat nicht geantwortet.")),
    },
  );

  return (
    <Modal title="Sicherheitsschlüssel hinzufügen" onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          add.mutate(undefined);
        }}
      >
        <Field label="Name *" hint="Etwa „YubiKey am Schlüsselbund“.">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
          <FieldError errors={errors.name} />
        </Field>
        <p className="muted small">
          Nach „Hinzufügen“ fragt dein Browser nach dem Schlüssel. Prüft er dich selbst per PIN,
          Fingerabdruck oder Gesichtserkennung, wird er als <strong>Passkey</strong> eingerichtet:
          Dann meldest du dich mit ihm auch ganz ohne Passwort an („Mit Passkey anmelden“). Sonst
          dient er als zweiter Faktor nach dem Passwort.
        </p>
        <div className="row-actions">
          <Button type="submit" busy={add.isPending}>
            Hinzufügen
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function RenameModal({ factor, onClose }: { factor: FactorOut; onClose: () => void }) {
  const toast = useToast();
  const [name, setName] = useState(factor.name);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const fail = useFail(setErrors);
  const rename = useApiMutation(
    () =>
      unwrap(
        client.PATCH("/api/logindata/two-factor/{kind}/{factor_id}", {
          params: { path: { kind: factor.kind, factor_id: factor.id } },
          body: { name },
        }),
      ),
    {
      invalidate: [STATUS_KEY],
      onSuccess: () => {
        toast.success("Umbenannt.");
        onClose();
      },
      onError: fail,
    },
  );
  return (
    <Modal title="Umbenennen" onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          rename.mutate(undefined);
        }}
      >
        <Field label="Name *">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
          <FieldError errors={errors.name} />
        </Field>
        <div className="row-actions">
          <Button type="submit" busy={rename.isPending}>
            Speichern
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** A key that came without passkey support: a second factor only. */
function PlainKeyModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Ohne Passkey eingerichtet" onClose={onClose} size="sm">
      <div className="stack">
        <p>
          Der Sicherheitsschlüssel wurde hinzugefügt, aber nicht als Passkey: Er prüft dich nicht
          selbst per PIN oder Fingerabdruck. Du nutzt ihn nach dem Passwort als zweiten Faktor; ohne
          Passwort meldet er dich nicht an.
        </p>
        <div className="row-actions">
          <Button type="button" onClick={onClose}>
            Verstanden
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/** The recovery codes, shown this once: the server keeps only their hashes. */
function RecoveryCodesModal({ codes, onClose }: { codes: string[]; onClose: () => void }) {
  const toast = useToast();
  return (
    <Modal title="Deine Wiederherstellungscodes" onClose={onClose} size="sm">
      <div className="stack">
        <p>
          Bewahre diese Codes an einem sicheren Ort auf, etwa ausgedruckt oder in einem
          Passwortmanager. Sie werden <strong>nur dieses eine Mal</strong> angezeigt; jeder gilt für
          eine Anmeldung.
        </p>
        <ul className="recovery-codes">
          {codes.map((c) => (
            <li key={c}>
              <code>{c}</code>
            </li>
          ))}
        </ul>
        <div className="row-actions">
          <Button
            type="button"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(codes.join("\n"));
                toast.success("Codes kopiert.");
              } catch {
                toast.error("Kopieren nicht möglich — bitte von Hand markieren.");
              }
            }}
          >
            Kopieren
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Ich habe sie gespeichert
          </Button>
        </div>
      </div>
    </Modal>
  );
}
