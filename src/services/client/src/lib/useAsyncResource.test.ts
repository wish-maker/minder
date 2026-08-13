import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAsyncResource } from "./useAsyncResource";

/** A promise plus its resolve/reject handles, so a test can control exactly
 * when (and in what order) a fetch settles. */
function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

afterEach(() => vi.useRealTimers());

describe("useAsyncResource", () => {
  it("resolves to data, clearing loading and error", async () => {
    const { result } = renderHook(() =>
      useAsyncResource(() => Promise.resolve(42)),
    );

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBe(42);
    expect(result.current.error).toBeNull();
  });

  it("does not fetch while disabled", async () => {
    const fetcher = vi.fn(() => Promise.resolve("x"));
    const { result } = renderHook(() =>
      useAsyncResource(fetcher, { enabled: false }),
    );

    await Promise.resolve();
    expect(fetcher).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it("surfaces a failed fetch as a user-facing error string", async () => {
    const { result } = renderHook(() =>
      useAsyncResource(() => Promise.reject(new Error("boom"))),
    );

    await waitFor(() => expect(result.current.error).toBe("boom"));
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
  });

  it("drops a stale response when a newer run supersedes it", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const calls = [first, second];
    let call = 0;
    const fetcher = () => calls[call++].promise;

    const { result, rerender } = renderHook(
      ({ dep }) => useAsyncResource(fetcher, { deps: [dep] }),
      { initialProps: { dep: 1 } },
    );

    // Kick off the second run (supersedes the first) before either resolves.
    rerender({ dep: 2 });

    // Resolve the NEWER run first, then the older/slower one.
    await act(async () => {
      second.resolve("fresh");
    });
    await waitFor(() => expect(result.current.data).toBe("fresh"));

    await act(async () => {
      first.resolve("stale");
    });
    // The late "stale" result must NOT clobber the fresh data.
    expect(result.current.data).toBe("fresh");
  });

  it("reports a timeout when the request exceeds timeoutMs", async () => {
    vi.useFakeTimers();
    // A fetch that respects the abort signal but otherwise never settles.
    const fetcher = (signal: AbortSignal) =>
      new Promise<string>((_resolve, reject) => {
        signal.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        );
      });

    const { result } = renderHook(() =>
      useAsyncResource(fetcher, { timeoutMs: 1000 }),
    );

    // advanceTimersByTimeAsync flushes the microtasks between timers, so the
    // abort → reject → catch → setError chain runs. (Plain waitFor can't be used
    // under fake timers — its own polling clock never advances.)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(result.current.error).toBe("Request timed out.");
    expect(result.current.loading).toBe(false);
  });

  it("re-runs the fetcher when reload() is called", async () => {
    const fetcher = vi.fn(() => Promise.resolve("v"));
    const { result } = renderHook(() => useAsyncResource(fetcher));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetcher).toHaveBeenCalledTimes(1);

    act(() => result.current.reload());
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });

  it("aborts the in-flight request on unmount", async () => {
    let capturedSignal: AbortSignal | undefined;
    const fetcher = (signal: AbortSignal) => {
      capturedSignal = signal;
      return new Promise<string>(() => {}); // never settles
    };

    const { unmount } = renderHook(() => useAsyncResource(fetcher));
    expect(capturedSignal?.aborted).toBe(false);

    unmount();
    expect(capturedSignal?.aborted).toBe(true);
  });
});
