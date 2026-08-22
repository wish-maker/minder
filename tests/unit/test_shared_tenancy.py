"""Unit tests for shared/tenancy.py -- the canonical per-user tenancy helpers
(resolve_owner_id / is_privileged / is_visible_to / Visibility) that unify
ownership across services (Phase 1 of the tenancy model). See
docs/architecture/tenancy-and-correlation.md.
"""

import pytest
from fastapi import HTTPException

import shared.tenancy as tenancy

# --- resolve_owner_id -------------------------------------------------------


def test_resolve_owner_id_returns_sub():
    assert tenancy.resolve_owner_id({"sub": "alice", "role": "user"}) == "alice"


def test_resolve_owner_id_service_principal():
    assert (
        tenancy.resolve_owner_id({"sub": "internal-service", "role": "service"})
        == tenancy.SERVICE_OWNER
    )


def test_resolve_owner_id_stringifies_non_str_sub():
    # A numeric sub (some IdPs) must come back as a str so downstream string
    # comparisons/keys are consistent.
    assert tenancy.resolve_owner_id({"sub": 84, "role": "user"}) == "84"


def test_resolve_owner_id_missing_sub_401():
    with pytest.raises(HTTPException) as exc:
        tenancy.resolve_owner_id({"role": "user"})
    assert exc.value.status_code == 401


def test_resolve_owner_id_empty_sub_401():
    with pytest.raises(HTTPException) as exc:
        tenancy.resolve_owner_id({"sub": "", "role": "user"})
    assert exc.value.status_code == 401


# --- is_privileged ----------------------------------------------------------


@pytest.mark.parametrize(
    "role,expected",
    [("service", True), ("admin", True), ("user", False), (None, False)],
)
def test_is_privileged(role, expected):
    assert tenancy.is_privileged({"sub": "x", "role": role}) is expected


# --- is_visible_to ----------------------------------------------------------


def test_owner_sees_own_private_artifact():
    caller = {"sub": "alice", "role": "user"}
    assert tenancy.is_visible_to(caller, owner_id="alice", visibility="private")


def test_non_owner_denied_private_artifact():
    caller = {"sub": "bob", "role": "user"}
    assert not tenancy.is_visible_to(caller, owner_id="alice", visibility="private")


def test_shared_artifact_visible_to_everyone():
    caller = {"sub": "bob", "role": "user"}
    assert tenancy.is_visible_to(caller, owner_id="alice", visibility="shared")


def test_privileged_sees_any_private_artifact():
    for role in ("service", "admin"):
        caller = {"sub": "someone", "role": role}
        assert tenancy.is_visible_to(caller, owner_id="alice", visibility="private")


def test_null_owner_is_legacy_open():
    # Backward-compat: unowned rows (pre-migration) stay visible; migration
    # backfills a real owner + visibility later.
    caller = {"sub": "bob", "role": "user"}
    assert tenancy.is_visible_to(caller, owner_id=None, visibility=None)


def test_owned_but_untagged_defaults_to_private_to_owner():
    # owner_id set, visibility unset -> falls through to the owner check.
    owner = {"sub": "alice", "role": "user"}
    other = {"sub": "bob", "role": "user"}
    assert tenancy.is_visible_to(owner, owner_id="alice", visibility=None)
    assert not tenancy.is_visible_to(other, owner_id="alice", visibility=None)


def test_owner_id_type_coercion_in_visibility_check():
    # A UUID/int owner_id from a raw DB row must still match the string sub.
    caller = {"sub": "84", "role": "user"}
    assert tenancy.is_visible_to(caller, owner_id=84, visibility="private")


def test_visibility_constants():
    assert tenancy.Visibility.SHARED == "shared"
    assert tenancy.Visibility.PRIVATE == "private"
    assert set(tenancy.Visibility.ALL) == {"shared", "private"}
