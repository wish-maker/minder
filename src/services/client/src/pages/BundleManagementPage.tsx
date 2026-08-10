import { useCallback, useEffect, useState } from "react";

import { InfoCallout } from "../components/InfoCallout";
import { LoginPanel } from "../components/LoginPanel";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import { badgeClass, cardClass, primaryButtonClass, secondaryButtonClass, statusClass } from "../lib/ui";

interface BundleService {
  name: string;
  active: boolean;
  claimants: string[];
}

interface Bundle {
  name: string;
  core: boolean;
  enabled: boolean;
  claims: string[];
  services: BundleService[];
}

interface BundlesResponse {
  bundles: Bundle[];
  orphaned: string[];
  count: number;
}

interface EnableResponse {
  bundle: string;
  enabled: true;
  started: string[];
  already_running: string[];
  pending_create: string[];
  errors: string[];
}

interface DisableResponse {
  bundle: string;
  enabled: false;
  orphaned: string[];
  stopped: string[];
  already_stopped: string[];
  absent: string[];
  errors: string[];
}

interface ReconcileResponse {
  started: string[];
  already_running: string[];
  pending_create: string[];
  stopped: string[];
  already_stopped: string[];
  errors: string[];
}

function outcomeSummary(
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

function ServiceRow({ service }: { service: BundleService }) {
  return (
    <li className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          service.active ? "bg-green-500" : "bg-gray-300 dark:bg-gray-600"
        }`}
        aria-hidden="true"
      />
      {service.name}
      {service.claimants.length > 0 && (
        <span className="text-gray-400 dark:text-gray-500">
          (also claimed by: {service.claimants.filter((c) => c).join(", ") || "—"})
        </span>
      )}
    </li>
  );
}

function BundleCard({
  bundle,
  token,
  onChanged,
}: {
  bundle: Bundle;
  token: string;
  onChanged: () => void;
}) {
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleToggle() {
    setBusy(true);
    setStatus(bundle.enabled ? "Disabling…" : "Enabling…");
    try {
      const res = await apiFetch<EnableResponse | DisableResponse>(
        `/v1/bundles/${encodeURIComponent(bundle.name)}/${bundle.enabled ? "disable" : "enable"}`,
        { method: "POST", token },
      );
      setStatus(outcomeSummary(res));
      onChanged();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
    setBusy(false);
  }

  return (
    <section className={`mb-4 ${cardClass}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-gray-900 dark:text-gray-100">
            <span aria-hidden="true">📦</span> {bundle.name}
            {bundle.core && <span className={badgeClass}>core</span>}
            <span
              className={
                bundle.enabled
                  ? "inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-950 dark:text-green-300"
                  : "inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300"
              }
            >
              {bundle.enabled ? "enabled" : "disabled"}
            </span>
          </h2>
          <ul className="mt-2 flex flex-col gap-1">
            {bundle.services.map((s) => (
              <ServiceRow key={s.name} service={s} />
            ))}
          </ul>
        </div>
        <button
          onClick={handleToggle}
          disabled={!token || busy || bundle.core}
          title={bundle.core ? "core is the always-on kernel — it can't be disabled" : undefined}
          className={bundle.enabled ? secondaryButtonClass : primaryButtonClass}
        >
          {bundle.enabled ? "Disable" : "Enable"}
        </button>
      </div>
      {status && <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{status}</p>}
    </section>
  );
}

export function BundleManagementPage() {
  const { token } = useAuth();
  const [bundles, setBundles] = useState<Bundle[] | null>(null);
  const [orphaned, setOrphaned] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);
  const [reconciling, setReconciling] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadBundles = useCallback(async () => {
    setStatusMsg("Loading…");
    try {
      const res = await apiFetch<BundlesResponse>("/v1/bundles");
      setBundles(res.bundles);
      setOrphaned(res.orphaned);
      setStatusMsg("");
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e), true);
    }
  }, [setStatusMsg]);

  useEffect(() => {
    loadBundles();
  }, [loadBundles]);

  async function handleReconcile() {
    setReconciling(true);
    setStatusMsg("Reconciling…");
    try {
      const res = await apiFetch<ReconcileResponse>("/v1/bundles/reconcile", {
        method: "POST",
        token,
      });
      setStatusMsg(`Reconciled: ${outcomeSummary(res)}`);
      loadBundles();
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e), true);
    }
    setReconciling(false);
  }

  return (
    <>
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Turn optional feature bundles on or off — each claims a set of
        services shared with other bundles where needed. Browsing is open
        for everyone; log in to enable, disable, or reconcile.
      </p>
      <InfoCallout icon="ℹ️">
        Enabling/disabling only starts or stops containers that already
        exist. A service that was never brought up (e.g. a bundle that's
        been off since install) shows as needing a host converge — run{" "}
        <code>./setup.sh start</code> or <code>./setup.sh restart</code> on
        the host to actually create it. That's intentional: this API can't
        create containers by design (the docker-socket-proxy it talks to is
        start/stop/inspect only, never create).
      </InfoCallout>
      <div className="mt-4">
        <LoginPanel onStatus={setStatusMsg} />
      </div>
      <div className={statusClass(isError)}>{status}</div>

      {orphaned.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          ⚠️ Orphaned services (claimed by no enabled bundle, should be
          stopped): {orphaned.join(", ")}. Run Reconcile below to clean these
          up.
        </div>
      )}

      <button
        onClick={handleReconcile}
        disabled={!token || reconciling}
        className={`${secondaryButtonClass} mb-4`}
      >
        {reconciling ? "Reconciling…" : "🔄 Reconcile"}
      </button>

      {bundles?.length === 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No bundles reported by the server.
        </p>
      )}
      {bundles?.map((b) => (
        <BundleCard key={b.name} bundle={b} token={token} onChanged={loadBundles} />
      ))}
    </>
  );
}
