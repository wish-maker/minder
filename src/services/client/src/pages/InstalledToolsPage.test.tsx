import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../lib/api";
import { InstalledToolsPage, TryItPanel, type LiveTool } from "./InstalledToolsPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", async () => {
  const actual =
    await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    apiFetch: (...args: unknown[]) => apiFetch(...args),
  };
});
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ token: "test-token" }),
}));

function tool(overrides: Partial<LiveTool["metadata"]> = {}): LiveTool {
  return {
    type: "function",
    function: {
      name: "get_weather",
      description: "Get the current weather",
      parameters: {
        type: "object",
        properties: { city: { type: "string" } },
        required: ["city"],
      },
    },
    metadata: {
      plugin: "weather",
      endpoint: "/v1/plugins/weather/actions/get_weather",
      method: "POST",
      ...overrides,
    },
  };
}

async function openAndRun(paramsText?: string) {
  fireEvent.click(screen.getByText("▶ Try it"));
  if (paramsText !== undefined) {
    fireEvent.change(
      screen.getByLabelText("Example parameters — edit, then Run"),
      { target: { value: paramsText } },
    );
  }
  fireEvent.click(screen.getByRole("button", { name: /Run/ }));
}

describe("TryItPanel", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("pre-fills a schema-derived example the user can edit", () => {
    render(<TryItPanel tool={tool()} token="tok" />);
    fireEvent.click(screen.getByText("▶ Try it"));
    const textarea = screen.getByLabelText(
      "Example parameters — edit, then Run",
    ) as HTMLTextAreaElement;
    expect(JSON.parse(textarea.value)).toEqual({ city: "" });
  });

  it("sends params as a query string for a GET tool", async () => {
    apiFetch.mockResolvedValue({ temp: 72 });
    render(<TryItPanel tool={tool({ method: "GET" })} token="tok" />);
    await openAndRun('{"city": "san-francisco"}');

    await screen.findByText(/"temp": 72/);
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/plugins/weather/actions/get_weather?city=san-francisco",
      { method: "GET", token: "tok" },
    );
  });

  it("sends params as a JSON body for a non-GET tool", async () => {
    apiFetch.mockResolvedValue({ ok: true });
    render(<TryItPanel tool={tool({ method: "POST" })} token="tok" />);
    await openAndRun('{"city": "san-francisco"}');

    await screen.findByText(/"ok": true/);
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/plugins/weather/actions/get_weather",
      { method: "POST", body: { city: "san-francisco" }, token: "tok" },
    );
  });

  it("warns that a non-GET tool may change data", () => {
    render(<TryItPanel tool={tool({ method: "POST" })} token="tok" />);
    fireEvent.click(screen.getByText("▶ Try it"));
    expect(
      screen.getByText(/it may change data, not just read it/),
    ).toBeTruthy();
  });

  it("does not warn for a GET tool", () => {
    render(<TryItPanel tool={tool({ method: "GET" })} token="tok" />);
    fireEvent.click(screen.getByText("▶ Try it"));
    expect(
      screen.queryByText(/it may change data, not just read it/),
    ).toBeNull();
  });

  it("rejects non-object JSON with a clear message, without calling the tool", async () => {
    render(<TryItPanel tool={tool()} token="tok" />);
    fireEvent.click(screen.getByText("▶ Try it"));
    fireEvent.change(
      screen.getByLabelText("Example parameters — edit, then Run"),
      { target: { value: "[1, 2, 3]" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    await screen.findByText(/Parameters must be a JSON object/);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows a JSON-syntax-specific error for invalid JSON", async () => {
    render(<TryItPanel tool={tool()} token="tok" />);
    fireEvent.click(screen.getByText("▶ Try it"));
    fireEvent.change(
      screen.getByLabelText("Example parameters — edit, then Run"),
      { target: { value: "{not json" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Run/ }));

    await screen.findByText(/That's not valid JSON:/);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows the friendly message for an ApiError", async () => {
    apiFetch.mockRejectedValue(new ApiError("Tool is not enabled", 403));
    render(<TryItPanel tool={tool()} token="tok" />);
    await openAndRun();

    await screen.findByText("Tool is not enabled");
  });
});

describe("InstalledToolsPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("shows an empty state when no plugin exposes a live tool", async () => {
    apiFetch.mockResolvedValue({ tools: [] });
    render(<InstalledToolsPage />);

    await screen.findByText("No plugin is currently exposing an AI tool.");
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/plugins/ai/tools",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("renders a LiveToolCard per live tool, including its Try It panel", async () => {
    apiFetch.mockResolvedValue({ tools: [tool({ plugin: "weather" }), tool({ plugin: "news" })] });
    render(<InstalledToolsPage />);

    const cards = await screen.findAllByText("get_weather");
    expect(cards).toHaveLength(2);
    expect(screen.getAllByText("weather").length + screen.getAllByText("news").length).toBe(2);
    // Each card renders its own collapsed Try It panel.
    expect(screen.getAllByText("▶ Try it")).toHaveLength(2);
  });

  it("falls back to a placeholder when a live tool has no description", async () => {
    apiFetch.mockResolvedValue({
      tools: [
        {
          ...tool(),
          function: { ...tool().function, description: "" },
        },
      ],
    });
    render(<InstalledToolsPage />);

    await screen.findByText("No description provided.");
  });

  it("shows a friendly error message when the live-tools fetch fails", async () => {
    apiFetch.mockRejectedValue(new Error("plugin-registry unreachable"));
    render(<InstalledToolsPage />);

    await screen.findByText("plugin-registry unreachable");
  });

  it("renders (does not crash) when the response omits `tools` entirely", async () => {
    apiFetch.mockResolvedValue({});
    render(<InstalledToolsPage />);

    await screen.findByText("No plugin is currently exposing an AI tool.");
  });
});
