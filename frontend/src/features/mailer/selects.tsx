import { MultiSelect, Select } from "../../components/ui";

// Re-export the shared searchable-badge MultiSelect so mailer call sites
// (messages / addresses) pick it up unchanged.
export { MultiSelect };

/** Option shape for the single-select used in the mailer forms. */
export interface Option {
  value: number;
  label: string;
}

/** Native single-select for an optional foreign key (empty option = `null`). */
export function SingleSelect({
  options,
  value,
  onChange,
  placeholder = "—",
}: {
  options: Option[];
  value: number | null;
  onChange: (next: number | null) => void;
  placeholder?: string;
}) {
  return (
    <Select
      value={value === null ? "" : String(value)}
      onChange={(v) => onChange(v === "" ? null : Number(v))}
      options={options}
      placeholder={placeholder}
      allowEmpty
      emptyLabel={placeholder}
    />
  );
}
