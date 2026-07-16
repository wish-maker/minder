"""Version resolution — ported from scripts/lib/versions.sh (#7, Stage 2).

The pure algorithmic core (registry_type · image_repo · strip_v · ver_ge ·
tag_satisfies_constraint · best_tag), the spec derivation (compose_image_refs ·
third_party_image_specs · third_party_images), and the network + orchestration
layer (`*_list_tags` registry fetches, resolve_image_tag / pull_* /
version_drift_report). curl is replaced by urllib (cross-platform); the tag cache
is cache.py.

The deterministic path — SKIP_VERSION_CHECK / patch constraint short-circuits
resolve_image_tag to the pinned ref (no network) — is what install/update/doctor
run under the gate, and what pull_all_images / version_drift_report are verified
on. The live smart-resolution branch (list_tags + manifest probes) is ported
faithfully but exercised only against real registries.
"""

import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

from . import cache, config, docker, log

# Tags carrying these markers are pre-release / rolling and never eligible.
_PRERELEASE_RE = re.compile(r"(rc|alpha|beta|dev|nightly|edge|test)")
# A clean numeric release tag: 1 / 1.2 / 1.2.3 optionally with a single -suffix.
_NUMERIC_TAG_RE = re.compile(r"^[0-9]+(\.[0-9]+)*(-[a-zA-Z0-9]+)?$")


def compose_image_refs() -> list:
    """bash _compose_image_refs: the pinned `image:tag` refs from the compose file
    (grep '^<ws>image:<ws>…', strip the prefix + trailing comment/space)."""
    try:
        text = config.COMPOSE_FILE.read_text(encoding="utf-8")
    except OSError:
        return []
    refs = []
    for line in text.splitlines():
        m = re.match(r"^[ \t]+image:[ \t]+(.*)$", line)
        if m:
            refs.append(re.sub(r"[ \t]*(#.*)?$", "", m.group(1)))
    return refs


def third_party_image_specs() -> list:
    """bash _derive_third_party_specs / THIRD_PARTY_IMAGE_SPECS: join each 3rd-party
    compose image with its metadata into "image:tag|stable_prefix|constraint", in
    compose-file order. Warns (stderr) on metadata whose image compose no longer has."""
    specs = []
    seen = set()
    for ref in compose_image_refs():
        if not ref:
            continue
        name = ref.rsplit(":", 1)[0]  # ${ref%:*}
        meta = config.THIRD_PARTY_IMAGE_META.get(name)
        if meta:
            specs.append(f"{ref}|{meta}")
            seen.add(name)
    for key in config.THIRD_PARTY_IMAGE_META:
        if key not in seen:
            print(
                f"WARN: THIRD_PARTY_IMAGE_META has '{key}' but no matching image in compose",
                file=sys.stderr,
            )
    return specs


def third_party_images() -> list:
    """bash THIRD_PARTY_IMAGES: the pinned refs (spec before the first '|')."""
    return [spec.split("|", 1)[0] for spec in third_party_image_specs()]


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


# ── Registry tag queries (curl → urllib) + on-disk cache ──────────────────────
# The log_debug lines from the bash originals are ported as log.debug() (VERBOSE-
# gated, LOG_FILE-mirrored — no-ops otherwise). These hit the network, so they are
# exercised only against real registries (not gate-verified).


def _http_get(url: str, headers: "dict | None" = None) -> "str | None":
    """curl -sf --max-time TIMEOUT_REGISTRY: body on 2xx, else None."""
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(
            req, timeout=config.TIMEOUT_REGISTRY
        ) as resp:  # noqa: S310
            if not (200 <= resp.status < 300):
                return None
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_name_values(text: str) -> list:
    # grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed strip → the name values
    return re.findall(r'"name"[ \t]*:[ \t]*"([^"]+)"', text)


def dockerhub_list_tags(repo: str) -> str:
    cf = cache.cache_file("dockerhub", repo)
    cached = cache.load_cached_tags(cf)
    if cached:
        log.debug(f"dockerhub_list_tags: using cached tags for {repo}")
        return cached
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=100&ordering=last_updated"
    resp = _http_get(url)
    if resp is None:
        log.debug(f"dockerhub_list_tags: HTTP request failed for {repo}")
        return ""
    tags = "\n".join(_extract_name_values(resp))
    if tags:
        cache.cache_tags(cf, tags, _utc_now())
    return tags


def ghcr_list_tags(repo: str) -> str:
    cf = cache.cache_file("ghcr", repo)
    cached = cache.load_cached_tags(cf)
    if cached:
        log.debug(f"ghcr_list_tags: using cached tags for {repo}")
        return cached
    resp = _http_get(
        f"https://ghcr.io/v2/{repo}/tags/list", headers={"Accept": "application/json"}
    )
    if resp is None:
        log.debug(f"ghcr_list_tags: HTTP request failed for {repo}")
        return ""
    # bash: grep -oE '"[^"]+"' | sed 's/"//g' | grep -v '^tags$|^name$|^{$|^}$'
    # The grep -v pattern is BRE (| literal), so it matches nothing and filters
    # nothing — reproduced faithfully (a latent quirk: "tags"/"name" leak in).
    tags = "\n".join(re.findall(r'"([^"]+)"', resp))
    if tags:
        cache.cache_tags(cf, tags, _utc_now())
    return tags


