// VITE_API_BASE_URL is baked in at BUILD time (Vite convention), not read at
// container start like every Python service's env vars -- changing it means
// rebuilding the image, not just restarting the container. See
// docker/docker-compose.yml's client build.args and .env.example.
export const apiBaseUrl: string =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// OIDC/SSO entry point — a full-page navigation into Authelia's forward-auth +
// OIDC authorize flow, which only exists at a real Traefik hostname with valid
// DNS + TLS. So there is NO default (mirroring `autheliaPortalUrl` below): the
// old fallback baked in `https://api.minder.local/...`, which just dead-ends
// over a plain localhost/LAN address (the host doesn't resolve). A real SSO
// deployment sets VITE_OIDC_LOGIN_URL to its gateway URL; when unset the SSO
// button is hidden and local login (LoginPage) — the path that actually
// completes over localhost — is the only option shown.
export const oidcLoginUrl: string =
  import.meta.env.VITE_OIDC_LOGIN_URL || "";

// The Authelia self-service portal (change password / display name / groups).
// Deployment-specific and only reachable over real DNS + TLS, so there is NO
// hardcoded default — over a plain localhost/LAN address the portal isn't up,
// and a dead `https://authelia.minder.local` link (the old hardcoded value)
// just 404s. Baked at build time like the other VITE_* config; when unset the
// Settings page shows the guidance as plain text instead of a broken link.
export const autheliaPortalUrl: string =
  import.meta.env.VITE_AUTHELIA_PORTAL_URL || "";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Every page's catch block used `e instanceof Error ? e.message : String(e)`
 * verbatim -- which, for a 401, shows whatever raw string the backend's
 * HTTPException carries (e.g. "Not authenticated") instead of an actionable
 * message telling the user what to actually do about it. Only 1 of 10 pages
 * special-cased this. Centralized here so every page gets the same
 * treatment without each one re-deriving it. */
export function friendlyErrorMessage(e: unknown): string {
  if (e instanceof ApiError && e.status === 401) {
    return "Your session expired — log in again.";
  }
  return e instanceof Error ? e.message : String(e);
}

async function parseErrorDetail(res: Response): Promise<string> {
  const data = await res.json().catch(() => ({}) as { detail?: unknown });
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail !== undefined) return JSON.stringify(detail);
  return `Request failed (${res.status})`;
}

export interface ApiOptions {
  method?: string;
  body?: unknown;
  token?: string;
  // Optional AbortSignal so a caller (e.g. useAsyncResource) can cancel an
  // in-flight request on unmount / supersession / timeout. When the signal
  // aborts, fetch rejects with an AbortError the caller is expected to swallow.
  signal?: AbortSignal;
}

/** The shared list envelope every Minder `list` endpoint returns (#501):
 * `{items, total, limit, offset}`. `total` is the pre-slice count, so
 * `offset + items.length < total` means another page exists. */
export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** Thin fetch wrapper: prefixes the gateway base URL, injects the bearer
 * token when present, and centralizes JSON parsing + error handling --
 * replacing the copy-pasted try/catch blocks the old plugin_config.html and
 * model_management.html each carried independently. */
export async function apiFetch<T>(
  path: string,
  { method = "GET", body, token, signal }: ApiOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const isFormData = body instanceof FormData;
  // Never set Content-Type for FormData -- the browser fills in the
  // multipart boundary itself; a manually-set header drops it and breaks
  // parsing server-side.
  if (body !== undefined && !isFormData) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${apiBaseUrl}${path}`, {
    method,
    headers,
    body:
      body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
    signal,
  });

  if (!res.ok) throw new ApiError(await parseErrorDetail(res), res.status);

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Like apiFetch, but for endpoints that return a binary body (e.g. tts-stt's
 * synthesized WAV/MP3 audio) instead of JSON -- calling .json() on those
 * would throw. Returns the blob plus any response headers the caller asked
 * for (e.g. tts-stt's X-Language/X-Duration), since Blob itself carries no
 * header info. */
export async function apiFetchBlob(
  path: string,
  { method = "GET", body, token, signal }: ApiOptions = {},
): Promise<{ blob: Blob; headers: Headers }> {
  const headers: Record<string, string> = {};
  const isFormData = body instanceof FormData;
  if (body !== undefined && !isFormData) {
    headers["Content-Type"] = "application/json";
  }
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${apiBaseUrl}${path}`, {
    method,
    headers,
    body:
      body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
    signal,
  });

  if (!res.ok) throw new ApiError(await parseErrorDetail(res), res.status);

  return { blob: await res.blob(), headers: res.headers };
}
