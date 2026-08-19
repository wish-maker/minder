"""Backup/restore web UI (#870) — job-queue front end, NOT a Docker orchestrator.

Backup needs `docker exec`/`docker cp` against already-running containers (fits
docker-socket-proxy's existing allowlist), but restore additionally needs `docker
compose up` for every datastore (container-CREATE) — exactly the privilege class
docker-socket-proxy's allowlist was built to deny (#377/#378: "Anything not
matched here is DENIED, including create/exec/kill/... so a compromised registry
still can't host-takeover"). Widening the proxy to cover restore would mean
granting host-takeover-equivalent privilege, not a narrow addition — so this
router never talks to Docker at all.

Instead it only reads/writes small JSON job files in a shared bind-mounted
directory (``/app/backup-jobs``); a host-side cron job (`python -m scripts.setup
backup-watch`, see scripts/setup/backup_jobs.py) does the real work with the same
host-level trust `scripts/setup/backup.py`/`restore.py` have always had. Mirrors
bundles.py's own GitOps split (API sets desired state; a privileged host
reconciler materialises it) for the same "proxy can't create" reason.

All endpoints are admin-only: unlike GET /v1/bundles (deliberately open),
archive existence/timestamps are treated as sensitive operational detail here,
same rationale as GET /v1/containers/{name}/logs.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from shared.auth.jwt_middleware import require_role

_BACKUPS_DIR = Path("/app/backups")
_JOBS_DIR = Path("/app/backup-jobs")

# Matches backup.py's own archive naming: minder-<%Y%m%d-%H%M%S>.tar.gz. Used both
# to filter GET /v1/backups' listing and, more importantly, as an allowlist for
# the restore target — `name` comes from the URL path, so this is what stands
# between an admin-only-gated request and an arbitrary filesystem path.
_ARCHIVE_NAME_RE = re.compile(r"^minder-\d{8}-\d{6}\.tar\.gz$")

# job_id is always a uuid.uuid4().hex generated server-side (see _write_job's
# callers) -- this is the analogous allowlist for the job-lookup path, same
# rationale as _ARCHIVE_NAME_RE above.
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_MAX_JOBS_LISTED = 50


def _find_by_name(directory: Path, filename: str, glob_pattern: str) -> "Path | None":
    """Resolve ``filename`` to a real path by matching it against
    ``directory``'s own listing, rather than joining ``filename`` onto
    ``directory`` directly.

    The untrusted string (``job_id``/``name``) is validated against a fixed-
    format allowlist regex before this runs, which already makes traversal
    impossible on its own -- but CodeQL's path-injection dataflow analysis
    doesn't credit a regex match as clearing taint, and flagged even a
    resolve()+relative_to() join-then-verify helper tried here first.
    Matching against an enumerated, already-safe directory listing instead
    means the
    untrusted string never flows into a path-construction expression at all,
    which sidesteps that class of finding rather than fighting its sanitizer
    recognition.
    """
    try:
        candidates = directory.glob(glob_pattern)
    except OSError:
        return None
    for path in candidates:
        if path.name == filename:
            return path
    return None


def _now_iso() -> str:
    """UTC, second precision, lexicographically sortable — kept byte-identical to
    scripts/setup/backup_jobs.py's own `_now_iso` by convention (duplicated, not
    imported: this container never has scripts/setup on its path, see the module
    docstring)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _list_archives(backups_dir: Path) -> list[dict]:
    try:
        paths = sorted(backups_dir.glob("minder-*.tar.gz"), reverse=True)
    except OSError:
        return []
    archives = []
    for path in paths:
        if not _ARCHIVE_NAME_RE.match(path.name):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        archives.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return archives


def _write_job(jobs_dir: Path, job: dict) -> None:
    jobs_dir.mkdir(parents=True, exist_ok=True)
    (jobs_dir / f"{job['id']}.json").write_text(json.dumps(job), encoding="utf-8")


def _read_job(jobs_dir: Path, job_id: str) -> "dict | None":
    if not _JOB_ID_RE.match(job_id):
        return None
    path = _find_by_name(jobs_dir, f"{job_id}.json", "*.json")
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _list_jobs(jobs_dir: Path, limit: int) -> list[dict]:
    try:
        paths = list(jobs_dir.glob("*.json"))
    except OSError:
        return []
    jobs = []
    for path in paths:
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    jobs.sort(key=lambda j: j.get("requested_at", ""), reverse=True)
    return jobs[:limit]


def build_backups_router(*, backups_dir=None, jobs_dir=None) -> APIRouter:
    """``backups_dir``/``jobs_dir`` are test-injection seams (tmp_path in tests),
    same DI pattern as bundles.py's ``container_ops``."""
    router = APIRouter(tags=["Backups"])
    b_dir = backups_dir or _BACKUPS_DIR
    j_dir = jobs_dir or _JOBS_DIR

    @router.get("/v1/backups")
    async def list_backups(current_user: dict = Depends(require_role("admin"))):
        return {"archives": _list_archives(b_dir)}

    @router.post("/v1/backups", status_code=202)
    async def trigger_backup(current_user: dict = Depends(require_role("admin"))):
        job = {
            "id": uuid.uuid4().hex,
            "action": "backup",
            "archive": None,
            "status": "pending",
            "requested_by": current_user.get("sub", "?"),
            "requested_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "output": "",
        }
        _write_job(j_dir, job)
        return job

    @router.get("/v1/backups/jobs")
    async def list_backup_jobs(current_user: dict = Depends(require_role("admin"))):
        return {"jobs": _list_jobs(j_dir, _MAX_JOBS_LISTED)}

    @router.get("/v1/backups/jobs/{job_id}")
    async def get_backup_job(
        job_id: str, current_user: dict = Depends(require_role("admin"))
    ):
        job = _read_job(j_dir, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @router.post("/v1/backups/{name}/restore", status_code=202)
    async def trigger_restore(
        name: str,
        body: dict = Body(...),
        current_user: dict = Depends(require_role("admin")),
    ):
        """Restore is destructive (overwrites live data), so beyond admin-only
        gating this requires the caller to echo the exact archive filename back
        in the body — a deliberate extra confirmation step, not a security
        control (the admin JWT already authorizes the action)."""
        if not _ARCHIVE_NAME_RE.match(name):
            raise HTTPException(status_code=404, detail="Backup archive not found")
        archive_path = _find_by_name(b_dir, name, "minder-*.tar.gz")
        if archive_path is None or not archive_path.is_file():
            raise HTTPException(status_code=404, detail="Backup archive not found")
        if body.get("confirm_filename") != name:
            raise HTTPException(
                status_code=400,
                detail="confirm_filename must exactly match the archive being restored",
            )
        job = {
            "id": uuid.uuid4().hex,
            "action": "restore",
            "archive": name,
            "status": "pending",
            "requested_by": current_user.get("sub", "?"),
            "requested_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "output": "",
        }
        _write_job(j_dir, job)
        return job

    return router
