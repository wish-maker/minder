import { useCallback, useEffect, useRef, useState } from "react";

import { friendlyErrorMessage } from "./api";

/** Shape returned by {@link useAsyncResource}. */
export interface AsyncResource<T> {
  /** Latest successfully-fetched value, or null before the first success. */
  data: T | null;
  /** User-facing error message from the most recent failed load, or null. */
  error: string | null;
  /** True while a load is in flight. */
  loading: boolean;
  /** Re-run the fetcher (e.g. after a mutation). Cancels any in-flight load. */
  reload: () => void;
}

export interface UseAsyncResourceOptions {
  /** Extra dependencies that should re-trigger the fetch when they change
   * (same semantics as a useEffect dep array). Default: []. */
  deps?: readonly unknown[];
  /** Abort the request after this many ms. OPT-IN only — long-running ops
   * (model pull, graph build, LLM query) must not get a timeout, so there is
   * NO default. When omitted, the request runs until it settles or unmounts. */
  timeoutMs?: number;
  /** Skip fetching while false (e.g. not authenticated yet). The resource stays
   * `{data:null, error:null, loading:false}`. Default: true. */
  enabled?: boolean;
}

/** Declarative data-fetching hook that removes the copy-pasted
 * `status/isError/loadX` boilerplate every page reimplemented, and adds the two
 * safeguards those hand-rolled versions all lacked (#502):
 *
 *  1. **Cancellation** — each run gets a fresh AbortController; unmounting or
 *     re-running aborts the previous request (wire `signal` into apiFetch).
 *  2. **Stale-response race guard** — if a slow request resolves AFTER a newer
 *     one was kicked off, its result is dropped instead of clobbering the fresh
 *     data (the classic "type fast, see an old page flash back" bug).
 *
 * Plus an opt-in `timeoutMs`. The fetcher receives the run's AbortSignal.
 *
 * @example
 *   const kbs = useAsyncResource(
 *     (signal) => apiFetch<Paginated<KnowledgeBase>>("/v1/rag/knowledge-bases", { signal }),
 *     { timeoutMs: 15_000 },
 *   );
 */
export function useAsyncResource<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: UseAsyncResourceOptions = {},
): AsyncResource<T> {
  const { deps = [], timeoutMs, enabled = true } = options;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // The fetcher is typically an inline arrow that changes every render; keep the
  // latest in a ref so the effect below doesn't re-run on its identity — only on
  // the caller-declared deps / reload / enabled.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // Monotonic run id: only the newest run may commit state (the stale guard).
  const runIdRef = useRef(0);
  const [reloadCount, setReloadCount] = useState(0);

  const reload = useCallback(() => setReloadCount((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }

    const myRunId = ++runIdRef.current;
    const controller = new AbortController();
    // Only a real timeout flips this — so an abort from unmount/supersession
    // (which also aborts the controller) is never misreported as a timeout.
    let timedOut = false;
    const timer =
      timeoutMs !== undefined
        ? setTimeout(() => {
            timedOut = true;
            controller.abort();
          }, timeoutMs)
        : undefined;

    const isCurrent = () => runIdRef.current === myRunId;

    setLoading(true);
    setError(null);

    fetcherRef
      .current(controller.signal)
      .then((result) => {
        if (!isCurrent()) return; // superseded by a newer run
        setData(result);
        setError(null);
        setLoading(false);
      })
      .catch((e: unknown) => {
        // Aborts (unmount, supersession, timeout) are expected — never surface
        // an unmount/supersession abort as a user error. A timeout, however, IS
        // a real failure the user should see.
        if (!isCurrent()) return;
        if (controller.signal.aborted) {
          if (timedOut) {
            setError("Request timed out.");
            setLoading(false);
          }
          return;
        }
        setError(friendlyErrorMessage(e));
        setLoading(false);
      })
      .finally(() => {
        if (timer !== undefined) clearTimeout(timer);
      });

    return () => {
      if (timer !== undefined) clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, timeoutMs, reloadCount, ...deps]);

  return { data, error, loading, reload };
}
