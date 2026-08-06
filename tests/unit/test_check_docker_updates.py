"""Unit tests for scripts/check_docker_updates.py's pure parsing/classification
logic (tag parsing, version-scheme detection, update classification, in-track
resolution). No network: only functions that don't call a registry.

Extracted from docker-image-update.yml's previously-embedded ~450-line Python
heredoc — this is its first test coverage of any kind.

Also covers #351: check_updates_from_compose()'s minio RELEASE.* special case
used to leave a service out of every report dict (updates/safe_updates/
risky_updates/up_to_date/manual_check/excluded_local) when the lookup raised
or resolved to no usable tag — a real check failure silently read as "nothing
to report" instead of "this needs a manual look."
"""

import scripts.check_docker_updates as check_docker_updates
from scripts.check_docker_updates import (
    check_updates_from_compose,
    classify_update,
    detect_version_scheme,
    get_latest_in_track,
    get_latest_minio_release,
    get_registry,
    normalize_repo,
    parse_tag,
    parse_version_safe,
    should_skip_tag,
)

_MINIO_COMPOSE = """
services:
  minio:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
"""


def test_parse_tag_plain_semver():
    assert parse_tag("v3.7.9") == ("3.7.9", "")
    assert parse_tag("13.1.1") == ("13.1.1", "")


def test_parse_tag_suffix():
    assert parse_tag("8.8.1-alpine") == ("8.8.1", "-alpine")


def test_parse_tag_apicurio_final():
    assert parse_tag("2.6.13.Final") == ("2.6.13", ".Final")


def test_should_skip_tag():
    assert should_skip_tag("latest") is True
    assert should_skip_tag("dev") is True
    assert should_skip_tag("sha256-abc123") is True
    assert should_skip_tag("v3.7.10") is False


def test_parse_version_safe():
    assert parse_version_safe("3.7.9") == (3, 7, 9)
    assert parse_version_safe("13.1") == (13, 1, 0)
    assert parse_version_safe("not-a-version") is None


def test_detect_version_scheme():
    assert detect_version_scheme("2026.06.0") == "calver"
    assert detect_version_scheme("3.7.9") == "semver"
    assert detect_version_scheme("18") == "semver"


def test_classify_update_patch_minor_major():
    assert classify_update("3.7.9", "3.7.10") == "patch"
    assert classify_update("8.8.1", "8.10.0") == "minor"
    assert classify_update("v1.18.3", "v2.0.0") == "major"


def test_classify_update_scheme_change():
    # semver -> calver (e.g. a hypothetical neo4j 5.x -> 2026.x jump)
    assert classify_update("5.20.0", "2026.06.0") == "scheme-change"


def test_classify_update_same_version_is_unknown():
    assert classify_update("3.7.9", "3.7.9") == "unknown"


def test_get_latest_in_track_picks_highest_same_suffix():
    tags = ["8.8.0-alpine", "8.8.1-alpine", "8.10.0-alpine", "9.0.0-bookworm"]
    latest, reason = get_latest_in_track("8.8.1-alpine", tags)
    assert latest == "8.10.0-alpine"
    assert reason == "found"


def test_get_latest_in_track_ignores_ci_build_id_tags():
    # A bare 5+ digit tag (e.g. a CI build number) must not be mistaken for a
    # real version that outranks every genuine release.
    tags = ["1.76.0", "89133199"]
    latest, reason = get_latest_in_track("1.76.0", tags)
    assert latest == "1.76.0"
    assert reason == "found"


def test_get_latest_in_track_no_valid_versions():
    latest, reason = get_latest_in_track("1.0.0-foo", ["not-a-version-foo"])
    assert latest is None
    assert reason == "no valid versions in track"


def test_get_latest_minio_release_finds_newer_base_date():
    tags = [
        "RELEASE.2025-09-07T16-13-09Z",
        "RELEASE.2025-09-07T16-13-09Z-cpuv1",
        "RELEASE.2026-01-01T00-00-00Z",
    ]
    latest, reason = get_latest_minio_release("RELEASE.2025-09-07T16-13-09Z", tags)
    assert latest == "RELEASE.2026-01-01T00-00-00Z"
    assert "update available" in reason


def test_get_latest_minio_release_already_current():
    tags = ["RELEASE.2026-01-01T00-00-00Z"]
    latest, reason = get_latest_minio_release("RELEASE.2026-01-01T00-00-00Z", tags)
    assert latest == "RELEASE.2026-01-01T00-00-00Z"
    assert reason == "up to date"


def test_get_registry():
    assert get_registry("ghcr.io/open-webui/open-webui") == "GHCR"
    assert get_registry("gcr.io/cadvisor/cadvisor") == "GCR"
    assert get_registry("minder/api-gateway") == "LOCAL"
    assert get_registry("redis") == "DOCKER_HUB"


def test_normalize_repo():
    assert normalize_repo("redis") == "library/redis"
    assert normalize_repo("grafana/grafana") == "grafana/grafana"


def _write_compose(tmp_path):
    p = tmp_path / "docker-compose.yml"
    p.write_text(_MINIO_COMPOSE)
    return str(p)


def test_minio_lookup_exception_goes_to_manual_check(tmp_path, monkeypatch):
    def boom(repo):
        raise ConnectionError("registry unreachable")

    monkeypatch.setattr(check_docker_updates, "fetch_all_tags", boom)

    (
        updates,
        safe,
        risky,
        up_to_date,
        manual_check,
        excluded,
    ) = check_updates_from_compose(_write_compose(tmp_path))

    assert "minio" not in updates
    assert "minio" not in up_to_date
    assert "minio" in manual_check
    assert "minio" not in excluded


def test_minio_unresolvable_release_goes_to_manual_check(tmp_path, monkeypatch):
    monkeypatch.setattr(check_docker_updates, "fetch_all_tags", lambda repo: [])
    monkeypatch.setattr(
        check_docker_updates,
        "get_latest_minio_release",
        lambda current, tags: (None, "no RELEASE tags found"),
    )

    (
        updates,
        safe,
        risky,
        up_to_date,
        manual_check,
        excluded,
    ) = check_updates_from_compose(_write_compose(tmp_path))

    assert "minio" not in updates
    assert "minio" not in up_to_date
    assert "minio" in manual_check
