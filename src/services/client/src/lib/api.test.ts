import { describe, expect, it } from "vitest";

import { ApiError, friendlyErrorMessage } from "./api";

describe("ApiError", () => {
  it("is an Error that carries the HTTP status", () => {
    const err = new ApiError("nope", 404);
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
    expect(err.message).toBe("nope");
  });
});

describe("friendlyErrorMessage", () => {
  it("maps a 401 ApiError to an actionable session message", () => {
    expect(friendlyErrorMessage(new ApiError("Not authenticated", 401))).toMatch(
      /session expired/i,
    );
  });

  it("passes through a non-401 ApiError's own message", () => {
    expect(friendlyErrorMessage(new ApiError("boom", 500))).toBe("boom");
  });

  it("uses .message for a plain Error", () => {
    expect(friendlyErrorMessage(new Error("plain"))).toBe("plain");
  });

  it("stringifies a non-Error value", () => {
    expect(friendlyErrorMessage("weird")).toBe("weird");
  });
});
