// VITE_API_BASE_URL is baked in at BUILD time (Vite convention), not read at
// container start like every Python service's env vars -- changing it means
// rebuilding the image, not just restarting the container. See
// docker/docker-compose.yml's client build.args and .env.example.
export const apiBaseUrl: string =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
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
}

/** Thin fetch wrapper: prefixes the gateway base URL, injects the bearer
 * token when present, and centralizes JSON parsing + error handling --
 * replacing the copy-pasted try/catch blocks the old plugin_config.html and
 * model_management.html each carried independently. */
export async function apiFetch<T>(
  path: string,
  { method = "GET", body, token }: ApiOptions = {},
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
  });

  if (!res.ok) throw new ApiError(await parseErrorDetail(res), res.status);

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