def quay_list_tags(repo: str) -> str:
    cf = cache.cache_file("quay", repo)
    cached = cache.load_cached_tags(cf)
    if cached:
        log.debug(f"quay_list_tags: using cached tags for {repo}")
        return cached
    resp = _http_get(
        f"https://quay.io/api/v1/repository/{repo}/tag/?limit=100&onlyActiveTags=true"
    )
    if resp is None:
        log.debug(f"quay_list_tags: HTTP request failed for {repo}")
        return ""
    tags = "\n".join(_extract_name_values(resp))
    if tags:
        cache.cache_tags(cf, tags, _utc_now())
    return tags


# ── Main resolver ─────────────────────────────────────────────────────────────
# RESOLVED_IMAGE_TAGS: per-run memo of pinned_ref → resolved_ref (bash's assoc array).
RESOLVED_IMAGE_TAGS: dict = {}


def _list_tags(registry: str, repo: str) -> str:
    if registry == "ghcr":
        return ghcr_list_tags(repo)
    if registry == "quay":
        return quay_list_tags(repo)
    return dockerhub_list_tags(repo)


def _tag_exists(registry: str, repo: str, tag: str, test_ref: str) -> bool:
    # dockerhub: Docker Hub API (avoids pull rate limits); else `docker manifest inspect`.
    if registry == "dockerhub":
        return (
            _http_get(
                f"https://registry.hub.docker.com/v2/repositories/{repo}/tags/{tag}"
            )
            is not None
        )
    try:
        return (
            subprocess.run(
                ["docker", "manifest", "inspect", test_ref],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def _ref_for(registry: str, repo: str, image_base: str, tag: str) -> str:
    if registry == "ghcr":
        return f"ghcr.io/{repo}:{tag}"
    if registry == "quay":
        return f"quay.io/{repo}:{tag}"
    return f"{image_base}:{tag}"


def resolve_image_tag(spec: str) -> str:
    """bash resolve_image_tag: resolve a spec's best working tag, memoized in
    RESOLVED_IMAGE_TAGS, falling back to the pin. SKIP_VERSION_CHECK / a `patch`
    constraint short-circuits to the pin (no network) — the deterministic path."""
    pinned_ref, stable_prefix, constraint = (spec.split("|", 2) + ["", ""])[:3]

    if pinned_ref in RESOLVED_IMAGE_TAGS:
        return RESOLVED_IMAGE_TAGS[pinned_ref]

    if constraint == "patch" or config.SKIP_VERSION_CHECK:
        RESOLVED_IMAGE_TAGS[pinned_ref] = pinned_ref
        return pinned_ref

    image_base = pinned_ref.split(":", 1)[0]  # ${pinned_ref%%:*}
    pinned_tag = pinned_ref.rsplit(":", 1)[-1]  # ${pinned_ref##*:}
    registry = registry_type(pinned_ref)
    repo = image_repo(pinned_ref)

    log.debug(
        f"Querying {registry} for {repo} (prefix={stable_prefix}, constraint={constraint})"
    )

    all_tags = _list_tags(registry, repo)
    if not all_tags:
        RESOLVED_IMAGE_TAGS[pinned_ref] = pinned_ref
        return pinned_ref

    best = best_tag(all_tags, stable_prefix, constraint)
    if not best:
        RESOLVED_IMAGE_TAGS[pinned_ref] = pinned_ref
        return pinned_ref

    candidate_ref = _ref_for(registry, repo, image_base, best)
    if candidate_ref == pinned_ref:
        RESOLVED_IMAGE_TAGS[pinned_ref] = pinned_ref
        return pinned_ref

    # Try satisfying tags newest→oldest until one's manifest resolves.
    log.spinner_start(f"Resolving {image_base}: finding latest working version...")
    working_tag = ""
    tried = set()
    for tag in all_tags.split("\n"):
        if not tag or tag in tried:
            continue
        if not tag_satisfies_constraint(tag, stable_prefix, constraint):
            continue
        tried.add(tag)
        test_ref = _ref_for(registry, repo, image_base, tag)
        if _tag_exists(registry, repo, tag, test_ref):
            working_tag = tag
            break
    log.spinner_stop()

    if working_tag:
        final_ref = _ref_for(registry, repo, image_base, working_tag)
        if working_tag == pinned_tag:
            log.detail(
                f"{image_base}: using pinned {pinned_tag} (no newer working version found)"
            )
        else:
            tail = (
                f"{log._CYAN}{working_tag}{log._NC}"
                if log._colors_on()
                else working_tag
            )
            log.success(f"{image_base}: {pinned_tag} → {tail}  (latest working)")
        RESOLVED_IMAGE_TAGS[pinned_ref] = final_ref
        return final_ref

    log.warn(
        f"{image_base}: no working version found — falling back to pinned {pinned_tag}"
    )
    RESOLVED_IMAGE_TAGS[pinned_ref] = pinned_ref
    return pinned_ref


def pull_image_with_fallback(spec: str) -> int:
    """bash pull_image_with_fallback: resolve, pull; on failure pull the pin.
    Non-fatal (always returns 0)."""
    pinned_ref = spec.split("|", 1)[0]
    target_ref = resolve_image_tag(spec)

    log.spinner_start(f"Pulling {target_ref}…")
    if docker.run("docker", "pull", target_ref, quiet=True) == 0:
        log.spinner_stop()
        log.success(target_ref)
        return 0
    log.spinner_stop()

    if target_ref != pinned_ref:
        log.warn(f"{target_ref} pull failed — falling back to pinned {pinned_ref}")
        log.spinner_start(f"Pulling {pinned_ref} (fallback)…")
        if docker.run("docker", "pull", pinned_ref, quiet=True) == 0:
            log.spinner_stop()
            tail = (
                f"  {log._DIM}(pinned fallback){log._NC}"
                if log._colors_on()
                else "  (pinned fallback)"
            )
            log.success(f"{pinned_ref}{tail}")
            RESOLVED_IMAGE_TAGS[pinned_ref] = pinned_ref
            return 0
        log.spinner_stop()
        log.warn(f"{pinned_ref} also failed — image may already be cached locally")
    else:
        log.warn(f"{pinned_ref} pull failed — image may already be cached locally")
    return 0


def pull_all_images() -> None:
    """bash pull_all_images: pull every third-party image with version resolution."""
    log.section("📦  Pulling Images  (smart version resolution)")
    log.info(
        "Constraint legend: major=same major OK · minor=same major.minor OK · none=any"
    )
    log._emit("")
    for spec in third_party_image_specs():
        pull_image_with_fallback(spec)
    log.success("Image pull phase complete")


def version_drift_report(json_mode: bool = False) -> int:
    """bash version_drift_report (doctor + update --check): resolve each spec
    without pulling, report which images have a newer compatible tag. Returns the
    number of drifted images (doctor counts it toward `issues`; bash re-runs +
    greps for that — same observable output, drift shown once)."""
    drift_items = []  # (image_base, pinned_tag, resolved_tag, constraint)
    ok_items = []  # (image_base, pinned_tag, constraint)

    for spec in third_party_image_specs():
        pinned_ref, stable_prefix, constraint = (spec.split("|", 2) + ["", ""])[:3]
        pinned_tag = pinned_ref.rsplit(":", 1)[-1]
        image_base = pinned_ref.split(":", 1)[0]
        resolved = resolve_image_tag(spec)
        resolved_tag = resolved.rsplit(":", 1)[-1]
        if resolved_tag != pinned_tag and resolved_tag != "":
            drift_items.append((image_base, pinned_tag, resolved_tag, constraint))
        else:
            ok_items.append((image_base, pinned_tag, constraint))

    if json_mode:
        log._emit("{")
        log._emit(f'  "timestamp": "{_utc_now()}",')
        log._emit(f'  "updates_available": {len(drift_items)},')
        log._emit('  "drift": [')
        for i, (img, cur, avail, con) in enumerate(drift_items):
            if i > 0:
                log._emit(",")
            log._write_raw(
                f'    {{"image":"{img}","current":"{cur}","available":"{avail}","constraint":"{con}"}}'
            )
        log._emit("")
        log._emit("  ]")
        log._emit("}")
        return len(drift_items)

    log._emit(
        "\n"
        + (
            f"{log._BOLD}Version Drift Report{log._NC}"
            if log._colors_on()
            else "Version Drift Report"
        )
    )
    if not drift_items:
        log.success("All images are up to date ✓")
    else:
        head = (
            f"  {log._YELLOW}{len(drift_items)} update(s) available:{log._NC}\n"
            if log._colors_on()
            else f"  {len(drift_items)} update(s) available:\n"
        )
        log._emit(head)
        log._emit(f"  {'IMAGE':<45}  {'CURRENT':<20}  {'AVAILABLE':<20}  CONSTRAINT")
        log._emit(f"  {'─────':<45}  {'───────':<20}  {'─────────':<20}  ──────────")
        for img, cur, avail, con in drift_items:
            if log._colors_on():
                log._emit(
                    f"  {log._CYAN}{img:<45}{log._NC}  {log._DIM}{cur:<20}{log._NC}  {log._GREEN}{avail:<20}{log._NC}  {con}"  # noqa: E501
                )
            else:
                log._emit(f"  {img:<45}  {cur:<20}  {avail:<20}  {con}")
        log._emit("")
        log.detail(f"Apply updates:   ./{config.SCRIPT_NAME} update")
        log.detail(
            f"Skip and use pins: SKIP_VERSION_CHECK=1 ./{config.SCRIPT_NAME} update"
        )

    if ok_items and config.VERBOSE:
        log._emit(
            "\n  "
            + (f"{log._DIM}Up to date:{log._NC}" if log._colors_on() else "Up to date:")
        )
        for img, cur, con in ok_items:
            log.detail(f"  ✓  {img}:{cur}  ({con})")

    return len(drift_items)
