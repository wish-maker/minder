import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReviewQueuePage } from "./ReviewQueuePage";
import type { Submission } from "./SubmissionsPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

// Mutable per test, same convention as AvailablePluginsPage.test.tsx.
let mockAuth = { token: "", role: "", isAuthenticated: false };
vi.mock("../lib/auth", () => ({
  useAuth: () => mockAuth,
}));

function submission(overrides: Partial<Submission> = {}): Submission {
  return {
    id: "s1",
    name: "weather-plus",
    display_name: "Weather Plus",
    description: "A better weather plugin",
    author: "dev1",
    repository_url: null,
    distribution_type: "docker",
    docker_image: "org/weather-plus:latest",
    pricing_model: "free",
    base_tier: "community",
    status: "submitted",
    review_notes: null,
    requires_services: [],
    ...overrides,
  };
}

describe("ReviewQueuePage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("tells a non-admin the page is admins-only and never fetches", () => {
    mockAuth = { token: "tok", role: "user", isAuthenticated: true };
    render(<ReviewQueuePage />);

    expect(screen.getByText(/Admins only/)).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("tells a logged-out visitor the page is admins-only and never fetches", () => {
    mockAuth = { token: "", role: "", isAuthenticated: false };
    render(<ReviewQueuePage />);

    expect(screen.getByText(/Admins only/)).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("loads the submitted queue by default for an admin", async () => {
    mockAuth = { token: "tok", role: "admin", isAuthenticated: true };
    apiFetch.mockResolvedValue({ plugins: [submission()] });

    render(<ReviewQueuePage />);

    await screen.findByText("Weather Plus");
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/marketplace/submissions?status=submitted",
      { token: "tok" },
    );
  });

  it("re-fetches when the status filter changes", async () => {
    mockAuth = { token: "tok", role: "admin", isAuthenticated: true };
    apiFetch.mockResolvedValue({ plugins: [] });

    render(<ReviewQueuePage />);
    await screen.findByText(/No submissions in status/);

    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "approved" },
    });

    await vi.waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/marketplace/submissions?status=approved",
        { token: "tok" },
      ),
    );
  });

  it("shows Claim and Reject for a submitted item, and claims it", async () => {
    mockAuth = { token: "tok", role: "admin", isAuthenticated: true };
    apiFetch.mockResolvedValueOnce({ plugins: [submission({ status: "submitted" })] });
    apiFetch.mockResolvedValueOnce({}); // claim
    apiFetch.mockResolvedValueOnce({ plugins: [submission({ status: "in_review" })] });

    render(<ReviewQueuePage />);
    await screen.findByRole("button", { name: "Claim" });
    expect(screen.getByRole("button", { name: "Reject" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Claim" }));

    await vi.waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/marketplace/submissions/s1/claim",
        { method: "POST", token: "tok", body: undefined },
      ),
    );
  });

  it("shows Approve and Reject for an in_review item, and approves it", async () => {
    mockAuth = { token: "tok", role: "admin", isAuthenticated: true };
    apiFetch.mockResolvedValueOnce({ plugins: [submission({ status: "in_review" })] });
    apiFetch.mockResolvedValueOnce({}); // approve
    apiFetch.mockResolvedValueOnce({ plugins: [submission({ status: "approved" })] });

    render(<ReviewQueuePage />);
    await screen.findByRole("button", { name: "Approve" });

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await vi.waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/marketplace/submissions/s1/approve",
        { method: "POST", token: "tok", body: undefined },
      ),
    );
  });

  it("requires notes before confirming a reject", async () => {
    mockAuth = { token: "tok", role: "admin", isAuthenticated: true };
    apiFetch.mockResolvedValueOnce({ plugins: [submission({ status: "in_review" })] });

    render(<ReviewQueuePage />);
    await screen.findByRole("button", { name: "Reject" });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    const confirmButton = screen.getByRole("button", { name: "Confirm reject" });
    expect(confirmButton.hasAttribute("disabled")).toBe(true);

    fireEvent.change(
      screen.getByLabelText("Feedback for the developer (required)"),
      { target: { value: "Please fix X" } },
    );
    expect(confirmButton.hasAttribute("disabled")).toBe(false);

    apiFetch.mockResolvedValueOnce({}); // reject
    apiFetch.mockResolvedValueOnce({ plugins: [] });
    fireEvent.click(confirmButton);

    await vi.waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/marketplace/submissions/s1/reject",
        { method: "POST", token: "tok", body: { notes: "Please fix X" } },
      ),
    );
  });

  it("shows only Archive for an approved item", async () => {
    mockAuth = { token: "tok", role: "admin", isAuthenticated: true };
    apiFetch.mockResolvedValue({ plugins: [submission({ status: "approved" })] });

    render(<ReviewQueuePage />);
    await screen.findByRole("button", { name: "Archive" });
    expect(screen.queryByRole("button", { name: "Claim" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("shows no reviewer action for a draft or rejected item", async () => {
    mockAuth = { token: "tok", role: "admin", isAuthenticated: true };
    apiFetch.mockResolvedValue({ plugins: [submission({ status: "draft" })] });

    render(<ReviewQueuePage />);

    await screen.findByText("No reviewer action available in this status.");
  });
});
