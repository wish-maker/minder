import { useCallback, useId, useRef, useState } from "react";

import { BundleCard } from "../components/BundleCard";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  type Bundle,
  type BundlesResponse,
  type ReconcileResponse,
  bundlesToStateExport,
  outcomeSummary,
  parseBundleStateExport,
} from "../lib/bundles";
import { secondaryButtonClass } from "../lib/ui";
import { useAsyncResource } from "../lib/useAsyncResource";

/** Downloads `data` as a JSON file -- a real browser download (this is the
 * actual product, not a sandboxed preview), not an in-page viewer. */
function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ExportImportPanel({
  bundles,
  token,
  isAdmin,
  onChanged,
}: {
  bundles: Bundle[];
  token: string;
  isAdmin: boolean;
  onChanged: () => void;
}) {
  const fileInputId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);
  const [busy, setBusy] = useState(false);

  function handleExport() {
    const ts = new Date().toISOString().slice(0, 10);
    downloadJson(`minder-bundles-${ts}.json`, bundlesToStateExport(bundles));
  }

  const handleImportFile = useCallback(
    async (file: File) => {
      setBusy(true);
      setIsError(false);
      setStatus("Reading file…");
      try {
        const text = await file.text();
        const desired = parseBundleStateExport(JSON.parse(text));
        const byName = new Map(bundles.map((b) => [b.name, b]));
        const applied: string[] = [];
        const skipped: string[] = [];
        const errors: string[] = [];
        for (const [name, { enabled }] of Object.entries(desired)) {
          const current = byName.get(name);
          if (!current) {
            skipped.push(`${name} (unknown bundle)`);
            continue;
          }
          if (current.enabled === enabled) {
            continue; // already matches -- nothing to do
          }
          if (current.core && !enabled) {
            skipped.push(`${name} (core can't be disabled)`);
            continue;
          }
          setStatus(`Applying ${name} → ${enabled ? "enabled" : "disabled"}…`);
          try {
            await apiFetch(
              `/v1/bundles/${encodeURIComponent(name)}/${enabled ? "enable" : "disable"}`,
              { method: "POST", token },
            );
            applied.push(name);
          } catch (e) {
            errors.push(`${name}: ${friendlyErrorMessage(e)}`);
          }
        }
        const parts = [
          applied.length > 0 ? `applied: ${applied.join(", ")}` : "",
          skipped.length > 0 ? `skipped: ${skipped.join(", ")}` : "",
          errors.length > 0 ? `errors: ${errors.join("; ")}` : "",
        ].filter(Boolean);
        setStatus(parts.length > 0 ? parts.join(" — ") : "Nothing to change.");
        setIsError(errors.length > 0);
        onChanged();
      } catch (e) {
        setStatus(
          e instanceof Error ? e.message : "Could not read that file as bundle state.",
        );
        setIsError(true);
      }
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [bundles, token, onChanged],
  );

  return (
    <section className="mb-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900">
      <h2 className="mb-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">💾</span> Export / Import
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Export the current enabled/disabled state of every bundle as a JSON
        file — the same shape the host's own <code>bundles.state.json</code>{" "}
        uses. Import re-applies a previously exported (or hand-written) file
        by calling enable/disable for whatever differs from the current
        state; bundles not mentioned in the file are left untouched.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={handleExport} className={secondaryButtonClass}>
          ⬇️ Export current state
        </button>
        <label htmlFor={fileInputId} className="sr-only">
          Import bundle state from a JSON file
        </label>
        <input
          id={fileInputId}
          ref={fileInputRef}
          type="file"
          accept="application/json"
          disabled={!isAdmin || busy}
          title={!isAdmin ? "Admin role required to import" : undefined}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleImportFile(file);
          }}
          className="text-xs text-gray-600 file:mr-2 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-gray-700 hover:file:bg-gray-200 dark:text-gray-400 dark:file:bg-gray-800 dark:file:text-gray-300 dark:hover:file:bg-gray-700"
        />
      </div>
      <StatusLine isError={isError} className="mt-2">
        {status}
      </StatusLine>
    </section>
  );
}

/** Bundles currently enabled — export/import and the docker-version detail
 * per claimed service live here rather than on Available Bundles, since both
 * are specifically about the bundles you're actually running. */
export function InstalledBundlesPage() {
  const { token, role } = useAuth();
  const isAdmin = role === "admin";
  const bundlesRes = useAsyncResource((signal) =>
    apiFetch<BundlesResponse>("/v1/bundles", { signal }),
  );
  const bundles = bundlesRes.data?.bundles ?? [];
  const installed = bundles.filter((b) => b.enabled);
  const orphaned = bundlesRes.data?.orphaned ?? [];

  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);
  const [reconciling, setReconciling] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  async function handleReconcile() {
    setReconciling(true);
    setStatusMsg("Reconciling…");
    try {
      const res = await apiFetch<ReconcileResponse>("/v1/bundles/reconcile", {
        method: "POST",
        token,
      });
      setStatusMsg(`Reconciled: ${outcomeSummary(res)}`);
      bundlesRes.reload();
    } catch (e) {
      setStatusMsg(friendlyErrorMessage(e), true);
    }
    setReconciling(false);
  }

  return (
    <>
      <PageHeader icon="📦" title="Installed Bundles" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Feature bundles currently turned on, the Docker image each claimed
        service actually runs, and export/import for the whole set. Disabling
        or reconciling requires an admin account.
      </p>

      {bundlesRes.data && (
        <ExportImportPanel
          bundles={bundles}
          token={token}
          isAdmin={isAdmin}
          onChanged={bundlesRes.reload}
        />
      )}

      <StatusLine isError={isError || !!bundlesRes.error}>
        {status || bundlesRes.error || (bundlesRes.loading ? "Loading…" : "")}
      </StatusLine>

      {orphaned.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          ⚠️ Orphaned services (claimed by no enabled bundle, should be
          stopped): {orphaned.join(", ")}. Run Reconcile below to clean these
          up.
        </div>
      )}

      <button
        onClick={handleReconcile}
        disabled={!isAdmin || reconciling}
        title={
          !isAdmin
            ? token
              ? "Admin role required"
              : "Log in as an admin to reconcile"
            : undefined
        }
        className={`${secondaryButtonClass} mb-4`}
      >
        {reconciling ? "Reconciling…" : "🔄 Reconcile"}
      </button>

      {bundlesRes.data && installed.length === 0 && (
        <EmptyState>
          No bundles are enabled yet — see Available Bundles.
        </EmptyState>
      )}
      {installed.map((b) => (
        <BundleCard
          key={b.name}
          bundle={b}
          token={token}
          isAdmin={isAdmin}
          onChanged={bundlesRes.reload}
        />
      ))}
    </>
  );
}
