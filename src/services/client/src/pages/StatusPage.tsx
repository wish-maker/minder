import { useCallback, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { InfoCallout } from "../components/InfoCallout";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { badgeClass, badgeTone, secondaryButtonClass } from "../lib/ui";
import { useAsyncResource } from "../lib/useAsyncResource";

interface ServiceStatus {
  name: string;
  reachable: boolean;
  status: string;
  version?: string | null;
  environment?: string | null;
  checks?: Record<string, string>;
  error?: string;
}

interface StatusResponse {
  services: ServiceStatus[];
}

interface LogLine {
  stream: "stdout" | "stderr";
  text: string;
}

interface LogsResponse {
  name: string;
  lines: LogLine[];
}

function statusBadgeColor(status: string): string {
  if (status === "healthy") return badgeTone.success;
  if (status === "degraded") return badgeTone.warn;
  return badgeTone.danger;
}

export function LogViewer({ name, token }: { name: string; token: string }) {
  const [loaded, setLoaded] = useState(false);
  const [lines, setLines] = useState<LogLine[]>([]);
  const [status, setStatus] = useState("");

  const loadLogs = useCallback(async () => {
    setStatus("Loading…");
    try {
      const res = await apiFetch<LogsResponse>(
        `/v1/containers/${encodeURIComponent(name)}/logs?tail=200`,
        { token },
      );
      setLines(res.lines);
      setLoaded(true);
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
  }, [name, token]);

  function handleToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    // Only fires the fetch on first expand -- once `loaded`, logs sat frozen
    // at whatever "tail=200" caught at that moment, with re-opening the
    // details element a no-op. The explicit Refresh button below is the only
    // way to see anything newer.
    if (!e.currentTarget.open || loaded) return;
    loadLogs();
  }

  return (
    <details className="mt-2" onToggle={handleToggle}>
      <summary className="cursor-pointer text-xs font-medium text-indigo-600 dark:text-indigo-400">
        {token ? "View recent logs" : "View recent logs (log in required)"}
      </summary>
      <div className="mt-2 text-xs">
        <div className="mb-1 flex items-center gap-2">
          {status && <p className="text-gray-500 dark:text-gray-400">{status}</p>}
          {loaded && (
            <button
              onClick={loadLogs}
              className="text-indigo-600 hover:underline dark:text-indigo-400"
            >
              ↻ Refresh
            </button>
          )}
        </div>
        {lines.length > 0 && (
          <pre className="max-h-64 overflow-auto rounded bg-gray-900 p-2 font-mono text-[11px] leading-relaxed text-gray-100">
            {lines.map((l, i) => (
              <div key={i} className={l.stream === "stderr" ? "text-red-400" : "text-gray-100"}>
                {l.text.replace(/\n$/, "")}
              </div>
            ))}
          </pre>
        )}
        {loaded && lines.length === 0 && (
          <p className="text-gray-500 dark:text-gray-400">No recent log output.</p>
        )}
      </div>
    </details>
  );
}

function ServiceCard({ service, token }: { service: ServiceStatus; token: string }) {
  return (
    <section className="mb-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">{service.reachable ? "🟢" : "🔴"}</span> {service.name}
        <span className={`${badgeClass} ${statusBadgeColor(service.status)}`}>
          {service.status}
        </span>
        {service.version && <span className={badgeClass}>reported v{service.version}</span>}
      </h3>
      {service.error && (
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">{service.error}</p>
      )}
      {service.checks && Object.keys(service.checks).length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500 dark:text-gray-400">
          {Object.entries(service.checks).map(([dep, result]) => (
            <li key={dep}>
              {dep}: {result}
            </li>
          ))}
        </ul>
      )}
      <LogViewer name={service.name} token={token} />
    </section>
  );
}

export function StatusPage() {
  const { token } = useAuth();
  // Single whole-object read → useAsyncResource (cancels on unmount, drops a
  // stale response if Refresh is clicked twice fast). #502
  const services = useAsyncResource((signal) =>
    apiFetch<StatusResponse>("/v1/status", { signal }).then((r) => r.services ?? []),
  );

  return (
    <>
      <PageHeader icon="🩺" title="Status" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Health, reported version, and recent logs for every core service.
        Browsing the health grid is open for everyone; log in to view logs
        (they can contain stack traces, so they're treated as sensitive).
      </p>
      <InfoCallout icon="ℹ️">
        "Reported version" is a hardcoded string each service's own code
        carries — it isn't derived from the deployed Docker image tag, so
        don't treat it as a deployment-tracking signal.
      </InfoCallout>
      <StatusLine isError={!!services.error}>
        {services.error ?? (services.loading ? "Loading…" : "")}
      </StatusLine>
      <button
        onClick={services.reload}
        className={`${secondaryButtonClass} mb-4`}
      >
        🔄 Refresh
      </button>
      {services.data?.length === 0 && (
        <EmptyState>No services reported by the server.</EmptyState>
      )}
      {services.data?.map((s) => (
        <ServiceCard key={s.name} service={s} token={token} />
      ))}
    </>
  );
}
