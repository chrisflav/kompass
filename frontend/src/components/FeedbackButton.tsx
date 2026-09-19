import { useState } from "react";
import { useLocation } from "react-router-dom";

import { ApiError, client, unwrap } from "../api/http";
import { useApiMutation } from "../api/hooks";
import { Button, Field, Modal, useToast } from "./ui";

/** Mirrors MAX_MESSAGE_LENGTH in feedback/api/router.py. */
const MAX_LENGTH = 5000;

/**
 * The feedback button, carried by the site chrome so it is on every page.
 *
 * Anyone can use it — the public website included — and a signed-in sender is
 * attributed by the API from the bearer token the client already sends. The
 * page context is opt-out rather than silent: the dialog prints the exact
 * values that would travel with the note.
 */
export function FeedbackButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="feedback-btn"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        <span aria-hidden="true">✎</span>
        <span className="feedback-btn-label">Feedback</span>
      </button>
      {open && <FeedbackDialog onClose={() => setOpen(false)} />}
    </>
  );
}

function FeedbackDialog({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const location = useLocation();
  const [message, setMessage] = useState("");
  const [withContext, setWithContext] = useState(true);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  // What "the current page" actually means, spelled out so the checkbox is an
  // informed choice rather than a promise.
  const pageUrl = `${window.location.origin}${location.pathname}${location.search}`;
  const userAgent = navigator.userAgent;

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/feedback", {
          body: {
            message,
            page_url: withContext ? pageUrl : "",
            user_agent: withContext ? userAgent : "",
          },
        }),
      ),
    {
      onSuccess: () => {
        toast.success("Danke für dein Feedback!");
        onClose();
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  const tooLong = message.length > MAX_LENGTH;
  const remaining = MAX_LENGTH - message.length;

  return (
    <Modal title="Feedback geben" onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setFieldErrors({});
          mutation.mutate(undefined);
        }}
      >
        <p className="muted">
          Was ist dir aufgefallen? Fehler, Wünsche und Lob landen alle beim Team.
        </p>

        <Field label="Dein Feedback">
          <textarea
            autoFocus
            rows={6}
            required
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          {/* Only count down once it matters, so the field is quiet while typing. */}
          {remaining < 500 && (
            <span className={tooLong ? "field-error" : "field-hint"}>
              {tooLong
                ? `${-remaining} Zeichen zu viel.`
                : `Noch ${remaining} Zeichen.`}
            </span>
          )}
          {fieldErrors.message && (
            <div className="field-error">{fieldErrors.message.join(" ")}</div>
          )}
        </Field>

        <label className="feedback-context">
          <input
            type="checkbox"
            checked={withContext}
            onChange={(e) => setWithContext(e.target.checked)}
          />
          <span>
            <span className="feedback-context-label">Aktuelle Seite mitsenden</span>
            <span className="feedback-context-detail">
              Hilft beim Nachstellen. Mitgesendet wird dann:
              <code>{pageUrl}</code>
              <code>{userAgent}</code>
            </span>
          </span>
        </label>

        <div className="row-actions">
          <Button type="submit" busy={mutation.isPending} disabled={!message.trim() || tooLong}>
            Absenden
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </form>
    </Modal>
  );
}
