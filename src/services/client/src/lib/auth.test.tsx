import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "./auth";

const TOKEN_KEY = "minder_jwt";

/** Build a JWT-shaped string (`header.payload.signature`) whose payload is the
 * base64url encoding of `claims` — mirrors jwt.test.ts's helper. */
function makeJwt(claims: Record<string, unknown>): string {
  const b64 = btoa(JSON.stringify(claims))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `header.${b64}.sig`;
}

function renderAuth() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider });
}

describe("AuthProvider / useAuth", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("throws when used outside an AuthProvider", () => {
    expect(() => renderHook(() => useAuth())).toThrow(
      "useAuth must be used within an AuthProvider",
    );
  });

  it("starts unauthenticated with no token in sessionStorage", () => {
    const { result } = renderAuth();
    expect(result.current.token).toBe("");
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.username).toBe("");
  });

  it("picks up a valid, non-expired token already in sessionStorage", () => {
    const jwt = makeJwt({
      username: "ada",
      email: "ada@example.com",
      role: "admin",
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    sessionStorage.setItem(TOKEN_KEY, jwt);

    const { result } = renderAuth();

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.username).toBe("ada");
    expect(result.current.email).toBe("ada@example.com");
    expect(result.current.role).toBe("admin");
  });

  it("treats an expired token in sessionStorage as not authenticated", () => {
    const jwt = makeJwt({
      username: "ada",
      exp: Math.floor(Date.now() / 1000) - 10,
    });
    sessionStorage.setItem(TOKEN_KEY, jwt);

    const { result } = renderAuth();

    expect(result.current.isAuthenticated).toBe(false);
  });

  describe("login", () => {
    it("stores the returned token and flips isAuthenticated on success", async () => {
      const jwt = makeJwt({
        username: "ada",
        exp: Math.floor(Date.now() / 1000) + 3600,
      });
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({ access_token: jwt }),
      } as Response);

      const { result } = renderAuth();
      await act(async () => {
        await result.current.login("ada", "hunter2");
      });

      expect(fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/login",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: "ada", password: "hunter2" }),
        }),
      );
      expect(result.current.token).toBe(jwt);
      expect(result.current.isAuthenticated).toBe(true);
      expect(sessionStorage.getItem(TOKEN_KEY)).toBe(jwt);
    });

    it("throws the backend's detail message on failure and leaves state unchanged", async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Invalid credentials" }),
      } as Response);

      const { result } = renderAuth();
      await expect(
        act(async () => {
          await result.current.login("ada", "wrong");
        }),
      ).rejects.toThrow("Invalid credentials");

      expect(result.current.token).toBe("");
      expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    });

    it("falls back to a generic status message when the error body isn't JSON", async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error("not json");
        },
      } as unknown as Response);

      const { result } = renderAuth();
      await expect(
        act(async () => {
          await result.current.login("ada", "wrong");
        }),
      ).rejects.toThrow("Request failed (500)");
    });
  });

  describe("register", () => {
    it("posts username/email/password and does not touch token state on success", async () => {
      vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({}) } as Response);

      const { result } = renderAuth();
      await act(async () => {
        await result.current.register("ada", "ada@example.com", "hunter2");
      });

      expect(fetch).toHaveBeenCalledWith(
        "http://localhost:8000/v1/auth/register",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            username: "ada",
            email: "ada@example.com",
            password: "hunter2",
          }),
        }),
      );
      expect(result.current.isAuthenticated).toBe(false);
    });

    it("throws the backend's detail message on failure", async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ detail: "Username already taken" }),
      } as Response);

      const { result } = renderAuth();
      await expect(
        act(async () => {
          await result.current.register("ada", "ada@example.com", "hunter2");
        }),
      ).rejects.toThrow("Username already taken");
    });
  });

  it("loginWithToken sets the token and sessionStorage directly, without a network call", () => {
    const jwt = makeJwt({
      username: "bob",
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    const { result } = renderAuth();

    act(() => {
      result.current.loginWithToken(jwt);
    });

    expect(fetch).not.toHaveBeenCalled();
    expect(result.current.token).toBe(jwt);
    expect(result.current.username).toBe("bob");
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe(jwt);
  });

  it("logout clears the token from state and sessionStorage", () => {
    const jwt = makeJwt({
      username: "ada",
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    sessionStorage.setItem(TOKEN_KEY, jwt);
    const { result } = renderAuth();
    expect(result.current.isAuthenticated).toBe(true);

    act(() => {
      result.current.logout();
    });

    expect(result.current.token).toBe("");
    expect(result.current.isAuthenticated).toBe(false);
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});
