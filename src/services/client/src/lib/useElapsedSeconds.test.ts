import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { formatElapsed, useElapsedSeconds } from "./useElapsedSeconds";

describe("formatElapsed", () => {
  it("renders sub-minute durations as plain seconds", () => {
    expect(formatElapsed(0)).toBe("0s");
    expect(formatElapsed(45)).toBe("45s");
  });

  it("renders minutes with zero-padded seconds once past a minute", () => {
    expect(formatElapsed(60)).toBe("1m00s");
    expect(formatElapsed(134)).toBe("2m14s");
  });
});

describe("useElapsedSeconds", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("stays at 0 while inactive", () => {
    const { result } = renderHook(() => useElapsedSeconds(false));
    expect(result.current).toBe(0);
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current).toBe(0);
  });

  it("ticks up once per second while active", () => {
    const { result } = renderHook(() => useElapsedSeconds(true));
    expect(result.current).toBe(0);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(1);
    act(() => vi.advanceTimersByTime(2000));
    expect(result.current).toBe(3);
  });

  it("resets to 0 when active flips back to false", () => {
    const { result, rerender } = renderHook(({ active }) => useElapsedSeconds(active), {
      initialProps: { active: true },
    });
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current).toBe(5);
    rerender({ active: false });
    expect(result.current).toBe(0);
  });
});
