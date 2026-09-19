import { useState } from "react";

import { ApiError, client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  Button,
  DataTable,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";

type RegistrationPasswordOut = components["schemas"]["RegistrationPasswordOut"];

/**
 * The shared secrets behind the "set your password" invite flow (`/passwort`).
 * A short list that is edited in place — the admin registered the model with a
 * plain `ModelAdmin`, and there is nothing to show on a detail page.
 */
export function RegistrationPasswordsList() {
  const { can } = usePermissions();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<RegistrationPasswordOut | null>(null);

  const query = useApiQuery(["auth", "registration-passwords"], () =>
    unwrap(client.GET("/api/logindata/registration-passwords")),
  );

  const remove = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/logindata/registration-passwords/{password_id}", {
          params: { path: { password_id: id } },
        }),
      ),
    {
      invalidate: [["auth", "registration-passwords"]],
      onSuccess: () => toast.success("Passwort gelöscht."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Registrierungspasswörter" }]}
        subtitle="Gemeinsame Passwörter für die Einladung „Passwort setzen“."
        actions={
          can("logindata.add_registrationpassword") && (
            <Button onClick={() => setCreating(true)}>Neues Passwort</Button>
          )
        }
      />
      <p className="fieldset-help">
        Wer per E-Mail eingeladen wird, ein Kompass-Konto anzulegen, muss zusätzlich eines dieser
        Passwörter kennen. Ein Passwort zu löschen macht alle offenen Einladungen ungültig, die
        damit arbeiten.
      </p>
      {(creating || editing) && (
        <PasswordModal
          entry={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}
      <QueryBoundary query={query} empty="Kein Registrierungspasswort hinterlegt.">
        {(rows: RegistrationPasswordOut[]) => (
          <DataTable
            rows={rows}
            rowKey={(r) => r.id}
            columns={[
              { header: "Passwort", cell: (r) => <code>{r.password}</code> },
              {
                header: "",
                cell: (r) => (
                  <div className="row-actions inline-actions">
                    {can("logindata.change_registrationpassword") && (
                      <Button type="button" variant="ghost" onClick={() => setEditing(r)}>
                        Ändern
                      </Button>
                    )}
                    {can("logindata.delete_registrationpassword") && (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={async () => {
                          if (
                            await confirm({
                              message:
                                "Dieses Registrierungspasswort wirklich löschen? Offene Einladungen damit funktionieren dann nicht mehr.",
                              danger: true,
                              confirmLabel: "Löschen",
                            })
                          )
                            remove.mutate(r.id);
                        }}
                      >
                        Entfernen
                      </Button>
                    )}
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

function PasswordModal({
  entry,
  onClose,
}: {
  entry: RegistrationPasswordOut | null;
  onClose: () => void;
}) {
  const toast = useToast();
  const [password, setPassword] = useState(entry?.password ?? "");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useApiMutation(
    () =>
      entry
        ? unwrap(
            client.PATCH("/api/logindata/registration-passwords/{password_id}", {
              params: { path: { password_id: entry.id } },
              body: { password },
            }),
          )
        : unwrap(
            client.POST("/api/logindata/registration-passwords", { body: { password } }),
          ),
    {
      invalidate: [["auth", "registration-passwords"]],
      onSuccess: () => {
        toast.success(entry ? "Passwort geändert." : "Passwort angelegt.");
        onClose();
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  return (
    <Modal
      title={entry ? "Registrierungspasswort ändern" : "Neues Registrierungspasswort"}
      onClose={onClose}
      size="sm"
    >
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setFieldErrors({});
          mutation.mutate(undefined);
        }}
      >
        <Field label="Passwort *" hint="Wird den Eingeladenen mitgeteilt, nicht verschlüsselt gespeichert.">
          <input value={password} onChange={(e) => setPassword(e.target.value)} required />
          {fieldErrors.password && (
            <div className="field-error">{fieldErrors.password.join(" ")}</div>
          )}
        </Field>
        <div className="row-actions">
          <Button type="submit" busy={mutation.isPending} disabled={!password.trim()}>
            {entry ? "Speichern" : "Anlegen"}
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </form>
    </Modal>
  );
}
