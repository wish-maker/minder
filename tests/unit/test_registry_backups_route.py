"""Unit tests for the plugin-registry backup/restore job-queue endpoints (#870).

The route never touches Docker (see routes/backups.py's module docstring for
why) -- it only reads/writes JSON job files in a tmp_path dir injected via
`backups_dir`/`jobs_dir`, and lists archives from another tmp_path dir. Loaded
by path (shared `routes` package name across services), same pattern as
test_registry_bundles_route.py.
"""

import importlib.util
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth.jwt_middleware import get_current_user

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "routes"
    / "backups.py"
)


def _load_route_module():
    spec = importlib.util.spec_from_file_location("registry_backups_route", _ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _client(tmp_path, *, auth=True, role="admin"):
    backups_dir = tmp_path / "backups"
    jobs_dir = tmp_path / "backup-jobs"
    backups_dir.mkdir()
    mod = _load_route_module()
    app = FastAPI()
    app.include_router(
        mod.build_backups_router(backups_dir=backups_dir, jobs_dir=jobs_dir)
    )
    if auth:
        app.dependency_overrides[get_current_user] = lambda: {
            "sub": "tester",
            "role": role,
        }
    return TestClient(app, raise_server_exceptions=True), backups_dir, jobs_dir


def _touch_archive(backups_dir, name, size=100):
    (backups_dir / name).write_bytes(b"x" * size)


# ── GET /v1/backups ───────────────────────────────────────────────────────────


def test_list_backups_empty(tmp_path):
    client, _, _ = _client(tmp_path)
    r = client.get("/v1/backups")
    assert r.status_code == 200
    assert r.json() == {"archives": []}


def test_list_backups_returns_name_size_and_mtime_newest_first(tmp_path):
    client, backups_dir, _ = _client(tmp_path)
    _touch_archive(backups_dir, "minder-20260101-000000.tar.gz", size=50)
    _touch_archive(backups_dir, "minder-20260201-000000.tar.gz", size=99)
    r = client.get("/v1/backups")
    names = [a["name"] for a in r.json()["archives"]]
    assert names == ["minder-20260201-000000.tar.gz", "minder-20260101-000000.tar.gz"]
    assert r.json()["archives"][0]["size_bytes"] == 99
    assert "modified_at" in r.json()["archives"][0]


def test_list_backups_ignores_non_matching_files(tmp_path):
    client, backups_dir, _ = _client(tmp_path)
    _touch_archive(backups_dir, "minder-20260101-000000.tar.gz")
    (backups_dir / "not-a-backup.txt").write_text("nope", encoding="utf-8")
    (backups_dir / "minder-corrupted.tar.gz").write_text("nope", encoding="utf-8")
    r = client.get("/v1/backups")
    assert [a["name"] for a in r.json()["archives"]] == [
        "minder-20260101-000000.tar.gz"
    ]


def test_list_backups_requires_auth(tmp_path):
    client, _, _ = _client(tmp_path, auth=False)
    assert client.get("/v1/backups").status_code == 401


def test_list_backups_requires_admin_role(tmp_path):
    client, _, _ = _client(tmp_path, role="user")
    assert client.get("/v1/backups").status_code == 403


# ── POST /v1/backups ─────────────────────────────────────────────────────────


def test_trigger_backup_enqueues_a_pending_job(tmp_path):
    client, _, jobs_dir = _client(tmp_path)
    r = client.post("/v1/backups")
    assert r.status_code == 202
    body = r.json()
    assert body["action"] == "backup"
    assert body["status"] == "pending"
    assert body["requested_by"] == "tester"
    on_disk = json.loads((jobs_dir / f"{body['id']}.json").read_text(encoding="utf-8"))
    assert on_disk == body


def test_trigger_backup_requires_admin_role(tmp_path):
    client, _, _ = _client(tmp_path, role="user")
    assert client.post("/v1/backups").status_code == 403


# ── GET /v1/backups/jobs[/id] ─────────────────────────────────────────────────


def test_list_jobs_sorted_newest_first(tmp_path):
    client, _, _ = _client(tmp_path)
    client.post("/v1/backups")
    client.post("/v1/backups")
    r = client.get("/v1/backups/jobs")
    jobs = r.json()["jobs"]
    assert len(jobs) == 2
    assert jobs[0]["requested_at"] >= jobs[1]["requested_at"]


def test_get_job_by_id(tmp_path):
    client, _, _ = _client(tmp_path)
    job = client.post("/v1/backups").json()
    r = client.get(f"/v1/backups/jobs/{job['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == job["id"]


def test_get_unknown_job_is_404(tmp_path):
    client, _, _ = _client(tmp_path)
    assert client.get("/v1/backups/jobs/does-not-exist").status_code == 404


def test_get_job_rejects_path_traversal_in_job_id(tmp_path):
    client, _, jobs_dir = _client(tmp_path)
    # A real file the traversal attempts to reach, one level above jobs_dir.
    secret = jobs_dir.parent / "secret.json"
    secret.write_text('{"leaked": true}', encoding="utf-8")
    r = client.get("/v1/backups/jobs/..%2Fsecret")
    assert r.status_code == 404


def test_read_job_rejects_path_traversal_in_job_id_directly(tmp_path):
    """FastAPI's default (non-``:path``) converter already rejects a `/` in
    a single path segment, so an HTTP-level request can never actually smuggle
    ``../`` into ``job_id`` -- the test above 404s for that reason alone, not
    because of _read_job's own validation. CodeQL's dataflow analysis doesn't
    know about that routing-level restriction, and neither would any future
    caller of _read_job that isn't behind this same route, so this exercises
    the helper directly to prove IT, not just the router, rejects traversal.
    """
    mod = _load_route_module()
    jobs_dir = tmp_path / "backup-jobs"
    jobs_dir.mkdir()
    secret = tmp_path / "secret.json"
    secret.write_text('{"leaked": true}', encoding="utf-8")

    assert mod._read_job(jobs_dir, "../secret") is None
    assert mod._read_job(jobs_dir, "not-32-hex-chars") is None


# ── POST /v1/backups/{name}/restore ──────────────────────────────────────────


def test_trigger_restore_enqueues_a_pending_job(tmp_path):
    client, backups_dir, jobs_dir = _client(tmp_path)
    _touch_archive(backups_dir, "minder-20260101-000000.tar.gz")
    r = client.post(
        "/v1/backups/minder-20260101-000000.tar.gz/restore",
        json={"confirm_filename": "minder-20260101-000000.tar.gz"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["action"] == "restore"
    assert body["archive"] == "minder-20260101-000000.tar.gz"
    assert body["status"] == "pending"
    on_disk = json.loads((jobs_dir / f"{body['id']}.json").read_text(encoding="utf-8"))
    assert on_disk == body


def test_trigger_restore_rejects_confirm_filename_mismatch(tmp_path):
    client, backups_dir, jobs_dir = _client(tmp_path)
    _touch_archive(backups_dir, "minder-20260101-000000.tar.gz")
    r = client.post(
        "/v1/backups/minder-20260101-000000.tar.gz/restore",
        json={"confirm_filename": "minder-99990101-000000.tar.gz"},
    )
    assert r.status_code == 400
    assert list(jobs_dir.glob("*.json")) == []  # nothing enqueued


def test_trigger_restore_404s_for_nonexistent_archive(tmp_path):
    client, _, jobs_dir = _client(tmp_path)
    r = client.post(
        "/v1/backups/minder-20260101-000000.tar.gz/restore",
        json={"confirm_filename": "minder-20260101-000000.tar.gz"},
    )
    assert r.status_code == 404
    assert list(jobs_dir.glob("*.json")) == []


def test_trigger_restore_rejects_path_traversal_in_name(tmp_path):
    client, backups_dir, jobs_dir = _client(tmp_path)
    # A real file the traversal attempts to reach, one level above backups_dir.
    (backups_dir.parent / "secret.tar.gz").write_bytes(b"nope")
    r = client.post(
        "/v1/backups/..%2Fsecret.tar.gz/restore",
        json={"confirm_filename": "../secret.tar.gz"},
    )
    assert r.status_code == 404
    assert list(jobs_dir.glob("*.json")) == []


def test_trigger_restore_requires_admin_role(tmp_path):
    client, backups_dir, _ = _client(tmp_path, role="user")
    _touch_archive(backups_dir, "minder-20260101-000000.tar.gz")
    r = client.post(
        "/v1/backups/minder-20260101-000000.tar.gz/restore",
        json={"confirm_filename": "minder-20260101-000000.tar.gz"},
    )
    assert r.status_code == 403
