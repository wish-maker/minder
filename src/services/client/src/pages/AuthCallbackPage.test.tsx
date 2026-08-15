import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthCallbackPage } from "./AuthCallbackPage";

const loginWithToken = vi.fn();
const navigate = vi.fn();

vi.mock("../lib/auth", () => ({
  useAuth: () => ({ loginWithToken }),
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => navigate,
}));

/** A previously-silent gap: a failed OIDC/SSO redirect (denied consent,
 * expired auth code, ...) carries `#error=...&error_description=...` instead
 * of `#token=...`, and used to fall straight through to navigate("/") with no
 * indication anything went wrong. Fixed to route to /login with the failure
 * message in router state instead. */
describe("AuthCallbackPage", () => {
  beforeEach(() => {
    loginWithToken.mockClear();
    navigate.mockClear();
  });
  afterEach(() => {
    cleanup();
    window.location.hash = "";
  });

  it("logs in and goes home when the redirect carries a token", () => {
    window.location.hash = "#token=abc.def.ghi";
    render(<AuthCallbackPage />);
    expect(loginWithToken).toHaveBeenCalledWith("abc.def.ghi");
    expect(navigate).toHaveBeenCalledWith("/", { replace: true });
  });

  it("URL-decodes the token before handing it to loginWithToken", () => {
    window.location.hash = "#token=abc%2Bdef";
    render(<AuthCallbackPage />);
    expect(loginWithToken).toHaveBeenCalledWith("abc+def");
  });

  it("routes to /login with the failure reason when the redirect carries an OIDC error", () => {
    window.location.hash =
      "#error=access_denied&error_description=User+denied+access";
    render(<AuthCallbackPage />);
    expect(loginWithToken).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/login", {
      replace: true,
      state: { oidcError: "User denied access" },
    });
  });

  it("falls back to a generic message when the redirect has neither a token nor an error", () => {
    window.location.hash = "";
    render(<AuthCallbackPage />);
    expect(loginWithToken).not.toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith("/login", {
      replace: true,
      state: { oidcError: "Sign-in did not complete — please try again." },
    });
  });
});
