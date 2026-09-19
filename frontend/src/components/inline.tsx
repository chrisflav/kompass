import type { ReactNode } from "react";

import { Button } from "./ui";

/**
 * A related-object inline table for a parent's change view (mirrors a Django
 * admin inline). Lists the parent's rows; when `editing`, shows a per-row remove
 * button and either a header "add" button (`onAdd`, opens a modal) or an inline
 * add area (`renderAdd`). IMPORTANT: the parent detail is already inside a
 * <form>, so any add UI must NOT use a nested <form> — trigger creation with a
 * type="button" onClick instead.
 */
export function InlineTable<T>({
  title,
  rows,
  columns,
  rowKey,
  editing,
  onDelete,
  onAdd,
  addLabel = "Hinzufügen",
  renderAdd,
  empty = "Keine Einträge.",
}: {
  title: string;
  rows: T[];
  columns: { header: string; cell: (row: T) => ReactNode }[];
  rowKey: (row: T) => string | number;
  editing: boolean;
  /** Shows a "Entfernen" button per row when editing. */
  onDelete?: (row: T) => void;
  /** When set, an "add" button in the header opens the caller's modal dialog. */
  onAdd?: () => void;
  addLabel?: string;
  /** Legacy inline add area shown below the table when editing (no <form>). */
  renderAdd?: () => ReactNode;
  empty?: ReactNode;
}) {
  const showActions = editing && Boolean(onDelete);
  return (
    <section className="inline-section">
      <div className="inline-head">
        <h3 className="fieldset-title">{title}</h3>
        {editing && onAdd && (
          <Button type="button" variant="ghost" onClick={onAdd}>
            + {addLabel}
          </Button>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="muted small">{empty}</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c.header}>{c.header}</th>
                ))}
                {showActions && <th className="inline-actions" aria-label="Aktionen" />}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={rowKey(row)}>
                  {columns.map((c) => (
                    <td key={c.header}>{c.cell(row)}</td>
                  ))}
                  {showActions && (
                    <td className="inline-actions">
                      <Button type="button" variant="danger" onClick={() => onDelete!(row)}>
                        Entfernen
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && renderAdd && <div className="inline-add">{renderAdd()}</div>}
    </section>
  );
}
