import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Button,
  DataTable,
  EditableDetail,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  useConfirmDialog,
  useToast,
  type Crumb,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type FAQBrief = components["schemas"]["FAQBrief"];
type FAQOut = components["schemas"]["FAQOut"];
type FAQIn = components["schemas"]["FAQIn"];

const emptyFaq: FAQIn = { question: "", answer: "" };

function FaqFormFields({
  form,
  onChange,
  errors = {},
}: {
  form: FAQIn;
  onChange: (patch: Partial<FAQIn>) => void;
  errors?: Record<string, string[]>;
}) {
  return (
    <>
      <Field label="Frage">
        <input
          value={form.question}
          onChange={(e) => onChange({ question: e.target.value })}
          required
        />
        {errors.question && <div className="field-error">{errors.question.join(" ")}</div>}
      </Field>
      <Field label="Antwort">
        <textarea
          value={form.answer}
          onChange={(e) => onChange({ answer: e.target.value })}
          rows={6}
          required
        />
        {errors.answer && <div className="field-error">{errors.answer.join(" ")}</div>}
      </Field>
    </>
  );
}

export function FaqList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<FAQIn>(emptyFaq);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const query = useApiQuery(["faqs"], () => unwrap(client.GET("/api/startpage/faqs")));
  const rows = query.data ?? [];

  const create = useApiMutation(
    (body: FAQIn) => unwrap(client.POST("/api/startpage/faqs", { body })),
    {
      invalidate: [["faqs"]],
      onSuccess: (created: FAQOut) => {
        toast.success("Frage angelegt.");
        setCreating(false);
        navigate(`/kompass/cms/faqs/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  function openCreate() {
    setForm(emptyFaq);
    setFieldErrors({});
    setCreating(true);
  }

  const config: ListViewConfig<FAQBrief> = useMemo(
    () => ({
      sort: { question: (f) => f.question },
      defaultSort: { key: "question", dir: "asc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "FAQ" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={can("startpage.add_faq") && <Button onClick={openCreate}>Neue Frage</Button>}
      />
      {creating && (
        <Modal title="Neue Frage" onClose={() => setCreating(false)}>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              setFieldErrors({});
              create.mutate(form);
            }}
          >
            <FaqFormFields
              form={form}
              onChange={(patch) => setForm({ ...form, ...patch })}
              errors={fieldErrors}
            />
            <div className="row-actions">
              <Button type="submit" busy={create.isPending}>
                Anlegen
              </Button>
              <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
                Abbrechen
              </Button>
            </div>
          </form>
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Fragen vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(f) => f.id}
            onRowClick={(f) => navigate(`/kompass/cms/faqs/${f.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[{ header: "Frage", cell: (f) => f.question, sortKey: "question" }]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

export function FaqDetailPage() {
  const { id } = useParams();
  const faqId = Number(id);
  const query = useApiQuery(["faqs", faqId], () =>
    unwrap(
      client.GET("/api/startpage/faqs/{faq_id}", { params: { path: { faq_id: faqId } } }),
    ),
  );

  const crumbs: Crumb[] = [
    { label: "FAQ", to: "/kompass/cms/faqs" },
    { label: query.data?.question ?? "Frage" },
  ];

  return (
    <QueryBoundary query={query}>
      {(faq: FAQOut) => <FaqDetailBody faq={faq} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

function FaqDetailBody({ faq, crumbs }: { faq: FAQOut; crumbs: Crumb[] }) {
  const [editing, setEditing] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [form, setForm] = useState<FAQIn>(() => ({ question: faq.question, answer: faq.answer }));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const set = (patch: Partial<FAQIn>) => setForm((prev) => ({ ...prev, ...patch }));

  const update = useApiMutation(
    (body: FAQIn) =>
      unwrap(
        client.PUT("/api/startpage/faqs/{faq_id}", {
          params: { path: { faq_id: faq.id } },
          body,
        }),
      ),
    {
      invalidate: [["faqs"], ["faqs", faq.id]],
      onSuccess: () => {
        toast.success("Gespeichert.");
        setEditing(false);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  const remove = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/startpage/faqs/{faq_id}", { params: { path: { faq_id: faq.id } } }),
      ),
    {
      invalidate: [["faqs"]],
      onSuccess: () => {
        toast.success("Frage gelöscht.");
        navigate("/kompass/cms/faqs");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm({ question: faq.question, answer: faq.answer });
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Frage",
      field: "question",
      value: faq.question,
      edit: (
        <input
          value={form.question}
          onChange={(e) => set({ question: e.target.value })}
          required
        />
      ),
    },
    {
      label: "Antwort",
      field: "answer",
      value: faq.answer,
      edit: (
        <textarea
          value={form.answer}
          onChange={(e) => set({ answer: e.target.value })}
          rows={6}
          required
        />
      ),
    },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        update.mutate(form);
      }}
    >
      <PageHeader
        breadcrumbs={crumbs}
        actions={
          editing ? (
            <>
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                Abbrechen
              </Button>
              <Button type="submit" busy={update.isPending}>
                Speichern
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              <Button
                type="button"
                variant="danger"
                busy={remove.isPending}
                onClick={async () => {
                  if (
                    await confirm({
                      message: "Diese Frage wirklich löschen?",
                      danger: true,
                      confirmLabel: "Löschen",
                    })
                  )
                    remove.mutate(undefined);
                }}
              >
                Löschen
              </Button>
              <Button type="button" onClick={startEditing}>
                Bearbeiten
              </Button>
            </>
          )
        }
      />
      <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />
    </form>
  );
}
