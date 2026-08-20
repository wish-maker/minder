"""Submission/review state machine for the marketplace (#402).

A developer-submitted plugin listing moves through a small, explicit lifecycle
before it becomes publicly visible, so a listing can't be self-published without
review (the prior gap: any authenticated user could POST an auto-approved,
immediately-visible listing). First-party module plugins auto-synced by the
plugin registry bypass this entirely (`origin='first_party'`, created already
`approved`).

    DRAFT ─submit▶ SUBMITTED ─claim▶ IN_REVIEW ─approve▶ APPROVED (visible)
      ▲                │                 │
      └── (developer) ─┘                 └─reject▶ REJECTED ─(resubmit)▶ SUBMITTED
                        ARCHIVED  ← from APPROVED (delist)

APPROVED is the publicly-visible terminal state (the existing read paths already
key on `status='approved'`); a dedicated PUBLISHED gate is deferred to a later
phase. Every accepted transition appends a row to ``marketplace_plugin_reviews``
so there's a full audit trail of who moved a submission and why.
"""

from typing import Dict, Optional, Set

from models.plugin import PluginStatus

DRAFT = PluginStatus.DRAFT.value
SUBMITTED = PluginStatus.SUBMITTED.value
IN_REVIEW = PluginStatus.IN_REVIEW.value
APPROVED = PluginStatus.APPROVED.value
REJECTED = PluginStatus.REJECTED.value
ARCHIVED = PluginStatus.ARCHIVED.value

# Allowed transitions: from-status -> the set of states it may move to.
ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    DRAFT: {SUBMITTED},
    SUBMITTED: {IN_REVIEW, REJECTED},
    IN_REVIEW: {APPROVED, REJECTED},
    REJECTED: {SUBMITTED},
    APPROVED: {ARCHIVED},
    # A legacy pre-#402 auto-approved listing can still be archived.
    "pending": {APPROVED, REJECTED, ARCHIVED},
}


class InvalidTransition(ValueError):
    """Raised when a submission-state transition isn't allowed from the current
    state — the route turns this into a 409."""


def ensure_transition_allowed(from_status: Optional[str], to_status: str) -> None:
    """Raise :class:`InvalidTransition` unless ``from_status -> to_status`` is a
    permitted move (a no-op self-transition is rejected too — the caller should
    handle "already in that state" explicitly if it wants idempotence)."""
    allowed = ALLOWED_TRANSITIONS.get(from_status or "", set())
    if to_status not in allowed:
        raise InvalidTransition(
            f"Cannot move a submission from '{from_status}' to '{to_status}'. "
            f"Allowed from '{from_status}': {sorted(allowed) or 'none'}."
        )


async def record_review(
    conn,
    *,
    plugin_id: str,
    from_status: Optional[str],
    to_status: str,
    actor: str,
    actor_role: Optional[str],
    notes: Optional[str] = None,
) -> None:
    """Append one immutable audit row for a transition (#402)."""
    await conn.execute(
        """
        INSERT INTO marketplace_plugin_reviews
            (plugin_id, from_status, to_status, actor, actor_role, notes)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        plugin_id,
        from_status,
        to_status,
        actor,
        actor_role,
        notes,
    )
