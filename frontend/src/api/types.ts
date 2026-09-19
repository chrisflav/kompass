import type { components } from "./schema";

// Convenience aliases for the generated schema components. If ninja names a
// component differently, adjust it here in one place.
export type MemberBrief = components["schemas"]["MemberBrief"];
export type MemberOut = components["schemas"]["MemberOut"];
export type GroupOut = components["schemas"]["GroupOut"];
export type ExcursionBrief = components["schemas"]["ExcursionBrief"];
export type ExcursionOut = components["schemas"]["ExcursionOut"];
