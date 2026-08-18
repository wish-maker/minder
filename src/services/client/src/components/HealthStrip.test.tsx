import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HealthStrip } from "./HealthStrip";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));
vi.mock("react-router-dom", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

afterEach(() => {
  apiFetch.mockReset();
  cleanup();
});

describe("HealthStrip", () => {
  it("renders nothing while the request is in flight before any data resolves", () => {
    apiFetch.mockReturnValue(new Promise(() => {})); // never resolves
    const { container } = render(<HealthStrip />);
    // Skeleton renders a placeholder div, not the real health summary.
    expect(screen.queryByText(/services healthy|All systems healthy/)).toBeNull();
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("renders nothing on a fetch failure (deliberately quiet)", async () => {
    apiFetch.mockRejectedValue(new Error("gateway unreachable"));
    const { container } = render(<HealthStrip />);

    await vi.waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("renders nothing when the service list is empty", async () => {
    apiFetch.mockResolvedValue({ services: [] });
    const { container } = render(<HealthStrip />);

    await vi.waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("renders nothing (not a crash) when the response omits `services` entirely", async () => {
    apiFetch.mockResolvedValue({});
    const { container } = render(<HealthStrip />);

    await vi.waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("shows 'All systems healthy' with a green indicator when every service is up", async () => {
    apiFetch.mockResolvedValue({
      services: [
        { name: "api-gateway", reachable: true, status: "healthy" },
        { name: "model-management", reachable: true, status: "healthy" },
      ],
    });
    render(<HealthStrip />);

    expect(await screen.findByText("All systems healthy")).toBeTruthy();
    expect(screen.getByText("🟢")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /All systems healthy/ }).getAttribute("href"),
    ).toBe("/platform/status");
  });

  it("shows an X/Y count with a yellow indicator when some (not all) services are down", async () => {
    apiFetch.mockResolvedValue({
      services: [
        { name: "api-gateway", reachable: true, status: "healthy" },
        { name: "model-management", reachable: true, status: "degraded" },
      ],
    });
    render(<HealthStrip />);

    expect(await screen.findByText("1/2 services healthy")).toBeTruthy();
    expect(screen.getByText("🟡")).toBeTruthy();
  });

  it("shows a red indicator when no services are healthy", async () => {
    apiFetch.mockResolvedValue({
      services: [
        { name: "api-gateway", reachable: false, status: "unreachable" },
        { name: "model-management", reachable: false, status: "unreachable" },
      ],
    });
    render(<HealthStrip />);

    expect(await screen.findByText("0/2 services healthy")).toBeTruthy();
    expect(screen.getByText("🔴")).toBeTruthy();
  });
});
