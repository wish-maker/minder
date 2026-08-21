import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { licenseStatus, MyLicensesPage, type License } from "./MyLicensesPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

// Mutable per test, same convention as SubmissionsPage.test.tsx.
let mockAuth = { token: "", isAuthenticated: false };
vi.mock("../lib/auth", () => ({
  useAuth: () => mockAuth,
}));

function license(overrides: Partial<License> = {}): License {
  return {
    id: "l1",
    plugin_id: "p1",
    plugin_name: "weather",
    plugin_display_name: "Weather",
    tier: "pro",
    valid_from: "2026-01-01T00:00:00Z",
    valid_until: "2027-01-01T00:00:00Z",
    active: true,
    usage_count: 3,
    last_used_at: null,
    ...overrides,
  };
}

describe("MyLicensesPage", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("prompts a logged-out user to log in instead of fetching anything", () => {
    mockAuth = { token: "", isAuthenticated: false };
    render(<MyLicensesPage />);

    expect(screen.getByText(/Log in to see your plugin licenses/i)).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("loads and renders the caller's own licenses", async () => {
    mockAuth = { token: "tok", isAuthenticated: true };
    apiFetch.mockResolvedValue({ licenses: [license()], count: 1 });

    render(<MyLicensesPage />);

    await screen.findByText("Weather");
    expect(apiFetch).toHaveBeenCalledWith("/v1/marketplace/licenses", {
      token: "tok",
    });
    expect(screen.getByText("pro")).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
  });

  it("shows an honest empty state when the caller has no licenses", async () => {
    mockAuth = { token: "tok", isAuthenticated: true };
    apiFetch.mockResolvedValue({ licenses: [], count: 0 });

    render(<MyLicensesPage />);

    await screen.findByText(/You don't have any plugin licenses yet/);
  });

  it("never renders an activate/upgrade control", async () => {
    mockAuth = { token: "tok", isAuthenticated: true };
    apiFetch.mockResolvedValue({ licenses: [license()], count: 1 });

    render(<MyLicensesPage />);

    await screen.findByText("Weather");
    expect(screen.queryByRole("button", { name: /activate|upgrade/i })).toBeNull();
  });

  it("shows an error status line when the fetch fails", async () => {
    mockAuth = { token: "tok", isAuthenticated: true };
    apiFetch.mockRejectedValue(new Error("network down"));

    render(<MyLicensesPage />);

    await screen.findByText("network down");
  });
});

describe("licenseStatus", () => {
  it("is Active for an active, unexpired license", () => {
    expect(licenseStatus(license()).label).toBe("Active");
  });

  it("is Inactive when active=false, even if not yet expired", () => {
    expect(licenseStatus(license({ active: false })).label).toBe("Inactive");
  });

  it("is Expired when active=true but valid_until is in the past", () => {
    expect(
      licenseStatus(license({ valid_until: "2020-01-01T00:00:00Z" })).label,
    ).toBe("Expired");
  });

  it("is Active when valid_until is null (no expiry)", () => {
    expect(licenseStatus(license({ valid_until: null })).label).toBe("Active");
  });
});
