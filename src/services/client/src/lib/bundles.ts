// Shared types + pure helpers for the Bundles pages (Available/Installed,
// split from a single Bundle Management page so each gets the same
// Available/Installed treatment as Plugins and AI Tools).

export interface BundleService {
  name: string;
  active: boolean;
  claimants: string[];
  // The pinned Docker image (repo/name:tag) for this service, straight from
  // docker-compose.yml -- null for a locally-built service with no image:
  // key (e.g. minder's own first-party images use `build:` in dev).
  image: string | null;
}

export interface Bundle {
  name: string;
  core: boolean;
  enabled: boolean;
  claims: string[];
  services: BundleService[];
}

export interface BundlesResponse {
  bundles: Bundle[];
  orphaned: string[];
  count: number;
}

export interface EnableResponse {
  bundle: string;
  enabled: true;
  started: string[];
  already_running: string[];
  pending_create: string[];
  errors: string[];
}

export interface DisableResponse {
  bundle: string;
  enabled: false;
  orphaned: string[];
  stopped: string[];
  already_stopped: string[];
  absent: string[];
  errors: string[];
}

export interface ReconcileResponse {
  started: string[];
  already_running: string[];
  pending_create: string[];
  stopped: string[];
  already_stopped: string[];
  errors: string[];
}

export function outcomeSummary(
  result: EnableResponse | DisableResponse | ReconcileResponse,
): string {
  const parts: string[] = [];
  if ("started" in result && result.started.length > 0) {
    parts.push(`started ${result.started.join(", ")}`);
  }
  if ("stopped" in result && result.stopped.length > 0) {
    parts.push(`stopped ${result.stopped.join(", ")}`);
  }
  if ("pending_create" in result && result.pending_create.length > 0) {
    parts.push(
      `${result.pending_create.join(", ")} need a host converge (./setup.sh start/restart) to come up`,
    );
  }
  if (result.errors.length > 0) {
    parts.push(`errors on ${result.errors.join(", ")}`);
  }
  return parts.length > 0 ? parts.join("; ") : "no change needed.";
}

/** The API's `claimants` list is every ENABLED bundle claiming this service --
 * including the bundle whose card we're already looking at. Found live: every
 * service under the "core" bundle rendered "(also claimed by: core)" -- itself,
 * not another bundle -- and "inference"'s own ollama row said "(also claimed
 * by: chat, inference, rag)", listing "inference" alongside its own siblings.
 * Filtering out the current bundle's own name is what makes this label
 * actually mean "shared with ANOTHER bundle" instead of always including a
 * self-reference. */
export function otherClaimants(service: BundleService, bundleName: string): string[] {
  return service.claimants.filter((c) => c && c !== bundleName);
}

/** Export shape for the Installed Bundles page's Export/Import -- deliberately
 * just the same {name: {enabled}} map bundles.state.json itself uses, so a
 * downloaded file is also valid input for a manual host-side restore, not
 * only this page's own Import button. */
export interface BundleStateExport {
  [bundleName: string]: { enabled: boolean };
}

export function bundlesToStateExport(bundles: Bundle[]): BundleStateExport {
  const out: BundleStateExport = {};
  for (const b of bundles) {
    out[b.name] = { enabled: b.enabled };
  }
  return out;
}

/** Validates an uploaded file's parsed JSON has the expected
 * {name: {enabled: bool}} shape before anything tries to act on it -- an
 * arbitrary/corrupt upload should fail loudly here, not partway through a
 * sequence of live enable/disable calls. */
export function parseBundleStateExport(data: unknown): BundleStateExport {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new Error("Expected a JSON object of {bundleName: {enabled: true|false}}.");
  }
  const out: BundleStateExport = {};
  for (const [name, value] of Object.entries(data as Record<string, unknown>)) {
    if (
      typeof value !== "object" ||
      value === null ||
      typeof (value as { enabled?: unknown }).enabled !== "boolean"
    ) {
      throw new Error(`"${name}" must be {"enabled": true|false}.`);
    }
    out[name] = { enabled: (value as { enabled: boolean }).enabled };
  }
  return out;
}
