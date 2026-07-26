"""Canonical license-tier vocabulary shared across services.

Historically the marketplace used ``{community, professional, enterprise}`` while the
plugin-state-manager used ``{free, community, pro, enterprise}``. A ``professional``
license issued by the marketplace did not match the state-manager's vocabulary, so its
tier gate either crashed (``LicenseTier("professional")`` → ``ValueError``) or silently
failed **open** (``tier_hierarchy.get("professional", 0) == 0`` — i.e. "no requirement",
so a paid tool became free to everyone).

This module makes one vocabulary authoritative and tolerates the legacy
``professional`` spelling as an alias, so any stray data or caller normalises cleanly
to ``pro`` instead of breaking or fail-opening. (#142)
"""

from enum import Enum


class LicenseTier(str, Enum):
    """Canonical license tiers, ordered free < community < pro < enterprise."""

    FREE = "free"
    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Deprecated spellings → canonical member. Kept so a marketplace-issued "professional"
# normalises to "pro" rather than failing or fail-opening.
_TIER_ALIASES = {"professional": LicenseTier.PRO}

# Privilege rank for "user tier >= required tier" comparisons. Higher = more privileged.
TIER_RANK = {
    LicenseTier.FREE: 0,
    LicenseTier.COMMUNITY: 1,
    LicenseTier.PRO: 2,
    LicenseTier.ENTERPRISE: 3,
}


def normalize_tier(value: "str | LicenseTier") -> LicenseTier:
    """Coerce a raw tier value to a canonical :class:`LicenseTier`.

    Accepts a ``LicenseTier``, any canonical string, or a known alias
    (``professional``). Case-insensitive. Raises ``ValueError`` (→ 422 at an API edge)
    for anything else, listing the valid values.
    """
    if isinstance(value, LicenseTier):
        return value
    key = str(value).strip().lower()
    if key in _TIER_ALIASES:
        return _TIER_ALIASES[key]
    try:
        return LicenseTier(key)
    except ValueError:
        valid = [t.value for t in LicenseTier]
        raise ValueError(
            f"invalid license tier '{value}'; valid values: {valid} "
            "(deprecated alias 'professional' → 'pro')"
        )


def tier_rank(value: "str | LicenseTier") -> int:
    """Privilege rank of a tier for ``>=`` comparisons; normalises aliases first."""
    return TIER_RANK[normalize_tier(value)]
