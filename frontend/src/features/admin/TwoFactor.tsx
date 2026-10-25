import { lazy, Suspense, useState } from "react";

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
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";
import { createCredential, webauthnSupported } from "./webauthn";

type TwoFactorStatus = components["schemas"]["TwoFactorStatus"];
type FactorOut = components["schemas"]["FactorOut"];
type FactorAdded = components["schemas"]["FactorAdded"];
type TOTPSetup = components["schemas"]["TOTPSetup"];

const QRCodeSVG = lazy(() => import("qrcode.react").then((m) => ({ default: m.QRCodeSVG })));

const STATUS_KEY = ["auth", "two-factor"];

function kindLabel(f: FactorOut) {
  if (f.kind === "totp") return <Badge tone="info">Authenticator-App</Badge>;
  return f.passwordless ? (
    <Badge tone="success">Passkey</Badge>
  ) : (
    <Badge tone="info">Sicherheitsschlüssel</Badge>
  );
}

function errorsOf(e: Error): Record<string, string[]> {
  return e instanceof ApiError ? e.fieldErrors : {};
}

function FieldError({ errors }: { errors?: string[] }) {
  return errors ? <div className="field-error">{errors.join(" ")}</div> : null;
}

/**
 * The signed-in user's second factors: authenticator apps, security keys and
 * the recovery codes for when neither is at hand. Adding or removing a factor
 * and replacing the recovery codes ask for the password again.
 */
