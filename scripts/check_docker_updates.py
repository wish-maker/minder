#!/usr/bin/env python3
"""Check 3rd-party Docker image tags in docker/docker-compose.yml for available
updates. Companion to check_pip_updates.py (which covers the Python side) for
the Docker side.

Extracted from docker-image-update.yml's embedded ~450-line Python heredoc so
this logic is lintable (black/isort/flake8/mypy via quality.yml) and testable
like every other script in this repo — a change to it previously escaped every
quality gate entirely, since quality.yml never lints .github/workflows/*.yml
contents.

Reads docker/docker-compose.yml, queries each 3rd-party image's registry
(Docker Hub / GCR / GHCR) for real, existing tags, classifies any newer tag as
patch/minor/major (or a version-scheme change, e.g. semver -> calver), and
writes six JSON files (updates/safe-updates/risky-updates/up-to-date/
manual-check/excluded-local) plus GITHUB_OUTPUT boolean flags — the exact
shape the workflow's downstream `actions/github-script` issue-body step
already expects, so that step needed no changes.

Usage:
    python scripts/check_docker_updates.py [--compose path] [--out-dir dir]
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import requests
import yaml

# ============================================================================
# TAG PARSING
# ============================================================================


def parse_tag(tag: str) -> Tuple[str, str]:
    """Parse tag into (version, suffix)."""
    tag = tag.lstrip("v")

    # Handle apicurio X.Y.Z.Final format
    if tag.endswith(".Final"):
        return tag[:-6], ".Final"

    match = re.match(r"^([0-9]+(?:\.[0-9]+)*)-(.+)$", tag)
    if match:
        return match.group(1), "-" + match.group(2)
    return tag, ""


def should_skip_tag(tag: str) -> bool:
    """Skip non-version tags."""
    skip_patterns = [
        r"^latest$",
        r"^dev$",
        r"^master$",
        r"^sha256-",
        r".*-unprivileged$",
        r".*-gpu-.*$",
    ]
    return any(re.match(pattern, tag) for pattern in skip_patterns)


def parse_version_safe(version_str: str) -> Optional[Tuple[int, int, int]]:
    """Parse version string into comparable tuple (handles X.Y.Z, X.Y, X)."""
    parts = version_str.split(".")
    try:
        int_parts = [int(p) for p in parts]
        while len(int_parts) < 3:
            int_parts.append(0)
        return (int_parts[0], int_parts[1], int_parts[2])
    except (ValueError, AttributeError):
        return None


def detect_version_scheme(version_str: str) -> str:
    """Detect version scheme: 'calver' or 'semver'."""
    parts = version_str.split(".")
    if len(parts) >= 2:
        try:
            first = int(parts[0])
            if first >= 2000 or (len(parts[0]) == 4 and parts[0].isdigit()):
                return "calver"
        except ValueError:
            pass
    return "semver"


def classify_update(current_tag: str, latest_tag: str) -> str:
    """Classify update as 'patch', 'minor', 'major', 'scheme-change', or 'unknown'.
    Assumes both tags are in the same track (same suffix)."""
    current_ver, _ = parse_tag(current_tag)
    latest_ver, _ = parse_tag(latest_tag)

    current_scheme = detect_version_scheme(current_ver)
    latest_scheme = detect_version_scheme(latest_ver)
    if current_scheme != latest_scheme:
        return "scheme-change"

    current_parsed = parse_version_safe(current_ver)
    latest_parsed = parse_version_safe(latest_ver)
    if not current_parsed or not latest_parsed:
        return "unknown"

    current_major, current_minor, current_patch = current_parsed
    latest_major, latest_minor, latest_patch = latest_parsed

    if latest_major > current_major:
        return "major"
    elif latest_minor > current_minor:
        return "minor"
    elif latest_patch > current_patch:
        return "patch"
    return "unknown"


# ============================================================================
# DOCKER HUB API
# ============================================================================


def fetch_all_tags(repo: str) -> List[str]:
    """Fetch all tags from Docker Hub (paginated)."""
    tags: List[str] = []
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=100"
    page = 0
    while url and page < 5:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            for tag_data in data["results"]:
                tag_name = tag_data["name"]
                if not should_skip_tag(tag_name):
                    tags.append(tag_name)
            url = data.get("next")
            page += 1
        except Exception as e:
            print(f"    [!] API error: {e}")
            break
    return tags


def get_latest_in_track(
    current_tag: str, all_tags: List[str]
) -> Tuple[Optional[str], str]:
    """Find the highest version in the same track as current_tag."""
    _, current_suffix = parse_tag(current_tag)
    same_track = [tag for tag in all_tags if parse_tag(tag)[1] == current_suffix]
    versions = []
    for tag in same_track:
        ver, _ = parse_tag(tag)
        # Skip CI build-id tags: a bare integer of 5+ digits is not a real
        # version (e.g. jaeger's '89133199' parses as 89133199.0.0 and would
        # otherwise sort above 1.76.0). Calver years are 4 digits, so kept.
        if re.match(r"^\d{5,}$", ver):
            continue
        parsed = parse_version_safe(ver)
        if parsed is not None:
            versions.append((parsed, tag))
    if not versions:
        return None, "no valid versions in track"
    versions.sort(key=lambda x: x[0], reverse=True)
    _, latest_tag = versions[0]
    return latest_tag, "found"


def get_latest_minio_release(
    current_tag: str, all_tags: List[str]
) -> Tuple[Optional[str], str]:
    """Find latest RELEASE.* base date for minio (variants like -cpuv1 are NOT
    updates)."""
    release_tags = [tag for tag in all_tags if tag.startswith("RELEASE.")]
    if not release_tags:
        return None, "no RELEASE tags found"

    # Extract base dates (RELEASE.YYYY-MM-DDTHH-MM-SSZ) ignoring variant suffixes
    base_dates: Dict[str, str] = {}
    for tag in release_tags:
        match = re.match(r"(RELEASE\.\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)", tag)
        if match:
            base = match.group(1)
            if base not in base_dates:
                base_dates[base] = tag
            # Prefer non-variant tags (base tag without -cpuv1 etc)
            if tag == base:
                base_dates[base] = tag

    if not base_dates:
        return None, "no valid RELEASE base dates found"

    latest_base = max(base_dates.keys())
    latest_tag = base_dates[latest_base]

    current_match = re.match(
        r"(RELEASE\.\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)", current_tag
    )
    if not current_match:
        return None, "invalid current tag format"

    current_base = current_match.group(1)
    if current_base == latest_base:
        return current_tag, "up to date"
    return latest_tag, f"update available (base: {latest_base})"


# ============================================================================
# GCR / GHCR RESOLUTION
# ============================================================================


def fetch_gcr_tags(name: str) -> List[str]:
    """Fetch tags from GCR (public images allow anonymous v2 API access)."""
    try:
        r = requests.get(f"https://gcr.io/v2/{name}/tags/list", timeout=10)
        r.raise_for_status()
        return [t for t in r.json().get("tags", []) if not should_skip_tag(t)]
    except Exception as e:
        print(f"    [!] GCR API error: {e}")
        return []


def latest_ghcr_release(repo: str) -> Optional[str]:
    """Latest stable release tag for a GHCR image via its backing GitHub repo.
    GHCR's own tag listing is unreliable for busy images (thousands of git-*
    tags bury the releases and the API is not recency-ordered), so the GitHub
    Releases API is the source of truth. Assumes ghcr.io/<owner>/<name> maps to
    the github.com/<owner>/<name> repo."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("tag_name")
    except Exception as e:
        print(f"    [!] GitHub releases API error for {repo}: {e}")
        return None


