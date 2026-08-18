import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UserMenu } from "./UserMenu";

const useAuth = vi.fn();

vi.mock("../lib/auth", () => ({
  useAuth: () => useAuth(),
}));

function renderMenu() {
  return render(
    <MemoryRouter>
      <UserMenu />
    </MemoryRouter>,
  );
}

describe("UserMenu", () => {
  afterEach(() => {
    useAuth.mockReset();
    cleanup();
  });

  it("shows a Log in link to /login when logged out", () => {
    useAuth.mockReturnValue({ isAuthenticated: false });
    renderMenu();

    const link = screen.getByText("Log in").closest("a");
    expect(link?.getAttribute("href")).toBe("/login");
  });

  it("does not show the username or log out button when logged out", () => {
    useAuth.mockReturnValue({ isAuthenticated: false });
    renderMenu();

    expect(screen.queryByText("Log out")).toBeNull();
  });

  it("shows the username linking to /settings and a Log out button when logged in", () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      username: "alice",
      logout: vi.fn(),
    });
    renderMenu();

    expect(screen.queryByText("Log in")).toBeNull();
    const link = screen.getByText("alice").closest("a");
    expect(link?.getAttribute("href")).toBe("/settings");
    expect(screen.getByText("Log out")).toBeTruthy();
  });

  it("calls logout when Log out is clicked", () => {
    const logout = vi.fn();
    useAuth.mockReturnValue({ isAuthenticated: true, username: "alice", logout });
    renderMenu();

    fireEvent.click(screen.getByText("Log out"));
    expect(logout).toHaveBeenCalledTimes(1);
  });
});
