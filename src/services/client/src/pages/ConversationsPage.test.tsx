import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConversationsPage } from "./ConversationsPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

let mockAuth = { token: "" };
vi.mock("../lib/auth", () => ({
  useAuth: () => mockAuth,
}));

const navigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
}));

function conversation(overrides: Partial<{
  conversation_id: string;
  last_activity: string;
  snippet: string;
}> = {}) {
  return {
    conversation_id: overrides.conversation_id ?? "conv-1",
    last_activity: overrides.last_activity ?? "2026-01-01T00:00:00Z",
    snippet: overrides.snippet ?? "what is the refund policy?",
  };
}

describe("ConversationsPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    navigate.mockReset();
    cleanup();
  });

  it("prompts to log in and never fetches when there's no token", () => {
    mockAuth = { token: "" };
    render(<ConversationsPage />);

    expect(
      screen.getByText("Log in to see your conversation history."),
    ).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("shows an empty state when the caller has no conversations", async () => {
    mockAuth = { token: "tok" };
    apiFetch.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    render(<ConversationsPage />);

    await screen.findByText(
      /No conversations yet — start one from a pipeline's Query panel/,
    );
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/conversations/mine?limit=20&offset=0",
      { token: "tok" },
    );
  });

  it("renders a card per conversation with its snippet and last-activity time", async () => {
    mockAuth = { token: "tok" };
    apiFetch.mockResolvedValue({
      items: [
        conversation({ conversation_id: "conv-1", snippet: "what is the refund policy?" }),
        conversation({ conversation_id: "conv-2", snippet: "how do I reset my password?" }),
      ],
      total: 2,
      limit: 20,
      offset: 0,
    });
    render(<ConversationsPage />);

    await screen.findByText("what is the refund policy?");
    expect(screen.getByText("how do I reset my password?")).toBeTruthy();
  });

  it("falls back to a placeholder when a conversation has no snippet", async () => {
    mockAuth = { token: "tok" };
    apiFetch.mockResolvedValue({
      items: [conversation({ snippet: "" })],
      total: 1,
      limit: 20,
      offset: 0,
    });
    render(<ConversationsPage />);

    await screen.findByText("(no question recorded)");
  });

  it("navigates to Pipelines with the chosen conversation_id when Continue is clicked", async () => {
    mockAuth = { token: "tok" };
    apiFetch.mockResolvedValue({
      items: [conversation({ conversation_id: "conv-xyz" })],
      total: 1,
      limit: 20,
      offset: 0,
    });
    render(<ConversationsPage />);

    await screen.findByText("what is the refund policy?");
    fireEvent.click(screen.getByText("Continue →"));

    expect(navigate).toHaveBeenCalledWith(
      "/rag/pipelines?conversation_id=conv-xyz",
    );
  });

  it("shows a Load more button when more results exist, and fetches the next page", async () => {
    mockAuth = { token: "tok" };
    apiFetch.mockResolvedValueOnce({
      items: [conversation({ conversation_id: "conv-1" })],
      total: 2,
      limit: 20,
      offset: 0,
    });
    render(<ConversationsPage />);
    await screen.findByText("what is the refund policy?");

    apiFetch.mockResolvedValueOnce({
      items: [conversation({ conversation_id: "conv-2", snippet: "second one" })],
      total: 2,
      limit: 20,
      offset: 20,
    });
    fireEvent.click(screen.getByText("Load more"));

    await screen.findByText("second one");
    expect(apiFetch).toHaveBeenLastCalledWith(
      "/v1/conversations/mine?limit=20&offset=20",
      { token: "tok" },
    );
  });

  it("shows a friendly status message when the fetch fails", async () => {
    mockAuth = { token: "tok" };
    apiFetch.mockRejectedValue(new Error("network down"));
    render(<ConversationsPage />);

    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText("network down")).toBeTruthy();
  });
});
