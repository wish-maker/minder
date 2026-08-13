import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePaginatedList } from "./usePaginatedList";

describe("usePaginatedList", () => {
  it("reload() loads the first page and reports hasMore from the total", async () => {
    const fetchPage = vi.fn(async (offset: number) => ({
      items: [`a${offset}`, `b${offset}`],
      total: 5,
    }));
    const { result } = renderHook(() => usePaginatedList(fetchPage, 2));

    await act(async () => {
      await result.current.reload();
    });

    expect(fetchPage).toHaveBeenCalledWith(0);
    expect(result.current.items).toEqual(["a0", "b0"]);
    expect(result.current.total).toBe(5);
    expect(result.current.status).toBe("");
    expect(result.current.hasMore).toBe(true); // 2 of 5 loaded
  });

  it("loadMore() appends the next page at offset += pageSize", async () => {
    const fetchPage = vi.fn(async (offset: number) => ({
      items: offset === 0 ? ["a", "b"] : ["c", "d"],
      total: 4,
    }));
    const { result } = renderHook(() => usePaginatedList(fetchPage, 2));

    await act(async () => {
      await result.current.reload();
    });
    await act(async () => {
      await result.current.loadMore();
    });

    expect(fetchPage).toHaveBeenLastCalledWith(2);
    expect(result.current.items).toEqual(["a", "b", "c", "d"]);
    expect(result.current.hasMore).toBe(false); // 4 of 4 loaded
  });

  it("reload() replaces rather than appends (filter-change semantics)", async () => {
    let batch = ["first"];
    const fetchPage = vi.fn(async () => ({ items: batch, total: 1 }));
    const { result } = renderHook(() => usePaginatedList(fetchPage));

    await act(async () => {
      await result.current.reload();
    });
    expect(result.current.items).toEqual(["first"]);

    batch = ["second"];
    await act(async () => {
      await result.current.reload();
    });
    expect(result.current.items).toEqual(["second"]); // replaced, not ["first","second"]
  });

  it("surfaces a fetch failure via status and leaves items intact", async () => {
    const fetchPage = vi.fn(async () => {
      throw new Error("nope");
    });
    const { result } = renderHook(() => usePaginatedList(fetchPage));

    await act(async () => {
      await result.current.reload();
    });

    await waitFor(() => expect(result.current.status).toBe("nope"));
    expect(result.current.items).toEqual([]);
  });
});
