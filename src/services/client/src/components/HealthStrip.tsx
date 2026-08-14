import { Link } from "react-router-dom";

import { apiFetch } from "../lib/api";
import { useAsyncResource } from "../lib/useAsyncResource";
import { Skeleton } from "./Skeleton";

interface ServiceStatus {
  name: string;
  reachable: boolean;
  status: string;
}

interface StatusResponse {
  services: ServiceStatus[];
}

function isHealthy(s: ServiceStatus): boolean {
  return s.reachable && s.status === "healthy";
}

/** One-line system-health summary for the home dashboard, built on the same
 * public `GET /v1/status` the full Status page uses -- so "is everything up"
 * is answered the moment you land, not three clicks deep. Deliberately quiet
 * on failure (returns null): a broken health check on the home page would
 * itself look like an outage, and the real place to investigate one already
 * exists at /platform/status. */
export function HealthStrip() {
  const services = useAsyncResource((signal) =>
    apiFetch<StatusResponse>("/v1/status", { signal }).then((r) => r.services),
  );

  if (services.error) return null;
  if (services.loading && services.data === null) {
    return <Skeleton className="mb-6 h-12 w-full" />;
  }
  if (services.data === null || services.data.length === 0) return null;

  const total = services.data.length;
  const healthy = services.data.filter(isHealthy).length;
  const allHealthy = healthy === total;

  return (
    <Link
      to="/platform/status"
      className="mb-6 flex items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm shadow-sm transition hover:border-indigo-300 hover:shadow-md dark:border-gray-700 dark:bg-gray-900"
    >
      <span aria-hidden="true" className="text-lg">
        {allHealthy ? "🟢" : healthy === 0 ? "🔴" : "🟡"}
      </span>
      <span className="font-medium text-gray-900 dark:text-gray-100">
        {allHealthy ? "All systems healthy" : `${healthy}/${total} services healthy`}
      </span>
      <span className="ml-auto flex -space-x-1" aria-hidden="true">
        {services.data.map((s) => (
          <span
            key={s.name}
            title={s.name}
            className={`h-2.5 w-2.5 rounded-full border-2 border-white dark:border-gray-900 ${
              isHealthy(s) ? "bg-emerald-500" : s.reachable ? "bg-amber-500" : "bg-red-500"
            }`}
          />
        ))}
      </span>
      <span className="whitespace-nowrap text-indigo-600 dark:text-indigo-400">
        View status →
      </span>
    </Link>
  );
}
