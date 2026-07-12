import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";

/**
 * Thin typed wrapper around TanStack Query. Pass a `queryFn` that returns
 * {@link unwrap}(client.GET(...)) so the path literal drives the result type:
 *
 *   const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
 */
export function useApiQuery<T>(
  key: unknown[],
  queryFn: () => Promise<T>,
  options?: Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn">,
) {
  return useQuery<T, Error>({ queryKey: key, queryFn, ...options });
}

/**
 * Typed mutation wrapper that invalidates the given query keys on success, so
 * lists refresh after a create/update/action.
 */
export function useApiMutation<TData, TVars>(
  mutationFn: (vars: TVars) => Promise<TData>,
  options: {
    invalidate?: unknown[][];
    onSuccess?: (data: TData, vars: TVars) => void;
  } & Omit<UseMutationOptions<TData, Error, TVars>, "mutationFn" | "onSuccess"> = {},
) {
  const qc = useQueryClient();
  const { invalidate, onSuccess, ...rest } = options;
  return useMutation<TData, Error, TVars>({
    mutationFn,
    onSuccess: (data, vars) => {
      for (const key of invalidate ?? []) {
        qc.invalidateQueries({ queryKey: key });
      }
      onSuccess?.(data, vars);
    },
    ...rest,
  });
}
