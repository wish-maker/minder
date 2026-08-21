import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "./Sidebar";

// Mutable per test (like AvailablePluginsPage.test.tsx's mockAuth) so both
// the non-admin (default) and admin (Review Queue visible) paths are covered.
let mockAuth = { role: "" };
vi.mock("../lib/auth", () => ({
  useAuth: () => mockAuth,
}));

describe("Sidebar", () => {
  beforeEach(() => {
    mockAuth = { role: "" };
  });
  afterEach(cleanup);

  it("links the wordmark to home and every section's nav items to their routes", () => {
    render(
      <MemoryRouter>
        <Sidebar open={false} onNavigate={() => {}} />
      </MemoryRouter>,
    );

    expect(screen.getByText("Minder").closest("a")?.getAttribute("href")).toBe("/");
    expect(
      screen.getByText("Knowledge Bases").closest("a")?.getAttribute("href"),
    ).toBe("/rag");
    expect(
      screen.getByText("Pipelines").closest("a")?.getAttribute("href"),
    ).toBe("/rag/pipelines");
    expect(
      screen.getByText("Available Tools").closest("a")?.getAttribute("href"),
    ).toBe("/ai-tools/available");
    expect(
      screen.getByText("Available Bundles").closest("a")?.getAttribute("href"),
    ).toBe("/bundles/available");
    expect(screen.getByText("Models").closest("a")?.getAttribute("href")).toBe(
      "/platform",
    );
  });

  it("renders every section label", () => {
    render(
      <MemoryRouter>
        <Sidebar open={false} onNavigate={() => {}} />
      </MemoryRouter>,
    );

    for (const label of ["RAG", "Plugins", "AI Tools", "Bundles", "Platform"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("calls onNavigate when a nav link is clicked", () => {
    const onNavigate = vi.fn();
    render(
      <MemoryRouter>
        <Sidebar open={true} onNavigate={onNavigate} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("Pipelines"));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it("calls onNavigate when the wordmark is clicked", () => {
    const onNavigate = vi.fn();
    render(
      <MemoryRouter>
        <Sidebar open={true} onNavigate={onNavigate} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("Minder"));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });

  it("translates on/off screen based on the open prop", () => {
    const { rerender } = render(
      <MemoryRouter>
        <Sidebar open={false} onNavigate={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Minder").closest("aside")?.className).toContain(
      "-translate-x-full",
    );

    rerender(
      <MemoryRouter>
        <Sidebar open={true} onNavigate={() => {}} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Minder").closest("aside")?.className).toContain(
      "translate-x-0",
    );
  });

  it("marks the active route's link distinctly from inactive ones", () => {
    render(
      <MemoryRouter initialEntries={["/rag/pipelines"]}>
        <Sidebar open={false} onNavigate={() => {}} />
      </MemoryRouter>,
    );

    expect(screen.getByText("Pipelines").className).toContain("bg-indigo-50");
    expect(screen.getByText("Knowledge Bases").className).not.toContain(
      "bg-indigo-50",
    );
  });

  it("shows Submit a Plugin to everyone but hides Review Queue from a non-admin", () => {
    render(
      <MemoryRouter>
        <Sidebar open={false} onNavigate={() => {}} />
      </MemoryRouter>,
    );

    expect(screen.getByText("Submit a Plugin")).toBeTruthy();
    expect(screen.queryByText("Review Queue")).toBeNull();
  });

  it("shows Review Queue to an admin", () => {
    mockAuth = { role: "admin" };
    render(
      <MemoryRouter>
        <Sidebar open={false} onNavigate={() => {}} />
      </MemoryRouter>,
    );

    expect(
      screen.getByText("Review Queue").closest("a")?.getAttribute("href"),
    ).toBe("/plugins/review");
  });
});
