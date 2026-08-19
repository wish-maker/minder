"""Unit tests for scripts/setup/backup_jobs.py -- the `backup-watch` host-side
executor for the web UI's backup/restore job queue (#870).

No Docker: backup.run()/restore.run() are monkeypatched to recorders. Job files
are plain JSON in a tmp_path dir, matching the contract routes/backups.py (the
plugin-registry side, which can't import this module -- see its own docstring)
writes into config.BACKUP_JOBS_DIR.
"""

import json

import pytest

from scripts.setup import backup_jobs


@pytest.fixture
def jobs_dir(monkeypatch, tmp_path):
    d = tmp_path / "backup-jobs"
    d.mkdir()
    monkeypatch.setattr(backup_jobs.config, "BACKUP_JOBS_DIR", d)
    for fn in ("info", "success", "warn", "error", "detail"):
        monkeypatch.setattr(backup_jobs.log, fn, lambda m: None)
    return d


def _write_job(jobs_dir, job_id, **overrides):
    job = {
        "id": job_id,
        "action": "backup",
        "archive": None,
        "status": "pending",
        "requested_by": "alice",
        "requested_at": "2026-08-19T00:00:00Z",
        "started_at": None,
        "finished_at": None,
        "error": None,
        "output": "",
    }
    job.update(overrides)
    (jobs_dir / f"{job_id}.json").write_text(json.dumps(job), encoding="utf-8")
    return job


def test_no_pending_jobs_is_a_no_op(jobs_dir):
    assert backup_jobs.run_pending() == 0


def test_backup_job_runs_backup_module_and_marks_done(jobs_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(
        backup_jobs.backup_module, "run", lambda: calls.append("backup") or 0
    )
    _write_job(jobs_dir, "job-1", action="backup")

    rc = backup_jobs.run_pending()

    assert rc == 0
    assert calls == ["backup"]
    result = json.loads((jobs_dir / "job-1.json").read_text(encoding="utf-8"))
    assert result["status"] == "done"
    assert result["started_at"] and result["finished_at"]


def test_restore_job_passes_archive_to_restore_module(jobs_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(
        backup_jobs.restore_module,
        "run",
        lambda archive: calls.append(archive) or 0,
    )
    _write_job(
        jobs_dir, "job-2", action="restore", archive="minder-20260101-000000.tar.gz"
    )

    backup_jobs.run_pending()

    assert calls == ["minder-20260101-000000.tar.gz"]
    result = json.loads((jobs_dir / "job-2.json").read_text(encoding="utf-8"))
    assert result["status"] == "done"


def test_nonzero_exit_marks_job_as_error(jobs_dir, monkeypatch):
    monkeypatch.setattr(backup_jobs.backup_module, "run", lambda: 1)
    _write_job(jobs_dir, "job-3")

    backup_jobs.run_pending()

    result = json.loads((jobs_dir / "job-3.json").read_text(encoding="utf-8"))
    assert result["status"] == "error"
    assert result["error"]


def test_unhandled_exception_is_caught_and_marks_job_as_error(jobs_dir, monkeypatch):
    def _boom():
        raise RuntimeError("docker vanished")

    monkeypatch.setattr(backup_jobs.backup_module, "run", _boom)
    _write_job(jobs_dir, "job-4")

    rc = backup_jobs.run_pending()  # must not raise

    assert rc == 0
    result = json.loads((jobs_dir / "job-4.json").read_text(encoding="utf-8"))
    assert result["status"] == "error"
    assert "docker vanished" in result["output"]


def test_only_pending_jobs_are_processed(jobs_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(backup_jobs.backup_module, "run", lambda: calls.append(1) or 0)
    _write_job(jobs_dir, "done-job", status="done")
    _write_job(jobs_dir, "running-job", status="running")
    _write_job(jobs_dir, "pending-job", status="pending")

    backup_jobs.run_pending()

    assert len(calls) == 1
    done = json.loads((jobs_dir / "done-job.json").read_text(encoding="utf-8"))
    running = json.loads((jobs_dir / "running-job.json").read_text(encoding="utf-8"))
    assert done["status"] == "done"  # untouched
    assert running["status"] == "running"  # untouched


def test_pending_jobs_are_processed_oldest_first(jobs_dir, monkeypatch):
    order = []
    monkeypatch.setattr(
        backup_jobs.backup_module, "run", lambda: order.append("backup") or 0
    )
    monkeypatch.setattr(
        backup_jobs.restore_module,
        "run",
        lambda archive: order.append(archive) or 0,
    )
    _write_job(
        jobs_dir,
        "newer",
        action="restore",
        archive="second",
        requested_at="2026-08-19T02:00:00Z",
    )
    _write_job(
        jobs_dir,
        "older",
        action="restore",
        archive="first",
        requested_at="2026-08-19T01:00:00Z",
    )

    backup_jobs.run_pending()

    assert order == ["first", "second"]


def test_corrupt_job_file_is_skipped_not_raised(jobs_dir):
    (jobs_dir / "corrupt.json").write_text("{not valid json", encoding="utf-8")

    assert backup_jobs.run_pending() == 0
