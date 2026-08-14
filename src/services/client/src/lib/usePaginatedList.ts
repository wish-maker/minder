import { useCallback, useRef, useState } from "react";

import { friendlyErrorMessage } from "./api";

interface Page<T> {
  items: T[];
  total: number;
}

/** Shared "load a page, then Load More" pagination — the offset/total
 * bookkeeping (replace on filter change vs. append on Load More) was
 * hand-rolled identically in AvailablePluginsPage and AvailableToolsPage. `fetchPage`
 * receives the offset to fetch and must return that page plus the server's
 * total count; the hook owns the state transition.
 *
 * Guards against out-of-order responses (#502): each `load()` takes a
 * monotonic run id and only the newest run may commit — so a search-as-you-type
 * whose earlier request resolves LAST can't render results for the wrong query.
 */
export function usePaginatedList<T>(
  fetchPage: (offset: number) => Promise<Page<T>>,
  pageSize = 20,
) {
  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const runIdRef = useRef(0);

  const load = useCallback(
    async (nextOffset: number, replace: boolean) => {
      const myRun = ++runIdRef.current;
      setStatus("Loading…");
      try {
        const page = await fetchPage(nextOffset);
        if (runIdRef.current !== myRun) return; // superseded by a newer load
        setItems((prev) => (replace ? page.items : [...prev, ...page.items]));
        setTotal(page.total);
        setOffset(nextOffset);
        setStatus("");
      } catch (e) {
        if (runIdRef.current !== myRun) return;
        setStatus(friendlyErrorMessage(e));
      }
    },
    [fetchPage],
  );

  const reload = useCallback(() => load(0, true), [load]);
  const loadMore = useCallback(
    () => load(offset + pageSize, false),
    [load, offset, pageSize],
  );

  return { items, total, status, reload, loadMore, hasMore: items.length < total };
}
