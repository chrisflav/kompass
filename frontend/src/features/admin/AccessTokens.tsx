import { useState } from "react";

import { API_BASE } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useMe, usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  Badge,
  Button,
  DataTable,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  Select,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";

type PersonalTokenOut = components["schemas"]["PersonalTokenOut"];
type PersonalTokenCreated = components["schemas"]["PersonalTokenCreated"];

const TOKENS_KEY = ["auth", "tokens"];

const NEVER = "never";

const LIFETIME_OPTIONS = [
  { value: "7", label: "7 Tage" },
  { value: "30", label: "30 Tage" },
  { value: "90", label: "90 Tage" },
  { value: NEVER, label: "Unbegrenzt" },
];

const ACCESS_OPTIONS = [
  { value: "read", label: "Nur lesen" },
  { value: "write", label: "Lesen und schreiben" },
];

function formatDateTime(value: string): string {
  const d = new Date(value);
  return d.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * The signed-in user's personal access tokens: bearer tokens for a script or an
 * assistant that should reach the API as this user, without a browser login.
 * Listing and revoking one's own tokens is open to everyone; creating one takes
 * `logindata.create_personalaccesstoken`. A superuser manages every account's
 * tokens and creates them for other accounts too, such as a bot's.
 */
export function AccessTokensList() {
  const { can, isSuperuser } = usePermissions();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<PersonalTokenCreated | null>(null);

  const query = useApiQuery(TOKENS_KEY, () => unwrap(client.GET("/api/logindata/tokens")));

  const revoke = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/logindata/tokens/{token_id}", {
          params: { path: { token_id: id } },
        }),
      ),
    {
      invalidate: [TOKENS_KEY],
      onSuccess: () => toast.success("Token widerrufen."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Zugangstokens" }]}
        subtitle="Zugang zur Kompass-API ohne Anmeldung im Browser."
        actions={
          can("logindata.create_personalaccesstoken") && (
            <Button onClick={() => setCreating(true)}>Neues Token</Button>
          )
        }
      />
      <p className="fieldset-help">
        Ein Token handelt mit den Rechten seines Kontos — wer es kennt, sieht und (falls erlaubt)
        ändert, was dieses Konto sehen und ändern darf. Gib es nur Programmen, denen du vertraust,
        und widerrufe es, sobald es nicht mehr gebraucht wird.
      </p>
      {creating && (
        <CreateTokenModal
          onClose={() => setCreating(false)}
          onCreated={(token) => {
            setCreating(false);
            setCreated(token);
          }}
        />
      )}
      {created && <CreatedTokenModal token={created} onClose={() => setCreated(null)} />}
      <QueryBoundary
        query={query}
        empty={isSuperuser ? "Es gibt keine Zugangstokens." : "Du hast keine Zugangstokens."}
      >
        {(rows: PersonalTokenOut[]) => (
          <DataTable
            rows={rows}
            rowKey={(t) => t.id}
            columns={[
              { header: "Name", cell: (t) => t.name },
              ...(isSuperuser
                ? [{ header: "Konto", cell: (t: PersonalTokenOut) => t.user.username }]
                : []),
              {
                header: "Rechte",
                cell: (t) =>
                  t.read_only ? (
                    <Badge tone="info">nur lesen</Badge>
                  ) : (
                    <Badge tone="warning">lesen und schreiben</Badge>
                  ),
              },
              { header: "Erstellt", cell: (t) => formatDateTime(t.created) },
              {
                header: "Gültig bis",
                cell: (t) =>
                  t.expires === null ? (
                    <span className="muted">unbegrenzt</span>
                  ) : new Date(t.expires) <= new Date() ? (
                    <Badge tone="danger">abgelaufen</Badge>
                  ) : (
                    formatDateTime(t.expires)
                  ),
              },
              {
                header: "",
                cell: (t) => (
                  <div className="row-actions inline-actions">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={async () => {
                        if (
                          await confirm({
                            message: `Token „${t.name}“ widerrufen? Programme, die es benutzen, verlieren sofort den Zugang.`,
                            danger: true,
                            confirmLabel: "Widerrufen",
                          })
                        )
                          revoke.mutate(t.id);
                      }}
                    >
                      Widerrufen
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

function CreateTokenModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (token: PersonalTokenCreated) => void;
}) {
  const toast = useToast();
  const { isSuperuser } = usePermissions();
  const me = useMe();
  const [name, setName] = useState("");
  const [access, setAccess] = useState("read");
  const [days, setDays] = useState("30");
  // "" is the signed-in account; a superuser may pick another one.
  const [account, setAccount] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const users = useApiQuery(["auth", "users"], () => unwrap(client.GET("/api/logindata/users")), {
    enabled: isSuperuser,
  });
  const accountOptions = (users.data ?? [])
    .filter((u) => u.id !== me.data?.user_id)
    .map((u) => ({ value: String(u.id), label: u.username }));

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/logindata/tokens", {
          body: {
            name,
            read_only: access === "read",
            days: days === NEVER ? null : Number(days),
            user_id: account ? Number(account) : null,
          },
        }),
      ),
    {
      invalidate: [TOKENS_KEY],
      onSuccess: (token: PersonalTokenCreated) => onCreated(token),
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  return (
    <Modal title="Neues Zugangstoken" onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setFieldErrors({});
          mutation.mutate(undefined);
        }}
      >
        <Field label="Name *" hint="Wofür das Token ist, z. B. „Claude: Feedback abholen“.">
          <input value={name} onChange={(e) => setName(e.target.value)} required />
          {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
        </Field>
        <Field label="Rechte" hint="„Nur lesen“ genügt, um Daten abzurufen.">
          <Select value={access} onChange={setAccess} options={ACCESS_OPTIONS} />
        </Field>
        <Field
          label="Gültigkeit"
          hint={
            days === NEVER
              ? "Läuft nie ab — widerrufe es, sobald es nicht mehr gebraucht wird."
              : undefined
          }
        >
          <Select value={days} onChange={setDays} options={LIFETIME_OPTIONS} />
          {fieldErrors.days && <div className="field-error">{fieldErrors.days.join(" ")}</div>}
        </Field>
        {isSuperuser && (
          <Field label="Konto" hint="Für ein anderes Konto, etwa einen Bot, der sich nie anmeldet.">
            <Select
              value={account}
              onChange={setAccount}
              options={accountOptions}
              allowEmpty
              emptyLabel="Mein Konto"
              placeholder="Mein Konto"
            />
          </Field>
        )}
        <div className="row-actions">
          <Button type="submit" busy={mutation.isPending} disabled={!name.trim()}>
            Erstellen
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** The new token, shown this once: the server keeps no way to show it again. */
function CreatedTokenModal({
  token,
  onClose,
}: {
  token: PersonalTokenCreated;
  onClose: () => void;
}) {
  const toast = useToast();
  const example = new URL("/api/feedback", API_BASE || window.location.origin).href;

  return (
    <Modal title="Token erstellt" onClose={onClose} size="sm">
      <div className="stack">
        <p>
          Kopiere das Token für <strong>{token.user.username}</strong> jetzt. Es wird{" "}
          <strong>nur dieses eine Mal</strong> angezeigt.
        </p>
        <code className="token-secret">{token.token}</code>
        <p className="muted small">So wird es benutzt:</p>
        <code className="token-secret">
          curl -H "Authorization: Bearer {token.token}" {example}
        </code>
        <div className="row-actions">
          <Button
            type="button"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(token.token);
                toast.success("Token kopiert.");
              } catch {
                toast.error("Kopieren nicht möglich — bitte von Hand markieren.");
              }
            }}
          >
            Kopieren
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Fertig
          </Button>
        </div>
      </div>
    </Modal>
  );
}
