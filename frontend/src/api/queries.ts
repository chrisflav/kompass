import type { UseQueryOptions } from "@tanstack/react-query";

import { useApiQuery } from "./hooks";
import { client, unwrap } from "./http";

/**
 * Shared cache keys and queries for the lists many pages read.
 *
 * Every page that needs "all members" or "all groups" goes through the same key
 * here, so one fetch serves the list page, the dashboard and every picker — and
 * a mutation that invalidates the key refreshes all of them. Keys are prefix
 * matched on invalidation: `queryKeys.members()` also covers each member's
 * detail and inlines (`["members", id, ...]`), `queryKeys.trainings()` covers
 * the per-member training lists.
 */
export const queryKeys = {
  members: () => ["members"],
  member: (id: number) => ["members", id],
  memberEmergencyContacts: (id: number) => ["members", id, "emergency-contacts"],
  memberDocuments: (id: number) => ["members", id, "documents"],
  memberPermissions: (id: number) => ["members", id, "permission-members"],
  groups: () => ["groups"],
  excursions: () => ["excursions"],
  trainings: () => ["trainings"],
  memberTrainings: (memberId: number) => ["trainings", { member: memberId }],
  trainingCategories: () => ["training-categories"],
  emailAddresses: () => ["mailer", "email-addresses"],
};

/**
 * How long a reference list counts as fresh. These lists back pickers and
 * labels on most pages, and every edit made here invalidates them explicitly,
 * so refetching them on each navigation only repeats the same answer. Changes
 * made by someone else show up after this long (or on reload).
 */
export const REFERENCE_STALE_TIME = 5 * 60_000;

type ListOptions<T> = Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn">;

function useReferenceList<T>(key: unknown[], fn: () => Promise<T>, options?: ListOptions<T>) {
  return useApiQuery(key, fn, { staleTime: REFERENCE_STALE_TIME, ...options });
}

const fetchMembers = () => unwrap(client.GET("/api/members/"));
const fetchGroups = () => unwrap(client.GET("/api/members/groups"));
const fetchExcursions = () => unwrap(client.GET("/api/members/excursions"));
const fetchTrainingCategories = () => unwrap(client.GET("/api/members/training-categories"));
const fetchEmailAddresses = () => unwrap(client.GET("/api/mailer/email-addresses"));

type Members = Awaited<ReturnType<typeof fetchMembers>>;
type Groups = Awaited<ReturnType<typeof fetchGroups>>;
type Excursions = Awaited<ReturnType<typeof fetchExcursions>>;
type TrainingCategories = Awaited<ReturnType<typeof fetchTrainingCategories>>;
type EmailAddresses = Awaited<ReturnType<typeof fetchEmailAddresses>>;

/** Every member the user may list (`GET /api/members/`). */
export function useMembers(options?: ListOptions<Members>) {
  return useReferenceList(queryKeys.members(), fetchMembers, options);
}

/** Every group (`GET /api/members/groups`). */
export function useGroups(options?: ListOptions<Groups>) {
  return useReferenceList(queryKeys.groups(), fetchGroups, options);
}

/** Every excursion the user may list (`GET /api/members/excursions`). */
export function useExcursions(options?: ListOptions<Excursions>) {
  return useReferenceList(queryKeys.excursions(), fetchExcursions, options);
}

/** Every training category (`GET /api/members/training-categories`). */
export function useTrainingCategories(options?: ListOptions<TrainingCategories>) {
  return useReferenceList(queryKeys.trainingCategories(), fetchTrainingCategories, options);
}

/** Every managed email address (`GET /api/mailer/email-addresses`). */
export function useEmailAddresses(options?: ListOptions<EmailAddresses>) {
  return useReferenceList(queryKeys.emailAddresses(), fetchEmailAddresses, options);
}