export function TwoFactorPage() {
  const query = useApiQuery(STATUS_KEY, () => unwrap(client.GET("/api/logindata/two-factor")));
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const close = () => setDialog(null);
  const added = (result: FactorAdded) =>
    setDialog(result.recovery_codes.length ? { kind: "codes", codes: result.recovery_codes } : null);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Zwei-Faktor-Authentifizierung" }]}
        subtitle="Schützt dein Konto, auch wenn jemand dein Passwort kennt."
        actions={
          query.data?.available && (
            <Button onClick={() => setDialog({ kind: "choose" })}>Faktor hinzufügen</Button>
          )
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
          status.available ? (
            <TwoFactorBody status={status} onDialog={setDialog} />
          ) : (
            <EmptyState>
              Die Anmeldung und ihre Faktoren verwaltet euer Identitätsanbieter, nicht Kompass.
            </EmptyState>
          )
        }
      </QueryBoundary>
      {dialog?.kind === "choose" && <ChooseFactorModal onClose={close} onChoose={setDialog} />}
      {dialog?.kind === "totp" && <AddTotpModal onClose={close} onAdded={added} />}
      {dialog?.kind === "key" && <AddKeyModal onClose={close} onAdded={added} />}
      {dialog?.kind === "rename" && <RenameModal factor={dialog.factor} onClose={close} />}
      {dialog?.kind === "remove" && <RemoveModal factor={dialog.factor} onClose={close} />}
      {dialog?.kind === "regenerate" && (
        <RegenerateModal onClose={close} onCodes={(codes) => setDialog({ kind: "codes", codes })} />
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
  | { kind: "remove"; factor: FactorOut }
  | { kind: "regenerate" }
  | { kind: "codes"; codes: string[] };

function TwoFactorBody({
  status,
  onDialog,
}: {
  status: TwoFactorStatus;
  onDialog: (d: Dialog) => void;
}) {
  if (status.factors.length === 0) {
    return <EmptyState>Du hast noch keinen zweiten Faktor eingerichtet.</EmptyState>;
  }
  return (
    <>
      <DataTable
        rows={status.factors}
        rowKey={(f) => `${f.kind}-${f.id}`}
        columns={[
          { header: "Name", cell: (f) => f.name },
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
                <Button type="button" variant="ghost" onClick={() => onDialog({ kind: "rename", factor: f })}>
                  Umbenennen
                </Button>
                <Button type="button" variant="ghost" onClick={() => onDialog({ kind: "remove", factor: f })}>
                  Entfernen
                </Button>
              </div>
            ),
          },
        ]}
      />
      <h3 className="fieldset-title">Wiederherstellungscodes</h3>
      <p className="fieldset-help">
        Hast du keinen deiner Faktoren zur Hand, meldest du dich mit einem Wiederherstellungscode an.
        Jeder Code gilt nur einmal. Du hast noch <strong>{status.recovery_codes_remaining}</strong>{" "}
        unbenutzte Codes.
      </p>
      <div className="row-actions">
        <Button type="button" variant="ghost" onClick={() => onDialog({ kind: "regenerate" })}>
          Neue Codes erzeugen
        </Button>
      </div>
    </>
  );
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

function PasswordField({
  value,
  onChange,
  errors,
}: {
  value: string;
  onChange: (v: string) => void;
  errors?: string[];
}) {
  return (
    <Field label="Dein Passwort *" hint="Zur Bestätigung, dass du es bist.">
      <input
        type="password"
        autoComplete="current-password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
      />
      <FieldError errors={errors} />
    </Field>
  );
}

function AddTotpModal({ onClose, onAdded }: { onClose: () => void; onAdded: (r: FactorAdded) => void }) {
  const toast = useToast();
  const [password, setPassword] = useState("");
  const [setup, setSetup] = useState<TOTPSetup | null>(null);
  const [name, setName] = useState("Authenticator-App");
  const [code, setCode] = useState("");
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const fail = (e: Error) => {
    setErrors(errorsOf(e));
    toast.error(e.message);
  };

  const start = useApiMutation(
    () => unwrap(client.POST("/api/logindata/two-factor/totp/setup", { body: { password } })),
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
          <PasswordField value={password} onChange={setPassword} errors={errors.password} />
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
          <Field label="Name *" hint="Damit du die App später wiedererkennst.">
            <input value={name} onChange={(e) => setName(e.target.value)} required />
            <FieldError errors={errors.name} />
          </Field>
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
  const [password, setPassword] = useState("");
  const [name, setName] = useState("Sicherheitsschlüssel");
  const [errors, setErrors] = useState<Record<string, string[]>>({});

  const add = useApiMutation(
    async () => {
      const setup = await unwrap(
        client.POST("/api/logindata/two-factor/webauthn/setup", { body: { password } }),
      );
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
      onError: (e: Error) => {
        setErrors(errorsOf(e));
        // The browser's own errors (cancelled, timed out) are not for reading.
        toast.error(e instanceof ApiError ? e.message : "Der Sicherheitsschlüssel hat nicht geantwortet.");
      },
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
        <PasswordField value={password} onChange={setPassword} errors={errors.password} />
        <p className="muted small">
          Nach „Hinzufügen“ fragt dein Browser nach dem Schlüssel. Kann er dich selbst prüfen (PIN,
          Fingerabdruck), meldet er dich künftig auch ohne Passwort an.
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
      onError: (e: Error) => {
        setErrors(errorsOf(e));
        toast.error(e.message);
      },
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

function RemoveModal({ factor, onClose }: { factor: FactorOut; onClose: () => void }) {
  const toast = useToast();
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const remove = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/logindata/two-factor/{kind}/{factor_id}/remove", {
          params: { path: { kind: factor.kind, factor_id: factor.id } },
          body: { password },
        }),
      ),
    {
      invalidate: [STATUS_KEY],
      onSuccess: () => {
        toast.success("Entfernt.");
        onClose();
      },
      onError: (e: Error) => {
        setErrors(errorsOf(e));
        toast.error(e.message);
      },
    },
  );
  return (
    <Modal title={`„${factor.name}“ entfernen`} onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          remove.mutate(undefined);
        }}
      >
        <p>
          Danach meldest du dich nicht mehr damit an. Ist es dein letzter zweiter Faktor, verfallen
          auch deine Wiederherstellungscodes.
        </p>
        <PasswordField value={password} onChange={setPassword} errors={errors.password} />
        <div className="row-actions">
          <Button type="submit" variant="danger" busy={remove.isPending}>
            Entfernen
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function RegenerateModal({ onClose, onCodes }: { onClose: () => void; onCodes: (c: string[]) => void }) {
  const toast = useToast();
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const regenerate = useApiMutation(
    () => unwrap(client.POST("/api/logindata/two-factor/recovery-codes", { body: { password } })),
    {
      invalidate: [STATUS_KEY],
      onSuccess: (r) => onCodes(r.codes),
      onError: (e: Error) => {
        setErrors(errorsOf(e));
        toast.error(e.message);
      },
    },
  );
  return (
    <Modal title="Neue Wiederherstellungscodes" onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setErrors({});
          regenerate.mutate(undefined);
        }}
      >
        <p>Die neuen Codes ersetzen alle bisherigen; die alten gelten danach nicht mehr.</p>
        <PasswordField value={password} onChange={setPassword} errors={errors.password} />
        <div className="row-actions">
          <Button type="submit" busy={regenerate.isPending}>
            Erzeugen
          </Button>
        </div>
      </form>
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
