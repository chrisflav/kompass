import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  DetailList,
  PageHeader,
  QueryBoundary,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";

type FeedbackBrief = components["schemas"]["FeedbackBrief"];
type FeedbackOut = components["schemas"]["FeedbackOut"];

const FEEDBACK = "/kompass/feedback";

/** Feedback is timestamped to the minute: when it arrived is part of the report. */
function formatReceived(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** First line of a note, for the list column. */
function firstLine(message: string, max = 90): string {
  const line = message.trim().split("\n")[0] ?? "";
  return line.length > max ? `${line.slice(0, max)}…` : line;
}

export function FeedbackList() {
  const navigate = useNavigate();
  const query = useApiQuery(["feedback"], () => unwrap(client.GET("/api/feedback")));
  const rows = query.data ?? [];

  const config: ListViewConfig<FeedbackBrief> = useMemo(
    () => ({
      search: (f) => [f.message, f.submitted_by?.name ?? "", f.page_url],
      filters: [
        {
          key: "sender",
          label: "Absender*in",
          options: [
            { value: "named", label: "Mit Konto" },
            { value: "anon", label: "Ohne Konto" },
          ],
          match: (f, v) => (v === "named" ? f.submitted_by !== null : f.submitted_by === null),
        },
      ],
      sort: {
        created: (f) => f.created,
        submitted_by: (f) => f.submitted_by?.name ?? "",
        message: (f) => f.message,
      },
      defaultSort: { key: "created", dir: "desc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Feedback" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
      />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Noch kein Feedback eingegangen.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(f) => f.id}
            onRowClick={(f) => navigate(`${FEEDBACK}/${f.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              {
                header: "Eingegangen",
                cell: (f) => formatReceived(f.created),
                sortKey: "created",
              },
              { header: "Rückmeldung", cell: (f) => firstLine(f.message), sortKey: "message" },
              {
                header: "Von",
                cell: (f) =>
                  f.submitted_by ? f.submitted_by.name : <span className="muted">ohne Konto</span>,
                sortKey: "submitted_by",
              },
              {
                header: "Seite",
                cell: (f) =>
                  f.has_context ? (
                    <Badge tone="info">mitgesendet</Badge>
                  ) : (
                    <span className="muted">—</span>
                  ),
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

export function FeedbackDetailPage() {
  const { id } = useParams();
  const feedbackId = Number(id);
  const query = useApiQuery(["feedback", feedbackId], () =>
    unwrap(
      client.GET("/api/feedback/{feedback_id}", {
        params: { path: { feedback_id: feedbackId } },
      }),
    ),
  );
  return (
    <QueryBoundary query={query}>{(f: FeedbackOut) => <FeedbackDetail feedback={f} />}</QueryBoundary>
  );
}

function FeedbackDetail({ feedback }: { feedback: FeedbackOut }) {
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();

  const remove = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/feedback/{feedback_id}", {
          params: { path: { feedback_id: feedback.id } },
        }),
      ),
    {
      invalidate: [["feedback"]],
      onSuccess: () => {
        toast.success("Feedback gelöscht.");
        navigate(FEEDBACK);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Feedback", to: FEEDBACK },
          { label: formatReceived(feedback.created) },
        ]}
        actions={
          <>
            <Button variant="ghost" onClick={() => navigate(FEEDBACK)}>
              Zurück
            </Button>
            {can("feedback.delete_feedback") && (
              <Button
                variant="danger"
                busy={remove.isPending}
                onClick={async () => {
                  const ok = await confirm({
                    message: "Dieses Feedback wirklich löschen?",
                    danger: true,
                    confirmLabel: "Löschen",
                  });
                  if (ok) remove.mutate(undefined);
                }}
              >
                Löschen
              </Button>
            )}
          </>
        }
      />

      {/* The note itself, not squeezed into a definition row — it is the point
          of the page and may run to paragraphs. */}
      <section className="feedback-message">{feedback.message}</section>

      <DetailList
        items={[
          ["Eingegangen", formatReceived(feedback.created)],
          [
            "Von",
            feedback.submitted_by ? (
              feedback.submitted_by.name
            ) : (
              <span className="muted">ohne Konto gesendet</span>
            ),
          ],
          [
            "Seite",
            feedback.page_url ? (
              <code className="feedback-context-value">{feedback.page_url}</code>
            ) : (
              <span className="muted">nicht mitgesendet</span>
            ),
          ],
          [
            "Browser",
            feedback.user_agent ? (
              <code className="feedback-context-value">{feedback.user_agent}</code>
            ) : (
              <span className="muted">nicht mitgesendet</span>
            ),
          ],
        ]}
      />
    </div>
  );
}
