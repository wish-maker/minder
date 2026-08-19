"""`backup-watch` verb (#870): host-side executor for the backup/restore web UI's
job queue.

Why this exists: the web UI (plugin-registry, routes/backups.py) can't call
docker directly — it only reaches Docker through docker-socket-proxy, which
deliberately allowlists just container inspect/restart/start/stop (#377/#378) and
nothing create-level. `restore.run()` needs `docker compose up` for every
datastore (container-create), which is exactly the privilege that allowlist was
built to deny — routing it through the proxy would mean widening that allowlist
to host-takeover-equivalent scope, reversing #377/#378 instead of building on it.

So the registry only writes/reads small JSON job files into a shared bind-mounted
directory (`config.BACKUP_JOBS_DIR`) — no Docker access, no new attack surface.
This module is the OTHER end: run as a host cron job (see scripts/dev/README.md),
it polls that same directory for pending jobs and calls the real, already
100%-tested `backup.run()` / `restore.run(archive)` directly on the host, with the
exact same trust level the CLI has always had. Mirrors scheduled-backup.ps1's
"cron-invoked one-shot, not a daemon" shape rather than adding a new long-running
process.

Job file: `<job-id>.json` in BACKUP_JOBS_DIR —
  {"id", "action" ("backup"|"restore"), "archive" (str or null, restore only),
   "status" ("pending"|"running"|"done"|"error"), "requested_by",
   "requested_at", "started_at", "finished_at", "error", "output"}
requested_at/started_at/finished_at are ISO-8601 UTC strings. Secret-free by
design (job metadata only — never credentials), matching bundles.state.json's
own secret-free rationale.
"""

import contextlib
import datetime
import io
import json
from pathlib import Path

from . import backup as backup_module
from . import config, log
from . import restore as restore_module


def _now_iso() -> str:
    """UTC, second precision, lexicographically sortable — the same format
    routes/backups.py stamps `requested_at` with (kept in sync by convention;
    duplicated rather than shared since the registry container can't import
    this module — see the module docstring)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _job_files() -> list[Path]:
    try:
        return sorted(config.BACKUP_JOBS_DIR.glob("*.json"))
    except OSError:
        return []


def _read_job(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_job(path: Path, job: dict) -> None:
    # Atomic-ish: write to a sibling temp file then rename, so a reader (the API's
    # GET /v1/backups/jobs/{id}) never observes a half-written file.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, indent=2), encoding="utf-8")
    tmp.replace(path)


def _pending_jobs_oldest_first() -> list[tuple[Path, dict]]:
    jobs = []
    for path in _job_files():
        try:
            job = _read_job(path)
        except (OSError, json.JSONDecodeError):
            continue
        if job.get("status") == "pending":
            jobs.append((path, job))
    jobs.sort(key=lambda item: item[1].get("requested_at", ""))
    return jobs


def _execute(job: dict) -> tuple[bool, str]:
    """Run the job's action for real. Returns (ok, captured_output)."""
    buf = io.StringIO()
    ok = False
    try:
        with contextlib.redirect_stdout(buf):
            if job.get("action") == "restore":
                archive = job.get("archive") or ""
                rc = restore_module.run(archive)
            else:
                rc = backup_module.run()
        ok = rc == 0
    except Exception as exc:  # noqa: BLE001 — a job must never crash the watcher
        buf.write(f"\n[backup-watch] unhandled exception: {exc}\n")
        ok = False
    return ok, buf.getvalue()


def run_pending() -> int:
    """Process every pending job, oldest first, one at a time (backup/restore
    against the same live stack must never overlap). Returns 0 unless a job file
    couldn't even be read/written — individual job failures are recorded in the
    job's own status, not surfaced as this function's exit code, since a cron
    invocation succeeding just means "the watcher ran", not "every job passed"."""
    pending = _pending_jobs_oldest_first()
    if not pending:
        log.detail("backup-watch: no pending jobs")
        return 0

    for path, job in pending:
        job["status"] = "running"
        job["started_at"] = _now_iso()
        _write_job(path, job)
        log.info(f"backup-watch: running job {job.get('id')} ({job.get('action')})")

        ok, output = _execute(job)

        job["status"] = "done" if ok else "error"
        job["finished_at"] = _now_iso()
        job["output"] = output[
            -8000:
        ]  # cap: job files stay small, tail is what matters
        if not ok and not job.get("error"):
            job["error"] = "backup/restore exited non-zero — see output"
        _write_job(path, job)

        if ok:
            log.success(f"backup-watch: job {job.get('id')} done")
        else:
            log.error(f"backup-watch: job {job.get('id')} failed")

    return 0
