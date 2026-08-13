import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function Boom({ message }: { message: string }): never {
  throw new Error(message);
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    // React logs caught render errors to console.error; silence it so the test
    // output isn't noisy (the boundary itself also logs via componentDidCatch).
    vi.spyOn(console, "error").mockImplementation(() => {});
  });
  afterEach(() => {
    // No globals/setupFile in vitest.config → testing-library's auto-cleanup
    // isn't registered; unmount + restore the console spy explicitly so the
    // rendered DOM doesn't leak between tests.
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders its children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("all good")).toBeTruthy();
  });

  it("shows a recoverable fallback (with the message) when a child throws", () => {
    render(
      <ErrorBoundary>
        <Boom message="map is not a function" />
      </ErrorBoundary>,
    );

    const alert = screen.getByRole("alert");
    expect(alert).toBeTruthy();
    expect(alert.textContent).toContain("unexpected error");
    expect(alert.textContent).toContain("map is not a function");
    // The recovery affordances are present.
    expect(screen.getByText("Reload")).toBeTruthy();
    expect(screen.getByText("Try again")).toBeTruthy();
  });
});
