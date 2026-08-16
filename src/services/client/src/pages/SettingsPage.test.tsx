import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./SettingsPage";

const logout = vi.fn();
let isAuthenticated = true;
let autheliaPortalUrl: string | null = "https://auth.minder.local/";

vi.mock("../lib/auth", () => ({
  useAuth: () => ({
    isAuthenticated,
    username: "alice",
    email: "alice@example.com",
    role: "admin",
    logout,
  }),
}));
vi.mock("react-router-dom", () => ({
  Navigate: ({ to, replace }: { to: string; replace?: boolean }) => (
    <div data-testid="navigate" data-to={to} data-replace={String(replace)} />
  ),
}));
vi.mock("../lib/api", () => ({
  get autheliaPortalUrl() {
    return autheliaPortalUrl;
  },
}));

describe("SettingsPage", () => {
  beforeEach(() => {
    logout.mockClear();
    isAuthenticated = true;
    autheliaPortalUrl = "https://auth.minder.local/";
  });
  afterEach(() => cleanup());

  it("redirects home when not authenticated", () => {
    isAuthenticated = false;
    render(<SettingsPage />);
    const nav = screen.getByTestId("navigate");
    expect(nav.dataset.to).toBe("/");
    expect(nav.dataset.replace).toBe("true");
  });

  it("displays the current JWT claims", () => {
    render(<SettingsPage />);
    expect(screen.getByText("alice")).toBeTruthy();
    expect(screen.getByText("alice@example.com")).toBeTruthy();
    expect(screen.getByText("admin")).toBeTruthy();
  });

  it("calls logout() when Log out is clicked", () => {
    render(<SettingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Log out" }));
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it("links to Authelia's portal when configured", () => {
    render(<SettingsPage />);
    const link = screen.getByRole("link", { name: "Authelia's own portal" });
    expect(link.getAttribute("href")).toBe("https://auth.minder.local/");
  });

  it("falls back to plain text when no Authelia portal is configured", () => {
    autheliaPortalUrl = null;
    render(<SettingsPage />);
    expect(
      screen.queryByRole("link", { name: "Authelia's own portal" }),
    ).toBeNull();
    expect(
      screen.getByText(/your identity provider's portal \(Authelia\)/),
    ).toBeTruthy();
  });
});
