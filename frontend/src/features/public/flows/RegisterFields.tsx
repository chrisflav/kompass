import { Field } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { GenderSelect } from "./shared";

type RegisterMemberData = components["schemas"]["RegisterMemberData"];

export function emptyRegisterMember(): RegisterMemberData {
  return {
    prename: "",
    lastname: "",
    gender: 0,
    email: "",
    street: "",
    plz: "",
    town: "",
    address_extra: "",
    phone_number: "",
    birth_date: null,
    alternative_email: null,
    photos_may_be_taken: false,
  };
}

/** The full member field set shared by the password and invited registrations. */
export function RegisterMemberFields({
  member,
  onChange,
}: {
  member: RegisterMemberData;
  onChange: (member: RegisterMemberData) => void;
}) {
  const set = (patch: Partial<RegisterMemberData>) => onChange({ ...member, ...patch });
  return (
    <>
      <Field label="Vorname">
        <input value={member.prename} onChange={(e) => set({ prename: e.target.value })} />
      </Field>
      <Field label="Nachname">
        <input value={member.lastname} onChange={(e) => set({ lastname: e.target.value })} />
      </Field>
      <GenderSelect value={member.gender} onChange={(gender) => set({ gender })} />
      <Field label="E-Mail">
        <input type="email" value={member.email} onChange={(e) => set({ email: e.target.value })} />
      </Field>
      <Field label="Alternative E-Mail (optional)">
        <input
          type="email"
          value={member.alternative_email ?? ""}
          onChange={(e) => set({ alternative_email: e.target.value || null })}
        />
      </Field>
      <Field label="Geburtsdatum">
        <input
          type="date"
          value={member.birth_date ?? ""}
          onChange={(e) => set({ birth_date: e.target.value || null })}
        />
      </Field>
      <Field label="Straße">
        <input value={member.street} onChange={(e) => set({ street: e.target.value })} />
      </Field>
      <Field label="PLZ">
        <input value={member.plz} onChange={(e) => set({ plz: e.target.value })} />
      </Field>
      <Field label="Ort">
        <input value={member.town} onChange={(e) => set({ town: e.target.value })} />
      </Field>
      <Field label="Adresszusatz">
        <input
          value={member.address_extra}
          onChange={(e) => set({ address_extra: e.target.value })}
        />
      </Field>
      <Field label="Telefon">
        <input
          value={member.phone_number}
          onChange={(e) => set({ phone_number: e.target.value })}
        />
      </Field>
      <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
        <input
          type="checkbox"
          checked={member.photos_may_be_taken}
          onChange={(e) => set({ photos_may_be_taken: e.target.checked })}
        />
        <span className="field-label">Fotos dürfen gemacht werden</span>
      </label>
    </>
  );
}
