"""Marketplace submission / review workflow routes (#402, Phase 1).

The human side of the catalog: a developer's plugin listing is created as a
``draft`` via ``POST /v1/marketplace/plugins`` (routes/marketplace.py, a
non-service caller), then moves through submit → review → approve here before it
becomes publicly visible. First-party module plugins auto-synced by the plugin
registry (`origin='first_party'`) never enter this flow — they're created already
`approved`.

Auth model (matches the rest of marketplace):
- developer actions (submit / list-mine) — any authenticated user, scoped to
  their own submissions by the JWT `sub`.
- reviewer actions (queue / claim / approve / reject / archive) — admin only
  (``require_role("admin")``), same convention as model pull/delete and bundle
  enable/disable elsewhere.

Every accepted transition is validated against the state machine in
``core/review.py`` (409 on an illegal move) and appends an audit row.
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from core.database import get_pool
from core.plugin_repository import PLUGIN_COLUMNS, row_to_plugin_response
from core.review import (
    APPROVED,
    ARCHIVED,
    IN_REVIEW,
    REJECTED,
    SUBMITTED,
    InvalidTransition,
    ensure_transition_allowed,
    record_review,
)
from core.validation import ensure_valid_plugin_id
from fastapi import APIRouter, Depends, HTTPException
from models.plugin import PluginListResponse, PluginResponse
from pydantic import BaseModel

from shared.auth.jwt_middleware import (
    get_current_user_or_service,
    require_role,
    require_role_or_service,
)
from shared.errors import backend_http_error

logger = logging.getLogger("minder.marketplace.submissions")

router = APIRouter(prefix="/v1/marketplace/submissions", tags=["Submissions"])


class ReviewActionRequest(BaseModel):
    """Optional reviewer notes for a transition (required on reject)."""

    notes: Optional[str] = None


async def _fetch_status_row(conn, plugin_id: str):
    """Return (status, submitted_by, origin) for a plugin, or None if unknown."""
    return await conn.fetchrow(
        "SELECT status, submitted_by, origin FROM marketplace_plugins WHERE id = $1",
        plugin_id,
    )


async def _apply_transition(
    plugin_id: str,
    to_status: str,
    actor: dict,
    *,
    set_reviewer: bool = False,
    notes: Optional[str] = None,
) -> PluginResponse:
    """Validate + persist a submission transition atomically, with an audit row.

    ``set_reviewer`` stamps reviewed_by/reviewed_at (the reviewer actions);
    ``notes`` is stored on the plugin (reject feedback) and in the audit row.
    """
    ensure_valid_plugin_id(plugin_id)
    pool = await get_pool()
    actor_sub = actor.get("sub", "unknown")
    actor_role = actor.get("role")
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await _fetch_status_row(conn, plugin_id)
                if row is None:
                    raise HTTPException(status_code=404, detail="Submission not found")
                from_status = row["status"]
                try:
                    ensure_transition_allowed(from_status, to_status)
                except InvalidTransition as e:
                    raise HTTPException(status_code=409, detail=str(e))

                sets = ["status = $2", "updated_at = NOW()"]
                params: List[Any] = [plugin_id, to_status]
                if notes is not None:
                    params.append(notes)
                    sets.append(f"review_notes = ${len(params)}")
                # Naive-UTC to match the naive TIMESTAMP columns (asyncpg rejects
                # aware datetimes on `timestamp`); same convention as core/licensing.py.
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if set_reviewer:
                    params.append(actor_sub)
                    sets.append(f"reviewed_by = ${len(params)}")
                    params.append(now)
                    sets.append(f"reviewed_at = ${len(params)}")
                if to_status == SUBMITTED:
                    params.append(now)
                    sets.append(f"submitted_at = ${len(params)}")

                # Compare-and-swap on the status we validated (#941): the
                # SELECT above doesn't lock, so under READ COMMITTED a concurrent
                # reviewer action could change status between our read and this
                # write. Guarding the UPDATE with `AND status = from_status`
                # makes the transition atomic — the loser of a race matches 0
                # rows and gets a 409 (instead of silently clobbering the other
                # transition and writing a bogus audit row).
                params.append(from_status)
                guard_idx = len(params)
                updated = await conn.fetchrow(
                    f"UPDATE marketplace_plugins SET {', '.join(sets)} "
                    f"WHERE id = $1 AND status = ${guard_idx} "
                    f"RETURNING {PLUGIN_COLUMNS}",
                    *params,
                )
                if updated is None:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Submission status changed concurrently; "
                            "re-read and retry"
                        ),
                    )
                await record_review(
                    conn,
                    plugin_id=plugin_id,
                    from_status=from_status,
                    to_status=to_status,
                    actor=actor_sub,
                    actor_role=actor_role,
                    notes=notes,
                )
                return row_to_plugin_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        raise backend_http_error(e, "Submission transition")


@router.get("/mine", response_model=PluginListResponse)
async def my_submissions(
    current_user: dict = Depends(get_current_user_or_service),
):
    """List the caller's own submissions (any status), newest first — scoped to
    the JWT ``sub`` so one developer can't see another's drafts/rejections."""
    pool = await get_pool()
    owner = current_user.get("sub")
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {PLUGIN_COLUMNS} FROM marketplace_plugins "
                f"WHERE submitted_by = $1 ORDER BY updated_at DESC",
                owner,
            )
        plugins = [row_to_plugin_response(r) for r in rows]
        return PluginListResponse(
            plugins=plugins,
            count=len(plugins),
            total=len(plugins),
            page=1,
            page_size=len(plugins),
            total_pages=1,
            limit=len(plugins),
            offset=0,
        )
    except Exception as e:
        raise backend_http_error(e, "Listing submissions")


@router.post("/{plugin_id}/submit", response_model=PluginResponse)
async def submit_for_review(
    plugin_id: str,
    current_user: dict = Depends(get_current_user_or_service),
):
    """Developer action: move an own ``draft``/``rejected`` submission to
    ``submitted`` (into the review queue). Only the submission's owner (or an
    admin/service) may submit it; a non-owner gets 404 (same message as an
    unknown id — no reason to reveal another tenant's submission exists)."""
    ensure_valid_plugin_id(plugin_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await _fetch_status_row(conn, plugin_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    is_privileged = current_user.get("role") in ("admin", "service")
    if not is_privileged and row["submitted_by"] != current_user.get("sub"):
        raise HTTPException(status_code=404, detail="Submission not found")
    return await _apply_transition(plugin_id, SUBMITTED, current_user)


@router.get("", response_model=PluginListResponse)
async def review_queue(
    status: str = SUBMITTED,
    current_user: dict = Depends(require_role("admin")),
):
    """Admin review queue: submissions in a given status (default ``submitted``),
    oldest-first so the longest-waiting is reviewed next."""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {PLUGIN_COLUMNS} FROM marketplace_plugins "
                f"WHERE status = $1 AND origin = 'submitted' "
                f"ORDER BY submitted_at ASC NULLS LAST",
                status,
            )
        plugins = [row_to_plugin_response(r) for r in rows]
        return PluginListResponse(
            plugins=plugins,
            count=len(plugins),
            total=len(plugins),
            page=1,
            page_size=len(plugins),
            total_pages=1,
            limit=len(plugins),
            offset=0,
        )
    except Exception as e:
        raise backend_http_error(e, "Listing the review queue")


@router.post("/{plugin_id}/claim", response_model=PluginResponse)
async def claim_review(
    plugin_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Admin: take a ``submitted`` submission into ``in_review`` (records the
    reviewer)."""
    return await _apply_transition(
        plugin_id, IN_REVIEW, current_user, set_reviewer=True
    )


@router.post("/{plugin_id}/approve", response_model=PluginResponse)
async def approve_submission(
    plugin_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Admin: approve an ``in_review`` submission → ``approved`` (publicly
    visible via the existing catalog read paths)."""
    return await _apply_transition(plugin_id, APPROVED, current_user, set_reviewer=True)


@router.post("/{plugin_id}/reject", response_model=PluginResponse)
async def reject_submission(
    plugin_id: str,
    body: ReviewActionRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """Admin: reject a ``submitted``/``in_review`` submission (feedback
    **required** so the developer knows what to fix before resubmitting)."""
    if not body.notes or not body.notes.strip():
        raise HTTPException(
            status_code=422, detail="review notes are required when rejecting"
        )
    return await _apply_transition(
        plugin_id, REJECTED, current_user, set_reviewer=True, notes=body.notes.strip()
    )


@router.post("/{plugin_id}/archive", response_model=PluginResponse)
async def archive_submission(
    plugin_id: str,
    current_user: dict = Depends(require_role_or_service("admin")),
):
    """Admin/service: archive (delist) an ``approved`` plugin."""
    return await _apply_transition(plugin_id, ARCHIVED, current_user, set_reviewer=True)
