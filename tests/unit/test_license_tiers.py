"""Unit tests for the shared canonical license-tier vocabulary (#142).

These guard the invariants the plugin-state-manager tier gate depends on: the legacy
"professional" spelling must rank identically to "pro", an unknown tier must raise
(so the gate's except-branch fails closed rather than fail-opening a paid tool), and
the ordering community < pro < enterprise must hold.
"""

import pytest

from shared.models.tiers import TIER_RANK, LicenseTier, normalize_tier, tier_rank


def test_canonical_values():
    assert {t.value for t in LicenseTier} == {"free", "community", "pro", "enterprise"}


def test_normalize_professional_alias_maps_to_pro():
    # The whole point of #142: a marketplace-issued "professional" must not diverge.
    assert normalize_tier("professional") is LicenseTier.PRO


def test_normalize_is_case_insensitive():
    assert normalize_tier("PRO") is LicenseTier.PRO
    assert normalize_tier("  Enterprise ") is LicenseTier.ENTERPRISE


def test_normalize_accepts_enum_passthrough():
    assert normalize_tier(LicenseTier.COMMUNITY) is LicenseTier.COMMUNITY


@pytest.mark.parametrize("bad", ["platinum", "gold", "", "professionals"])
def test_normalize_unknown_raises_with_valid_values(bad):
    with pytest.raises(ValueError) as exc:
        normalize_tier(bad)
    assert "valid values" in str(exc.value)


def test_alias_and_canonical_rank_equal():
    assert tier_rank("professional") == tier_rank("pro") == 2


def test_rank_ordering():
    assert (
        tier_rank("free")
        < tier_rank("community")
        < tier_rank("pro")
        < tier_rank("enterprise")
    )


def test_community_user_ranks_below_pro_requirement():
    # A community user (rank 1) must NOT satisfy a pro requirement (rank 2) — this is
    # the comparison the tool-access gate makes.
    assert tier_rank("community") < tier_rank("professional")


def test_tier_rank_covers_every_member():
    assert set(TIER_RANK) == set(LicenseTier)