def latest_semver_tag(tags: List[str]) -> Optional[str]:
    """Highest strict X.Y.Z tag. Rejects CI-junk single-int tags (e.g. a bare
    '89133199' that would otherwise parse as version 89133199.0.0 and beat
    every real release). Used to resolve a concrete version for :latest-pinned
    images."""
    candidates = []
    for tag in tags:
        if re.match(r"^v?\d+\.\d+\.\d+$", tag):
            parsed = parse_version_safe(tag.lstrip("v"))
            if parsed is not None:
                candidates.append((parsed, tag))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ============================================================================
# REGISTRY DETECTION
# ============================================================================


def get_registry(image_ref: str) -> str:
    # CodeQL flags anchored startswith() host checks as py/incomplete-url-
    # substring-sanitization (the query can't distinguish this from an
    # unanchored "in" check that a URL like evil.com/ghcr.io/x would bypass).
    # image_ref here is never attacker input -- it's an `image:` value read
    # straight from this repo's own hand-maintained docker/docker-compose.yml,
    # the same trust boundary as the identical pattern in scripts/setup/
    # versions.py's registry_type()/strip_known_registry().
    if image_ref.startswith("ghcr.io/"):
        return "GHCR"
    elif image_ref.startswith("gcr.io/"):
        return "GCR"
    elif image_ref.startswith("minder/"):
        return "LOCAL"
    return "DOCKER_HUB"


