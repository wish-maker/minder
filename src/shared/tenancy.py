"""Canonical per-user tenancy for AI-facing data (Phase 1 of the tenancy model).

The platform correlates data across users while keeping each user's data private.
Both are satisfied by tagging every AI-facing artifact with an ``owner_id`` (a
user's JWT ``sub``, or ``internal-service`` for the service principal) and a
``visibility`` (``shared`` | ``private``), then always reading with the filter::

    visibility = 'shared'  OR  owner_id = <current_user>

so the AI correlates over ``shared ∪ self`` and cross-user private leakage is
structurally impossible. See ``docs/architecture/tenancy-and-correlation.md``.

This module unifies the three divergent owner-resolution implementations that grew
independently — graph-rag's ``_owner_id`` (``owner_id``, #782), rag-pipeline's inline
``current_user.get("sub")`` (``owner_user_id``, #943), and the marketplace/conversation
``user_id`` convention — onto ONE helper, ONE column name (``owner_id``), and ONE
access predicate. Services adopt these instead of hand-rolling ownership checks.
"""

from typing import Optional

from fastapi import HTTPException

# The owner_id of the internal service principal (the X-Service-Token identity),
# matching get_current_user_or_service's synthesized sub.
SERVICE_OWNER = "internal-service"


class Visibility:
    """The visibility tag on an AI-facing artifact.

    ``PRIVATE`` — only the owner (and privileged principals) may see it.
    ``SHARED``  — visible to everyone (public reference data, e.g. a market price).
    """

    PRIVATE = "private"
    SHARED = "shared"
    ALL = (PRIVATE, SHARED)


# Roles that see across all tenants: the internal service (does cross-user
# dispatch/sync) and operators. A regular user's role is "user".
_PRIVILEGED_ROLES = ("service", "admin")


def is_privileged(current_user: dict) -> bool:
    """True if the caller sees across all tenants (service or admin)."""
    return current_user.get("role") in _PRIVILEGED_ROLES


def resolve_owner_id(current_user: dict) -> str:
    """The caller's stable tenant identity — the value to STAMP on data they create.

    A user JWT carries ``sub``; the internal service token resolves to
    ``sub == "internal-service"`` (its own scope). ``sub`` is guaranteed present by
    ``get_current_user`` / ``get_current_user_or_service``, but this defends
    against a token missing ``sub`` so it can never silently collapse into another
    tenant's (empty) scope — raises 401 instead.
    """
    owner = current_user.get("sub")
    if not owner:
        raise HTTPException(status_code=401, detail="Token is missing a subject (sub)")
    return str(owner)


def is_visible_to(
    current_user: dict,
    owner_id: Optional[str],
    visibility: Optional[str] = None,
) -> bool:
    """Whether ``current_user`` may READ an artifact owned by ``owner_id``.

    The canonical predicate behind ``visibility='shared' OR owner_id=self``:

    - privileged principals (service/admin) → always (cross-tenant by role);
    - ``visibility == 'shared'`` → always (public reference data);
    - ``owner_id is None`` → legacy/unowned, treated as open for backward-compat
      during migration (the migration backfills a real owner + visibility);
    - otherwise only the owner (``owner_id == caller's sub``).

    ``owner_id`` set + ``visibility`` unset falls through to the owner check, i.e.
    an owned-but-untagged row is treated as private to its owner (the safe default).
    """
    if is_privileged(current_user):
        return True
    if visibility == Visibility.SHARED:
        return True
    if owner_id is None:
        return True
    return str(owner_id) == current_user.get("sub")
