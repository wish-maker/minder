import { useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { InfoCallout } from "../components/InfoCallout";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  badgeClass,
  badgeTone,
  destructiveButtonClass,
  inlineInputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";
import { useAsyncResource } from "../lib/useAsyncResource";

export interface BackupArchive {
  name: string;
  size_bytes: number;
  modified_at: string;
}

interface BackupsResponse {
  archives: BackupArchive[];
}

export interface BackupJob {
  id: string;
  action: "backup" | "restore";
  archive: string | null;
  status: "pending" | "running" | "done" | "error";
  requested_by: string;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  output: string;
}

interface JobsResponse {
  jobs: BackupJob[];
}

/** Matches the backend's own size formatting intent (bytes are meaningless at
 * this scale) without pulling in a formatting dependency for one call site. */
function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = n;
  let unitIndex = -1;
  do {
    value /= 1024;
    unitIndex += 1;
  } while (value >= 1024 && unitIndex < units.length - 1);
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function jobStatusTone(status: BackupJob["status"]): string {
  if (status === "done") return badgeTone.success;
  if (status === "error") return badgeTone.danger;
  return badgeTone.warn; // pending / running
}

export function JobRow({ job }: { job: BackupJob }) {
  return (
    <div className="mb-2 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-gray-900 dark:text-gray-100">
          {job.action === "backup" ? "💾 Backup" : "♻️ Restore"}
        </span>
        {job.archive && (
          <span className="font-mono text-xs text-gray-600 dark:text-gray-400">
            {job.archive}
          </span>
        )}
        <span className={`${badgeClass} ${jobStatusTone(job.status)}`}>
          {job.status}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          requested by {job.requested_by} at {job.requested_at}
        </span>
      </div>
      {job.status === "error" && job.error && (
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">{job.error}</p>
      )}
    </div>
  );
}

/** Restore is destructive (overwrites live data) — beyond the admin gate the
 * backend itself requires the exact archive filename echoed back in the
 * request body (#870), so the confirm step here is a real text match, not
 * a generic yes/no dialog. */
export function RestoreControl({
  archive,
  token,
  onRestored,
}: {
  archive: BackupArchive;
  token: string;
  onRestored: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  async function handleConfirm() {
    setBusy(true);
    setIsError(false);
    setStatus("Enqueuing restore…");
    try {
      await apiFetch(`/v1/backups/${encodeURIComponent(archive.name)}/restore`, {
        method: "POST",
        token,
        body: { confirm_filename: typed },
      });
      setExpanded(false);
      setTyped("");
      onRestored();
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
      setIsError(true);
    }
    setBusy(false);
  }

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className={secondaryButtonClass}
      >
        Restore…
      </button>
    );
  }

  return (
    <div className="mt-2 w-full rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950">
      <p className="mb-2 text-xs text-amber-900 dark:text-amber-100">
        This overwrites live data. Type the exact archive filename to confirm:{" "}
        <span className="font-mono">{archive.name}</span>
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={archive.name}
          className={inlineInputClass}
          disabled={busy}
        />
        <button
          onClick={handleConfirm}
          disabled={busy || typed !== archive.name}
          className={destructiveButtonClass}
        >
          {busy ? "Restoring…" : "Confirm Restore"}
        </button>
        <button
          onClick={() => {
            setExpanded(false);
            setTyped("");
            setStatus("");
          }}
          disabled={busy}
          className={secondaryButtonClass}
        >
          Cancel
        </button>
      </div>
      <StatusLine isError={isError} className="mb-0 mt-2">
        {status}
      </StatusLine>
    </div>
  );
}

function ArchiveRow({
  archive,
  token,
  onRestored,
}: {
  archive: BackupArchive;
  token: string;
  onRestored: () => void;
}) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700">
      <span className="font-mono text-xs text-gray-900 dark:text-gray-100">
        {archive.name}
      </span>
      <span className="text-xs text-gray-500 dark:text-gray-400">
        {formatBytes(archive.size_bytes)}
      </span>
      <span className="text-xs text-gray-500 dark:text-gray-400">
        {archive.modified_at}
      </span>
      <div className="ml-auto w-full sm:w-auto">
        <RestoreControl archive={archive} token={token} onRestored={onRestored} />
      </div>
    </div>
  );
}

export function BackupsPage() {
  const { token, role } = useAuth();
  const isAdmin = role === "admin";

  const backupsRes = useAsyncResource(
    (signal) => apiFetch<BackupsResponse>("/v1/backups", { token, signal }),
    { enabled: isAdmin },
  );
  const jobsRes = useAsyncResource(
    (signal) => apiFetch<JobsResponse>("/v1/backups/jobs", { token, signal }),
    { enabled: isAdmin },
  );

  const [triggerStatus, setTriggerStatus] = useState("");
  const [triggerError, setTriggerError] = useState(false);
  const [triggering, setTriggering] = useState(false);

  function refreshAll() {
    backupsRes.reload();
    jobsRes.reload();
  }

  async function handleTriggerBackup() {
    setTriggering(true);
    setTriggerError(false);
    setTriggerStatus("Enqueuing backup…");
    try {
      await apiFetch<BackupJob>("/v1/backups", { method: "POST", token });
      setTriggerStatus("Backup job enqueued — see Recent Jobs below.");
      jobsRes.reload();
    } catch (e) {
      setTriggerStatus(friendlyErrorMessage(e));
      setTriggerError(true);
    }
    setTriggering(false);
  }

  return (
    <>
      <PageHeader icon="🗄️" title="Backups" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Backup and restore run as a job queue, not directly from this page —
        a host-side process picks up each request and does the real work
        (see Recent Jobs below for progress). Admin-only: archive existence
        and timestamps are treated as sensitive operational detail.
      </p>

      {!isAdmin && (
        <InfoCallout icon="🔒">
          {token
            ? "Admin role required to view or manage backups."
            : "Log in as an admin to view or manage backups."}
        </InfoCallout>
      )}

      {isAdmin && (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <button
              onClick={handleTriggerBackup}
              disabled={triggering}
              className={primaryButtonClass}
            >
              {triggering ? "Enqueuing…" : "💾 Trigger Backup"}
            </button>
            <button onClick={refreshAll} className={secondaryButtonClass}>
              🔄 Refresh
            </button>
          </div>
          <StatusLine isError={triggerError}>{triggerStatus}</StatusLine>

          <section className="mb-6">
            <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
              Archives
            </h2>
            <StatusLine isError={!!backupsRes.error}>
              {backupsRes.error ?? (backupsRes.loading ? "Loading…" : "")}
            </StatusLine>
            {backupsRes.data?.archives.length === 0 && (
              <EmptyState>No backup archives yet — trigger one above.</EmptyState>
            )}
            {backupsRes.data?.archives.map((a) => (
              <ArchiveRow
                key={a.name}
                archive={a}
                token={token}
                onRestored={refreshAll}
              />
            ))}
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
              Recent Jobs
            </h2>
            <StatusLine isError={!!jobsRes.error}>
              {jobsRes.error ?? (jobsRes.loading ? "Loading…" : "")}
            </StatusLine>
            {jobsRes.data?.jobs.length === 0 && <EmptyState>No jobs yet.</EmptyState>}
            {jobsRes.data?.jobs.map((j) => (
              <JobRow key={j.id} job={j} />
            ))}
          </section>
        </>
      )}
    </>
  );
}