def normalize_repo(image_name: str) -> str:
    if "/" not in image_name:
        return f"library/{image_name}"
    return image_name


# ============================================================================
# MAIN CHECK LOGIC
# ============================================================================


def check_updates_from_compose(
    compose_path: str,
) -> Tuple[Dict, Dict, Dict, Dict, Dict, Dict]:
    """Read docker-compose.yml and check every 3rd-party image for updates."""
    with open(compose_path, "r", encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    updates: Dict[str, dict] = {}
    safe_updates: Dict[str, dict] = {}
    risky_updates: Dict[str, dict] = {}
    up_to_date: Dict[str, dict] = {}
    manual_check: Dict[str, dict] = {}
    excluded_local: Dict[str, dict] = {}

    for service_name, service_config in compose["services"].items():
        if "image" not in service_config:
            continue

        image = service_config["image"]

        # Skip local builds (minder/* images)
        if "build" in service_config:
            excluded_local[service_name] = {
                "image": image,
                "note": "Local build — excluded from auto-update checks",
            }
            continue

        registry = get_registry(image)

        # Split image into name + current tag (':' absent => implicit :latest)
        if ":" not in image:
            image_name, current_tag = image, "latest"
        else:
            image_name, current_tag = image.rsplit(":", 1)

        # Special handling for minio RELEASE.* tags
        if image_name == "minio/minio" and current_tag.startswith("RELEASE."):
            try:
                repo = normalize_repo(image_name)
                all_tags = fetch_all_tags(repo)
                latest_release, _reason = get_latest_minio_release(
                    current_tag, all_tags
                )

                if latest_release and latest_release != current_tag:
                    updates[service_name] = {
                        "image": image_name,
                        "current": current_tag,
                        "latest": latest_release,
                        "registry": registry,
                        "classification": "patch",  # Date bumps are safe-ish
                    }
                    safe_updates[service_name] = updates[service_name]
                elif latest_release == current_tag:
                    up_to_date[service_name] = {
                        "image": image_name,
                        "current": current_tag,
                        "registry": registry,
                    }
            except Exception as e:
                print(f"    [X] {service_name}: Error - {e}")
            continue

        # ----------------------------------------------------------------
        # Resolve the newest version, per registry:
        #   DOCKER_HUB / GCR -> list tags, take highest in-track
        #   GHCR             -> tag listing unreliable, use GitHub releases
        # ----------------------------------------------------------------
        is_latest = current_tag == "latest"
        try:
            if registry == "GHCR":
                latest_tag = latest_ghcr_release(image_name[len("ghcr.io/") :])
            elif registry == "GCR":
                gcr_tags = fetch_gcr_tags(image_name[len("gcr.io/") :])
                latest_tag = (
                    latest_semver_tag(gcr_tags)
                    if is_latest
                    else get_latest_in_track(current_tag, gcr_tags)[0]
                )
            elif registry == "DOCKER_HUB":
                dh_tags = fetch_all_tags(normalize_repo(image_name))
                latest_tag = (
                    latest_semver_tag(dh_tags)
                    if is_latest
                    else get_latest_in_track(current_tag, dh_tags)[0]
                )
            else:
                latest_tag = None
        except Exception as e:
            print(f"    [X] {service_name}: Error - {e}")
            latest_tag = None

        # :latest floats — can't classify a diff, but surface the newest
        # concrete release and recommend pinning to it.
        if is_latest:
            if latest_tag:
                note = (
                    f"Floating on :latest — newest tagged release is "
                    f"`{latest_tag}`. Pin to `{image_name}:{latest_tag}` for "
                    f"reproducible deploys and automatic update tracking."
                )
            else:
                note = (
                    "Uses :latest and the newest release could not be "
                    "resolved automatically — verify manually."
                )
            manual_check[service_name] = {
                "image": image_name,
                "current": current_tag,
                "latest": latest_tag,
                "registry": registry,
                "note": note,
            }
            continue

        # Pinned version — classify the update
        if latest_tag is None:
            manual_check[service_name] = {
                "image": image_name,
                "current": current_tag,
                "latest": None,
                "registry": registry,
                "note": "Could not determine latest version — verify manually.",
            }
            continue

        if latest_tag != current_tag:
            classification = classify_update(current_tag, latest_tag)
            update_info = {
                "image": image_name,
                "current": current_tag,
                "latest": latest_tag,
                "registry": registry,
                "classification": classification,
            }
            updates[service_name] = update_info

            # Split into safe (patch/minor) and risky (major/scheme-change)
            if classification in ("patch", "minor"):
                safe_updates[service_name] = update_info
            elif classification in ("major", "scheme-change"):
                risky_updates[service_name] = update_info
        else:
            up_to_date[service_name] = {
                "image": image_name,
                "current": current_tag,
                "registry": registry,
            }

    return (
        updates,
        safe_updates,
        risky_updates,
        up_to_date,
        manual_check,
        excluded_local,
    )


def _write_flag(output_file: str, flag: str, value: bool) -> None:
    with open(output_file, "a", encoding="utf-8") as f:
        f.write(f"{flag}={str(value).lower()}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--compose",
        default="docker/docker-compose.yml",
        help="path to docker-compose.yml",
    )
    ap.add_argument(
        "--out-dir", default=".", help="directory to write the 6 JSON reports to"
    )
    args = ap.parse_args()

    (
        updates,
        safe_updates,
        risky_updates,
        up_to_date,
        manual_check,
        excluded_local,
    ) = check_updates_from_compose(args.compose)

    reports = {
        "updates.json": updates,
        "safe-updates.json": safe_updates,
        "risky-updates.json": risky_updates,
        "up-to-date.json": up_to_date,
        "manual-check.json": manual_check,
        "excluded-local.json": excluded_local,
    }
    for filename, data in reports.items():
        with open(os.path.join(args.out_dir, filename), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    output_file = os.environ.get("GITHUB_OUTPUT", "/dev/stdout")
    _write_flag(output_file, "updates-available", bool(updates))
    _write_flag(output_file, "safe-updates-available", bool(safe_updates))
    _write_flag(output_file, "risky-updates-available", bool(risky_updates))
    _write_flag(output_file, "up-to-date", bool(up_to_date))
    _write_flag(output_file, "manual-check-needed", bool(manual_check))
    _write_flag(output_file, "excluded-local", bool(excluded_local))

    print(
        f"updates={len(updates)} safe={len(safe_updates)} risky={len(risky_updates)} "
        f"up_to_date={len(up_to_date)} manual_check={len(manual_check)} "
        f"excluded_local={len(excluded_local)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
