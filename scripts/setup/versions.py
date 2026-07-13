"""Version resolution — ported from scripts/lib/versions.sh (#7, Stage 2).

This module ports the PURE, deterministic core of the smart-version engine — the
algorithmic helpers that map 1:1 to bash functions and are unit-verifiable
without a network:

    registry_type · image_repo · strip_v · ver_ge · tag_satisfies_constraint · best_tag

The network + orchestration layer (the `*_list_tags` registry fetches, the
`resolve_image_tag` / `pull_*` / `version_drift_report` orchestration) is DEFERRED:
it needs a curl→urllib decision, the spinner, the RESOLVED_IMAGE_TAGS cache, and
THIRD_PARTY_IMAGE_SPECS, and its only entry points are the still-bash
install/update/doctor verbs — so it lands when those verbs are ported. (The tag
cache in cache.py is consumed by that deferred layer.)
"""

import re

# Tags carrying these markers are pre-release / rolling and never eligible.
_PRERELEASE_RE = re.compile(r"(rc|alpha|beta|dev|nightly|edge|test)")
# A clean numeric release tag: 1 / 1.2 / 1.2.3 optionally with a single -suffix.
_NUMERIC_TAG_RE = re.compile(r"^[0-9]+(\.[0-9]+)*(-[a-zA-Z0-9]+)?$")


def registry_type(image_ref: str) -> str:
    """bash _registry_type: ghcr.io/* → ghcr, quay.io/* → quay, else dockerhub."""
    if image_ref.startswith("ghcr.io/"):
        return "ghcr"
    if image_ref.startswith("quay.io/"):
        return "quay"
    return "dockerhub"


def image_repo(image_ref: str) -> str:
    """bash _image_repo: strip the :tag, then the registry prefix; a bare official
    image (no '/') becomes library/<name>."""
    no_tag = image_ref.split(":", 1)[0]  # ${image_ref%%:*}
    if no_tag.startswith("ghcr.io/"):
        return no_tag[len("ghcr.io/") :]
    if no_tag.startswith("quay.io/"):
        return no_tag[len("quay.io/") :]
    if "/" in no_tag:
        return no_tag  # already org/repo
    return f"library/{no_tag}"  # official image, e.g. postgres → library/postgres


def strip_v(ver: str) -> str:
    """bash _strip_v: drop a single leading 'v' (v1.2.3 == 1.2.3)."""
    return ver[1:] if ver.startswith("v") else ver


def _version_key(ver: str) -> list[int]:
    """Numeric key for version ordering: the leading integer of each dot-separated
    component (`1.2.3-alpine` → [1, 2, 3]). Mirrors `sort -V` for the clean numeric
    release tags best_tag actually compares (pre-release/rolling tags are already
    filtered out by tag_satisfies_constraint)."""
    key = []
    for comp in ver.split("."):
        m = re.match(r"\d+", comp)
        key.append(int(m.group(0)) if m else 0)
    return key


def ver_ge(a: str, b: str) -> bool:
    """bash _ver_ge: True if a >= b under version ordering (leading 'v' ignored)."""
    return _version_key(strip_v(a)) >= _version_key(strip_v(b))


def tag_satisfies_constraint(tag: str, stable_prefix: str, constraint: str) -> bool:
    """bash _tag_satisfies_constraint: reject non-numeric / pre-release tags, then
    match on major / major.minor / anything, per the constraint."""
    t = strip_v(tag)
    p = strip_v(stable_prefix)

    if not _NUMERIC_TAG_RE.match(t) or _PRERELEASE_RE.search(t):
        return False

    if constraint == "major":
        return t.split(".")[0] == p.split(".")[0]
    if constraint == "minor":
        return ".".join(t.split(".")[:2]) == ".".join(p.split(".")[:2])
    if constraint == "none":
        return True
    return False


def best_tag(tags: str, stable_prefix: str, constraint: str) -> str:
    """bash _best_tag: the highest tag (newline-separated list) satisfying the
    constraint, or "" if none. First satisfying tag seeds; each later one replaces
    it only when >= (mirrors the bash loop exactly, including its tie behaviour)."""
    best = ""
    for tag in tags.split("\n"):
        if not tag:
            continue
        if tag_satisfies_constraint(tag, stable_prefix, constraint):
            if best == "" or ver_ge(tag, best):
                best = tag
    return best
