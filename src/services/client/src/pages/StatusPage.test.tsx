import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LogViewer } from "./StatusPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

describe("LogViewer", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("fetches logs only once expanded, not on initial render", () => {
    render(<LogViewer name="minder-rag-pipeline" token="tok" />);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows a login-required hint in the summary when logged out", () => {
    render(<LogViewer name="minder-rag-pipeline" token="" />);
    expect(
      screen.getByText("View recent logs (log in required)"),
    ).toBeTruthy();
  });

  it("fetches and renders stdout/stderr lines distinctly when expanded", async () => {
    apiFetch.mockResolvedValue({
      name: "minder-rag-pipeline",
      lines: [
        { stream: "stdout", text: "started\n" },
        { stream: "stderr", text: "a warning\n" },
      ],
    });
    render(<LogViewer name="minder-rag-pipeline" token="tok" />);

    fireEvent.click(screen.getByText("View recent logs"));

    const stdoutLine = await screen.findByText("started");
    const stderrLine = screen.getByText("a warning");
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/containers/minder-rag-pipeline/logs?tail=200",
      { token: "tok" },
    );
    expect(stdoutLine.className).toContain("text-gray-100");
    expect(stderrLine.className).toContain("text-red-400");
  });

  it('shows "No recent log output." for an empty log response', async () => {
    apiFetch.mockResolvedValue({ name: "x", lines: [] });
    render(<LogViewer name="minder-rag-pipeline" token="tok" />);

    fireEvent.click(screen.getByText("View recent logs"));

    await screen.findByText("No recent log output.");
  });

  it("shows a friendly error when the fetch fails", async () => {
    apiFetch.mockRejectedValue(new Error("Plugin not found in state database"));
    render(<LogViewer name="minder-rag-pipeline" token="tok" />);

    fireEvent.click(screen.getByText("View recent logs"));

    await screen.findByText("Plugin not found in state database");
  });

  it("re-fetches when Refresh is clicked, unlike a plain re-expand", async () => {
    apiFetch
      .mockResolvedValueOnce({
        name: "x",
        lines: [{ stream: "stdout", text: "first batch\n" }],
      })
      .mockResolvedValueOnce({
        name: "x",
        lines: [{ stream: "stdout", text: "second batch\n" }],
      });
    const { container } = render(
      <LogViewer name="minder-rag-pipeline" token="tok" />,
    );
    const details = container.querySelector("details")!;

    fireEvent.click(screen.getByText("View recent logs"));
    await waitFor(() => expect(details.open).toBe(true));
    await screen.findByText("first batch");
    expect(apiFetch).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "↻ Refresh" }));

    await screen.findByText("second batch");
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });

  it("does not re-fetch on a plain re-expand (only Refresh does)", async () => {
    apiFetch.mockResolvedValue({
      name: "x",
      lines: [{ stream: "stdout", text: "hello" }],
    });
    const { container } = render(
      <LogViewer name="minder-rag-pipeline" token="tok" />,
    );
    const details = container.querySelector("details")!;
    const summary = screen.getByText("View recent logs");

    // jsdom's native <details> "toggle" event resolves asynchronously
    // relative to fireEvent.click -- each click must be awaited to settle
    // before the next, or two rapid clicks can net out to no observed state
    // change and this test would pass even with the `loaded` guard removed
    // (confirmed with ChunkViewer's equivalent test earlier this session).
    fireEvent.click(summary); // open
    await waitFor(() => expect(details.open).toBe(true));
    await screen.findByText("hello");

    fireEvent.click(summary); // close
    await waitFor(() => expect(details.open).toBe(false));

    fireEvent.click(summary); // re-open
    await waitFor(() => expect(details.open).toBe(true));

    expect(apiFetch).toHaveBeenCalledTimes(1);
  });
});
