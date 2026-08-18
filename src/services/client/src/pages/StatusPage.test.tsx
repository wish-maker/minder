import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LogViewer, StatusPage } from "./StatusPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ token: "test-token" }),
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

describe("StatusPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("shows a loading state, then an empty state when no services are reported", async () => {
    apiFetch.mockResolvedValue({ services: [] });
    render(<StatusPage />);

    expect(screen.getByText("Loading…")).toBeTruthy();
    await screen.findByText("No services reported by the server.");
  });

  it("shows a friendly error when the status fetch fails", async () => {
    apiFetch.mockRejectedValue(new Error("api-gateway unreachable"));
    render(<StatusPage />);

    await screen.findByText("api-gateway unreachable");
  });

  it("renders a service card with version, error, and dependency checks", async () => {
    apiFetch.mockResolvedValue({
      services: [
        {
          name: "rag-pipeline",
          reachable: true,
          status: "degraded",
          version: "1.4.2",
          checks: { postgres: "ok", qdrant: "slow" },
          error: "qdrant latency above threshold",
        },
      ],
    });
    render(<StatusPage />);

    await screen.findByText("rag-pipeline");
    expect(screen.getByText("degraded")).toBeTruthy();
    expect(screen.getByText("reported v1.4.2")).toBeTruthy();
    expect(screen.getByText("qdrant latency above threshold")).toBeTruthy();
    expect(screen.getByText("postgres: ok")).toBeTruthy();
    expect(screen.getByText("qdrant: slow")).toBeTruthy();
    // Logged in (mocked token above) -- LogViewer should offer the real
    // action, not the "log in required" hint.
    expect(screen.getByText("View recent logs")).toBeTruthy();
  });

  it("renders one card per service, unreachable ones included", async () => {
    apiFetch.mockResolvedValue({
      services: [
        { name: "api-gateway", reachable: true, status: "healthy" },
        { name: "tts-stt", reachable: false, status: "unreachable" },
      ],
    });
    render(<StatusPage />);

    await screen.findByText("api-gateway");
    expect(screen.getByText("tts-stt")).toBeTruthy();
    expect(screen.getByText("unreachable")).toBeTruthy();
  });

  it("re-fetches when the page-level Refresh button is clicked", async () => {
    apiFetch
      .mockResolvedValueOnce({ services: [{ name: "svc-a", reachable: true, status: "healthy" }] })
      .mockResolvedValueOnce({ services: [{ name: "svc-b", reachable: true, status: "healthy" }] });
    render(<StatusPage />);

    await screen.findByText("svc-a");
    fireEvent.click(screen.getByRole("button", { name: "🔄 Refresh" }));

    await screen.findByText("svc-b");
    expect(apiFetch).toHaveBeenCalledTimes(2);
  });
});
