import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "./LoginPage";

const login = vi.fn();
const register = vi.fn();
const navigate = vi.fn();
let isAuthenticated = false;
let locationState: { oidcError?: string } | null = null;

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ isAuthenticated, login, register }),
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
  useLocation: () => ({ state: locationState }),
  Navigate: ({ to, replace }: { to: string; replace?: boolean }) => (
    <div data-testid="navigate" data-to={to} data-replace={String(replace)} />
  ),
}));
vi.mock("../lib/api", () => ({
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
  oidcLoginUrl: "https://sso.example.com/authorize",
}));

function fillAndSubmit(
  submitButtonName: string,
  { username = "alice", email = "", password = "hunter2" } = {},
) {
  fireEvent.change(screen.getByLabelText("Username"), {
    target: { value: username },
  });
  if (email) {
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: email },
    });
  }
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: password },
  });
  fireEvent.click(screen.getByRole("button", { name: submitButtonName }));
}

describe("LoginPage", () => {
  beforeEach(() => {
    login.mockClear();
    register.mockClear();
    navigate.mockClear();
    isAuthenticated = false;
    locationState = null;
  });
  afterEach(() => cleanup());

  it("redirects home when already authenticated", () => {
    isAuthenticated = true;
    render(<LoginPage />);
    const nav = screen.getByTestId("navigate");
    expect(nav.dataset.to).toBe("/");
    expect(nav.dataset.replace).toBe("true");
  });

  it("pre-populates the error banner from a failed OIDC redirect", () => {
    locationState = { oidcError: "User denied access" };
    render(<LoginPage />);
    expect(screen.getByText("User denied access")).toBeTruthy();
  });

  it("logs in without registering in login mode", async () => {
    login.mockResolvedValue(undefined);
    render(<LoginPage />);
    fillAndSubmit("Log in");
    await vi.waitFor(() =>
      expect(navigate).toHaveBeenCalledWith("/", { replace: true }),
    );
    expect(login).toHaveBeenCalledWith("alice", "hunter2");
    expect(register).not.toHaveBeenCalled();
  });

  it("registers then logs in when switched to register mode", async () => {
    register.mockResolvedValue(undefined);
    login.mockResolvedValue(undefined);
    render(<LoginPage />);
    fireEvent.click(screen.getByRole("button", { name: "Create one" }));
    fillAndSubmit("Create account & log in", { email: "alice@example.com" });
    await vi.waitFor(() =>
      expect(navigate).toHaveBeenCalledWith("/", { replace: true }),
    );
    expect(register).toHaveBeenCalledWith(
      "alice",
      "alice@example.com",
      "hunter2",
    );
    expect(login).toHaveBeenCalledWith("alice", "hunter2");
  });

  it("shows a friendly error and re-enables the form when login fails", async () => {
    login.mockRejectedValue(new Error("Invalid credentials"));
    render(<LoginPage />);
    fillAndSubmit("Log in");
    await screen.findByText("Invalid credentials");
    expect(
      screen.getByRole("button", { name: "Log in" }).hasAttribute("disabled"),
    ).toBe(false);
  });

  it("does not attempt login when register() itself fails", async () => {
    register.mockRejectedValue(new Error("Username already taken"));
    render(<LoginPage />);
    fireEvent.click(screen.getByRole("button", { name: "Create one" }));
    fillAndSubmit("Create account & log in", { email: "alice@example.com" });
    await screen.findByText("Username already taken");
    expect(login).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("shows the SSO link when VITE_OIDC_LOGIN_URL is configured", () => {
    render(<LoginPage />);
    const link = screen.getByRole("link", { name: /Sign in with SSO/i });
    expect(link.getAttribute("href")).toBe("https://sso.example.com/authorize");
  });
});
