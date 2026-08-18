import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AvailableToolsPage } from "./AvailableToolsPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", async () => {
  const actual =
    await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    apiFetch: (...args: unknown[]) => apiFetch(...args),
  };
});

function tool(overrides: {
  id?: string;
  tool_name?: string;
  active?: boolean;
  description?: string | null;
} = {}) {
  return {
    id: overrides.id ?? "t1",
    plugin_id: "p1",
    plugin_name: "weather",
    plugin_display_name: "Weather",
    tool_name: overrides.tool_name ?? "get_weather",
    type: "function",
    description:
      "description" in overrides ? overrides.description! : "Get the current weather",
    endpoint: "/v1/plugins/weather/actions/get_weather",
    method: "GET",
    required_tier: "free",
    active: overrides.active ?? true,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AvailableToolsPage />
    </MemoryRouter>,
  );
}

describe("AvailableToolsPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("shows an empty state when the catalog has no tools", async () => {
    apiFetch.mockResolvedValue({ tools: [], count: 0, total: 0, limit: 20, offset: 0 });
    renderPage();

    await screen.findByText("No AI tools in the catalog yet.");
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/marketplace/ai/tools?active_only=false&limit=20&offset=0",
    );
  });

  it("renders a card per catalog tool, including an inactive badge", async () => {
    apiFetch.mockResolvedValue({
      tools: [tool({ id: "t1" }), tool({ id: "t2", tool_name: "send_email", active: false })],
      count: 2,
      total: 2,
      limit: 20,
      offset: 0,
    });
    renderPage();

    await screen.findByText("get_weather");
    expect(screen.getByText("send_email")).toBeTruthy();
    expect(screen.getByText("inactive")).toBeTruthy();
  });

  it("falls back to a placeholder when a tool has no description", async () => {
    apiFetch.mockResolvedValue({
      tools: [tool({ description: null })],
      count: 1,
      total: 1,
      limit: 20,
      offset: 0,
    });
    renderPage();

    await screen.findByText("No description provided.");
  });

  it("shows a Load more button when more results exist, and fetches the next page", async () => {
    apiFetch.mockResolvedValueOnce({
      tools: [tool({ id: "t1" })],
      count: 1,
      total: 2,
      limit: 20,
      offset: 0,
    });
    renderPage();
    await screen.findByText("get_weather");

    apiFetch.mockResolvedValueOnce({
      tools: [tool({ id: "t2", tool_name: "send_email" })],
      count: 1,
      total: 2,
      limit: 20,
      offset: 20,
    });
    fireEvent.click(screen.getByText("Load more"));

    await screen.findByText("send_email");
    expect(apiFetch).toHaveBeenLastCalledWith(
      "/v1/marketplace/ai/tools?active_only=false&limit=20&offset=20",
    );
  });

  it("does not show Load more once every result has loaded", async () => {
    apiFetch.mockResolvedValue({
      tools: [tool()],
      count: 1,
      total: 1,
      limit: 20,
      offset: 0,
    });
    renderPage();

    await screen.findByText("get_weather");
    expect(screen.queryByText("Load more")).toBeNull();
  });

  it("shows a friendly status message when the fetch fails", async () => {
    apiFetch.mockRejectedValue(new Error("network down"));
    renderPage();

    await waitFor(() =>
      expect(screen.queryByText("Loading…")).toBeNull(),
    );
  });
});
