"""Unit tests for the marketplace submission/review workflow (#402, Phase 1):
core/review.py's state machine + routes/submissions.py's transitions, auth
gates, ownership scoping, and audit writes.

Isolated-import pattern matches test_marketplace_licensing_routes_authz.py (the
marketplace service dir is loaded by path; core/routes/models/config evicted +
restored so sibling services' same-named packages aren't poisoned).
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(*module_paths: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


submissions, review = _isolated_import("routes.submissions", "core.review")


# ── core/review.py: the state machine ────────────────────────────────────────


def test_allowed_transitions():
    review.ensure_transition_allowed("draft", "submitted")
    review.ensure_transition_allowed("submitted", "in_review")
    review.ensure_transition_allowed("submitted", "rejected")
    review.ensure_transition_allowed("in_review", "approved")
    review.ensure_transition_allowed("in_review", "rejected")
    review.ensure_transition_allowed("rejected", "submitted")
    review.ensure_transition_allowed("approved", "archived")


@pytest.mark.parametrize(
    "frm,to",
    [
        ("draft", "approved"),  # can't skip review
        ("draft", "in_review"),
        ("submitted", "approved"),  # must be claimed first
        ("approved", "submitted"),  # can't un-publish back into the queue
        ("submitted", "submitted"),  # no-op self-transition rejected
        (None, "approved"),  # unknown/absent state
    ],
)
def test_disallowed_transitions_raise(frm, to):
    with pytest.raises(review.InvalidTransition):
        review.ensure_transition_allowed(frm, to)


# ── routes/submissions.py: transactional transition helper ───────────────────


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Conn:
    """Fake asyncpg conn for the transition path: first fetchrow returns the
    current (status, submitted_by, origin); the second (the UPDATE ... RETURNING)
    returns the updated row; execute() records the audit insert."""

    def __init__(self, status_row, updated_row):
        self._status_row = status_row
        self._updated_row = updated_row
        self.executed = []

    def transaction(self):
        return _Txn()

    async def fetchrow(self, query, *args):
        # Route by query: the UPDATE...RETURNING yields the updated row; every
        # SELECT (ownership check + the transition's status lookup) yields the
        # current status row.
        if "UPDATE marketplace_plugins" in query:
            return self._updated_row
        return self._status_row

    async def fetch(self, query, *args):
        return []

    async def execute(self, query, *args):
        self.executed.append((query, args))


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return _Ctx()


def _updated_row(status):
    # Minimal row satisfying row_to_plugin_response (asyncpg Record `in` works on
    # a plain dict here since row_to_plugin_response only does `key in row`).
    return {
        "id": "11111111-1111-4111-8111-111111111111",
        "name": "dev-plugin",
        "display_name": "Dev Plugin",
        "description": None,
        "author": "dev",
        "repository_url": None,
        "distribution_type": "git",
        "docker_image": None,
        "current_version": None,
        "pricing_model": "free",
        "base_tier": "community",
        "status": status,
        "featured": False,
        "download_count": 0,
        "rating_average": None,
        "rating_count": 0,
        "created_at": __import__("datetime").datetime(2026, 1, 1),
        "updated_at": __import__("datetime").datetime(2026, 1, 1),
        "published_at": None,
        "developer_id": None,
        "category_id": None,
        "requires_services": "[]",
        "origin": "submitted",
        "submitted_by": "alice",
        "reviewed_by": None,
        "review_notes": None,
    }


def _patch_pool(monkeypatch, conn):
    monkeypatch.setattr(submissions, "get_pool", AsyncMock(return_value=_Pool(conn)))
    monkeypatch.setattr(submissions, "ensure_valid_plugin_id", lambda pid: pid)


PID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
async def test_claim_moves_submitted_to_in_review_and_audits(monkeypatch):
    conn = _Conn(
        status_row={
            "status": "submitted",
            "submitted_by": "alice",
            "origin": "submitted",
        },
        updated_row=_updated_row("in_review"),
    )
    _patch_pool(monkeypatch, conn)

    result = await submissions.claim_review(
        PID, current_user={"sub": "admin-1", "role": "admin"}
    )
    assert result.status.value == "in_review"
    # exactly one audit row written, from submitted -> in_review by the admin
    assert len(conn.executed) == 1
    audit_args = conn.executed[0][1]
    assert "submitted" in audit_args and "in_review" in audit_args
    assert "admin-1" in audit_args


@pytest.mark.asyncio
async def test_illegal_transition_is_409(monkeypatch):
    from fastapi import HTTPException

    conn = _Conn(
        status_row={"status": "draft", "submitted_by": "alice", "origin": "submitted"},
        updated_row=_updated_row("approved"),
    )
    _patch_pool(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        # draft -> approved (an approve action) is not allowed
        await submissions.approve_submission(
            PID, current_user={"sub": "admin-1", "role": "admin"}
        )
    assert exc.value.status_code == 409
    assert conn.executed == []  # no audit row on a rejected transition


@pytest.mark.asyncio
async def test_concurrent_transition_loses_the_cas_and_409s(monkeypatch):
    """#941: the status validated by the SELECT was changed by a concurrent
    reviewer action before our UPDATE. The compare-and-swap (`AND status =
    from_status`) matches 0 rows -> None -> 409, and NO audit row is written."""
    from fastapi import HTTPException

    conn = _Conn(
        status_row={
            "status": "submitted",
            "submitted_by": "alice",
            "origin": "submitted",
        },
        updated_row=None,  # UPDATE ... AND status=from_status matched nothing
    )
    _patch_pool(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        await submissions.claim_review(
            PID, current_user={"sub": "admin-1", "role": "admin"}
        )
    assert exc.value.status_code == 409
    assert conn.executed == []  # audit row is written only after a successful CAS


@pytest.mark.asyncio
async def test_transition_on_unknown_plugin_is_404(monkeypatch):
    from fastapi import HTTPException

    conn = _Conn(status_row=None, updated_row=None)
    _patch_pool(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        await submissions.claim_review(
            PID, current_user={"sub": "admin-1", "role": "admin"}
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_requires_notes(monkeypatch):
    from fastapi import HTTPException

    conn = _Conn(
        status_row={
            "status": "in_review",
            "submitted_by": "alice",
            "origin": "submitted",
        },
        updated_row=_updated_row("rejected"),
    )
    _patch_pool(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        await submissions.reject_submission(
            PID,
            submissions.ReviewActionRequest(notes="   "),
            current_user={"sub": "admin-1", "role": "admin"},
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_reject_with_notes_records_them(monkeypatch):
    conn = _Conn(
        status_row={
            "status": "in_review",
            "submitted_by": "alice",
            "origin": "submitted",
        },
        updated_row=_updated_row("rejected"),
    )
    _patch_pool(monkeypatch, conn)

    result = await submissions.reject_submission(
        PID,
        submissions.ReviewActionRequest(notes="needs a license"),
        current_user={"sub": "admin-1", "role": "admin"},
    )
    assert result.status.value == "rejected"
    assert any("needs a license" in a for a in conn.executed[0][1])


@pytest.mark.asyncio
async def test_submit_rejects_a_non_owner(monkeypatch):
    from fastapi import HTTPException

    # The submission belongs to alice; bob must not be able to submit it, and
    # must not even learn it exists (same 404 as an unknown id).
    conn = _Conn(
        status_row={"status": "draft", "submitted_by": "alice", "origin": "submitted"},
        updated_row=_updated_row("submitted"),
    )
    _patch_pool(monkeypatch, conn)

    with pytest.raises(HTTPException) as exc:
        await submissions.submit_for_review(
            PID, current_user={"sub": "bob", "role": "user"}
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_submit_allows_the_owner(monkeypatch):
    conn = _Conn(
        status_row={"status": "draft", "submitted_by": "alice", "origin": "submitted"},
        updated_row=_updated_row("submitted"),
    )
    _patch_pool(monkeypatch, conn)

    result = await submissions.submit_for_review(
        PID, current_user={"sub": "alice", "role": "user"}
    )
    assert result.status.value == "submitted"


# ── auth wiring: reviewer routes are admin-gated ─────────────────────────────


def _route_dep(path_suffix, method="POST"):
    route = next(
        r
        for r in submissions.router.routes
        if getattr(r, "path", "").endswith(path_suffix)
        and method in (getattr(r, "methods", None) or set())
    )
    return route.dependant.dependencies[0].call


@pytest.mark.asyncio
async def test_reviewer_routes_are_admin_gated():
    from fastapi import HTTPException

    for suffix in ("/claim", "/approve", "/reject"):
        gate = _route_dep(suffix)
        with pytest.raises(HTTPException) as exc:
            await gate(user={"sub": "u", "role": "user"})
        assert exc.value.status_code == 403
        admin = await gate(user={"sub": "a", "role": "admin"})
        assert admin["role"] == "admin"


@pytest.mark.asyncio
async def test_review_queue_is_admin_gated():
    from fastapi import HTTPException

    gate = _route_dep("/submissions", method="GET")
    with pytest.raises(HTTPException) as exc:
        await gate(user={"sub": "u", "role": "user"})
    assert exc.value.status_code == 403
