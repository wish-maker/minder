import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch, apiFetchBlob, ApiError, friendlyErrorMessage } from "./api";

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

describe("apiFetch", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GETs with no body/Content-Type by default and returns parsed JSON", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ hello: "world" }),
    } as Response);

    const result = await apiFetch<{ hello: string }>("/v1/things");

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/things",
      expect.objectContaining({ method: "GET", headers: {}, body: undefined }),
    );
    expect(result).toEqual({ hello: "world" });
  });

  it("JSON-stringifies a plain object body and sets Content-Type", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 1 }),
    } as Response);

    await apiFetch("/v1/things", { method: "POST", body: { name: "x" } });

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/things",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "x" }),
      }),
    );
  });

  it("passes a FormData body through untouched, without a Content-Type header", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    } as Response);
    const form = new FormData();
    form.append("file", "contents");

    await apiFetch("/v1/upload", { method: "POST", body: form });

    const call = vi.mocked(fetch).mock.calls[0];
    const init = call[1] as RequestInit;
    expect(init.headers).toEqual({});
    expect(init.body).toBe(form);
  });

  it("adds a Bearer Authorization header when a token is given", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    } as Response);

    await apiFetch("/v1/things", { token: "abc123" });

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/things",
      expect.objectContaining({
        headers: { Authorization: "Bearer abc123" },
      }),
    );
  });

  it("returns undefined for a 204 No Content response without calling .json()", async () => {
    const json = vi.fn();
    vi.mocked(fetch).mockResolvedValue({ ok: true, status: 204, json } as unknown as Response);

    const result = await apiFetch("/v1/things/1", { method: "DELETE" });

    expect(result).toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });

  it("throws an ApiError carrying the string detail on a non-ok response", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Not found" }),
    } as Response);

    await expect(apiFetch("/v1/things/99")).rejects.toMatchObject({
      message: "Not found",
      status: 404,
    });
  });

  it("JSON.stringifies a non-string detail (e.g. FastAPI validation errors)", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: [{ loc: ["body", "name"], msg: "required" }] }),
    } as Response);

    await expect(apiFetch("/v1/things")).rejects.toMatchObject({
      message: JSON.stringify([{ loc: ["body", "name"], msg: "required" }]),
      status: 422,
    });
  });

  it("falls back to a generic status message when there's no detail at all", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    } as Response);

    await expect(apiFetch("/v1/things")).rejects.toMatchObject({
      message: "Request failed (500)",
      status: 500,
    });
  });

  it("falls back to a generic status message when the error body isn't JSON", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error("not json");
      },
    } as unknown as Response);

    await expect(apiFetch("/v1/things")).rejects.toMatchObject({
      message: "Request failed (502)",
      status: 502,
    });
  });
});

describe("apiFetchBlob", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the response's blob and headers on success", async () => {
    const blob = new Blob(["audio bytes"]);
    const headers = new Headers({ "X-Language": "en" });
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => blob,
      headers,
    } as unknown as Response);

    const result = await apiFetchBlob("/v1/tts", { method: "POST", body: { text: "hi" } });

    expect(result.blob).toBe(blob);
    expect(result.headers.get("X-Language")).toBe("en");
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/tts",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: "hi" }),
      }),
    );
  });

  it("throws an ApiError on a non-ok response instead of trying to read a blob", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Text too long" }),
    } as Response);

    await expect(apiFetchBlob("/v1/tts")).rejects.toMatchObject({
      message: "Text too long",
      status: 400,
    });
  });

  it("GETs with a Bearer token and no body", async () => {
    const blob = new Blob(["bytes"]);
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => blob,
      headers: new Headers(),
    } as unknown as Response);

    await apiFetchBlob("/v1/tts/1", { token: "abc123" });

    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/v1/tts/1",
      expect.objectContaining({
        method: "GET",
        headers: { Authorization: "Bearer abc123" },
        body: undefined,
      }),
    );
  });

  it("passes a FormData body through untouched, without a Content-Type header", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => new Blob(["bytes"]),
      headers: new Headers(),
    } as unknown as Response);
    const form = new FormData();
    form.append("file", "contents");

    await apiFetchBlob("/v1/upload", { method: "POST", body: form });

    const call = vi.mocked(fetch).mock.calls[0];
    const init = call[1] as RequestInit;
    expect(init.headers).toEqual({});
    expect(init.body).toBe(form);
  });
});
