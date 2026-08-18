"""Unit tests for scripts/setup/versions.py -- the pure algorithmic core
(registry_type/image_repo/strip_v/ver_ge/tag_satisfies_constraint/best_tag),
spec derivation (compose_image_refs/third_party_image_specs/
third_party_images), the registry layer (_http_get/*_list_tags/_tag_exists),
and the orchestration layer (resolve_image_tag/pull_image_with_fallback/
pull_all_images/version_drift_report) -- 18% coverage, previously only the
SKIP_VERSION_CHECK/patch-constraint deterministic short-circuit was exercised
(via the install/update/doctor gate scripts). Every network/subprocess/docker
call is mocked; log.spinner_start/stop are no-op'd everywhere (real spinner
threading is log.py's own concern, not this module's).
"""

import subprocess

import pytest

from scripts.setup import versions


@pytest.fixture(autouse=True)
def _no_spinner(monkeypatch):
    monkeypatch.setattr(versions.log, "spinner_start", lambda msg: None)
    monkeypatch.setattr(versions.log, "spinner_stop", lambda: None)


@pytest.fixture(autouse=True)
def _reset_memo():
    versions.RESOLVED_IMAGE_TAGS.clear()
    yield
    versions.RESOLVED_IMAGE_TAGS.clear()


# ── compose_image_refs ────────────────────────────────────────────────────────


def test_compose_image_refs_extracts_and_strips_trailing_comments(
    tmp_path, monkeypatch
):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n"
        "  postgres:\n"
        "    image: postgres:16.1  # pinned\n"
        "    ports:\n"
        "      - 5432:5432\n"
        "  redis:\n"
        "    image: redis:7.2\n"
    )
    monkeypatch.setattr(versions.config, "COMPOSE_FILE", compose)

    assert versions.compose_image_refs() == ["postgres:16.1", "redis:7.2"]


def test_compose_image_refs_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(versions.config, "COMPOSE_FILE", tmp_path / "nope.yml")
    assert versions.compose_image_refs() == []


# ── third_party_image_specs / third_party_images ──────────────────────────────


def test_third_party_image_specs_joins_matching_metadata_in_compose_order(
    monkeypatch,
):
    monkeypatch.setattr(
        versions,
        "compose_image_refs",
        lambda: ["postgres:16.1", "myapp:1.0", "redis:7.2"],
    )
    monkeypatch.setattr(
        versions.config,
        "THIRD_PARTY_IMAGE_META",
        {"postgres": "16|major", "redis": "7|minor"},
    )

    assert versions.third_party_image_specs() == [
        "postgres:16.1|16|major",
        "redis:7.2|7|minor",
    ]


def test_third_party_image_specs_warns_on_stale_metadata(monkeypatch, capsys):
    monkeypatch.setattr(versions, "compose_image_refs", lambda: ["postgres:16.1"])
    monkeypatch.setattr(
        versions.config,
        "THIRD_PARTY_IMAGE_META",
        {"postgres": "16|major", "ghost": "1|none"},
    )

    versions.third_party_image_specs()

    err = capsys.readouterr().err
    assert "THIRD_PARTY_IMAGE_META has 'ghost'" in err


def test_third_party_image_specs_skips_blank_refs(monkeypatch):
    monkeypatch.setattr(versions, "compose_image_refs", lambda: ["", "postgres:16.1"])
    monkeypatch.setattr(
        versions.config, "THIRD_PARTY_IMAGE_META", {"postgres": "16|major"}
    )

    assert versions.third_party_image_specs() == ["postgres:16.1|16|major"]


def test_third_party_images_returns_just_the_pinned_refs(monkeypatch):
    monkeypatch.setattr(
        versions,
        "third_party_image_specs",
        lambda: ["postgres:16.1|16|major", "redis:7.2|7|minor"],
    )

    assert versions.third_party_images() == ["postgres:16.1", "redis:7.2"]


# ── pure helpers ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("ghcr.io/org/app:1.0", "ghcr"),
        ("quay.io/org/app:1.0", "quay"),
        ("postgres:16.1", "dockerhub"),
        ("myorg/app:1.0", "dockerhub"),
    ],
)
def test_registry_type(ref, expected):
    assert versions.registry_type(ref) == expected


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("ghcr.io/org/app:1.0", "org/app"),
        ("quay.io/org/app:1.0", "org/app"),
        ("myorg/app:1.0", "myorg/app"),
        ("postgres:16.1", "library/postgres"),
    ],
)
def test_image_repo(ref, expected):
    assert versions.image_repo(ref) == expected


@pytest.mark.parametrize(
    "ver,expected", [("v1.2.3", "1.2.3"), ("1.2.3", "1.2.3"), ("v", "")]
)
def test_strip_v(ver, expected):
    assert versions.strip_v(ver) == expected


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("1.2.3", "1.2.0", True),
        ("1.2.0", "1.2.3", False),
        ("v2.0.0", "1.9.9", True),
        # shorter component lists compare as "less than" their longer prefix
        # match (list comparison, not numeric padding) -- documents the real
        # behaviour, since best_tag only ever compares same-shape release tags.
        ("1.2", "1.2.0", False),
        ("1.2.0", "1.2", True),
        ("1.2.3", "1.2.3", True),
    ],
)
def test_ver_ge(a, b, expected):
    assert versions.ver_ge(a, b) is expected


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("3.10.1-core", "core"),
        ("v1.18.2", ""),
        ("v1-unprivileged", "unprivileged"),
        ("1.2.3", ""),
    ],
)
def test_tag_variant(tag, expected):
    assert versions._tag_variant(tag) == expected


@pytest.mark.parametrize(
    "tag,stable_prefix,constraint,expected",
    [
        ("16.2", "16", "major", True),
        ("17.0", "16", "major", False),
        ("16.2.5", "16.2", "minor", True),
        ("16.3.0", "16.2", "minor", False),
        ("99.0.0", "1", "none", True),
        ("16.2-rc1", "16", "major", False),
        ("not-a-version", "16", "major", False),
        ("16.2", "16", "unknown-constraint", False),
    ],
)
def test_tag_satisfies_constraint(tag, stable_prefix, constraint, expected):
    assert versions.tag_satisfies_constraint(tag, stable_prefix, constraint) is expected


def test_best_tag_picks_the_highest_satisfying_tag():
    tags = "16.0\n16.5\n16.2\n17.0\n16.5-rc1"
    assert versions.best_tag(tags, "16", "major") == "16.5"


def test_best_tag_returns_empty_when_nothing_satisfies():
    assert versions.best_tag("17.0\n18.0", "16", "major") == ""


def test_best_tag_skips_blank_lines():
    assert versions.best_tag("\n16.1\n\n16.2\n", "16", "major") == "16.2"


def test_best_tag_a_later_equal_tag_replaces_the_earlier_one():
    # mirrors the bash loop's `>=` tie behaviour exactly (documents current
    # observable behaviour, not a "fix").
    assert versions.best_tag("16.2\n16.2", "16", "major") == "16.2"


# ── _http_get ──────────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_get_returns_body_on_2xx(monkeypatch):
    monkeypatch.setattr(
        versions.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResponse(200, b"hello"),
    )
    assert versions._http_get("http://example.test") == "hello"


def test_http_get_returns_none_on_non_2xx(monkeypatch):
    monkeypatch.setattr(
        versions.urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResponse(404, b""),
    )
    assert versions._http_get("http://example.test") is None


def test_http_get_returns_none_on_any_exception(monkeypatch):
    def _raise(req, timeout=None):
        raise OSError("network unreachable")

    monkeypatch.setattr(versions.urllib.request, "urlopen", _raise)
    assert versions._http_get("http://example.test") is None


def test_extract_name_values_pulls_every_name_field():
    text = '{"name": "1.0.0"}, {"name":"1.1.0"}'
    assert versions._extract_name_values(text) == ["1.0.0", "1.1.0"]


# ── *_list_tags ────────────────────────────────────────────────────────────────


def test_dockerhub_list_tags_uses_cache_when_present(monkeypatch):
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "1.0.0\n1.1.0")
    monkeypatch.setattr(
        versions, "_http_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )
    assert versions.dockerhub_list_tags("library/postgres") == "1.0.0\n1.1.0"


def test_dockerhub_list_tags_returns_empty_on_http_failure(monkeypatch):
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "")
    monkeypatch.setattr(versions, "_http_get", lambda *a, **k: None)
    assert versions.dockerhub_list_tags("library/postgres") == ""


def test_dockerhub_list_tags_parses_and_caches_on_success(monkeypatch):
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "")
    monkeypatch.setattr(versions.cache, "cache_file", lambda registry, repo: "cf")
    monkeypatch.setattr(
        versions, "_http_get", lambda *a, **k: '{"name": "1.0.0"}, {"name": "1.1.0"}'
    )
    cached = {}
    monkeypatch.setattr(
        versions.cache,
        "cache_tags",
        lambda cf, tags, ts: cached.setdefault("tags", tags),
    )

    result = versions.dockerhub_list_tags("library/postgres")

    assert result == "1.0.0\n1.1.0"
    assert cached["tags"] == "1.0.0\n1.1.0"


def test_ghcr_list_tags_uses_cache_when_present(monkeypatch):
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "1.0.0")
    assert versions.ghcr_list_tags("org/app") == "1.0.0"


def test_ghcr_list_tags_returns_empty_on_http_failure(monkeypatch):
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "")
    monkeypatch.setattr(versions, "_http_get", lambda *a, **k: None)
    assert versions.ghcr_list_tags("org/app") == ""


def test_ghcr_list_tags_matches_every_quoted_string_a_documented_quirk(monkeypatch):
    # The bash grep -v pattern is BRE (a literal '|'), so it filters nothing --
    # "tags"/"name" leak into the result. Reproduced faithfully; this test
    # characterizes the existing (quirky) behaviour, not a "fix".
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "")
    monkeypatch.setattr(versions.cache, "cache_file", lambda registry, repo: "cf")
    monkeypatch.setattr(versions.cache, "cache_tags", lambda *a, **k: None)
    monkeypatch.setattr(
        versions, "_http_get", lambda *a, **k: '{"name":"app","tags":["1.0","2.0"]}'
    )

    result = versions.ghcr_list_tags("org/app")

    assert result.split("\n") == ["name", "app", "tags", "1.0", "2.0"]


def test_quay_list_tags_uses_cache_when_present(monkeypatch):
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "1.0.0")
    assert versions.quay_list_tags("org/app") == "1.0.0"


def test_quay_list_tags_returns_empty_on_http_failure(monkeypatch):
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "")
    monkeypatch.setattr(versions, "_http_get", lambda *a, **k: None)
    assert versions.quay_list_tags("org/app") == ""


def test_quay_list_tags_parses_and_caches_on_success(monkeypatch):
    monkeypatch.setattr(versions.cache, "load_cached_tags", lambda cf: "")
    monkeypatch.setattr(versions.cache, "cache_file", lambda registry, repo: "cf")
    monkeypatch.setattr(versions, "_http_get", lambda *a, **k: '{"name": "2.0.0"}')
    monkeypatch.setattr(versions.cache, "cache_tags", lambda *a, **k: None)

    assert versions.quay_list_tags("org/app") == "2.0.0"


# ── _list_tags / _tag_exists / _ref_for ───────────────────────────────────────


@pytest.mark.parametrize(
    "registry,expected_fn",
    [
        ("ghcr", "ghcr_list_tags"),
        ("quay", "quay_list_tags"),
        ("dockerhub", "dockerhub_list_tags"),
    ],
)
def test_list_tags_routes_by_registry(monkeypatch, registry, expected_fn):
    calls = []
    for name in ("ghcr_list_tags", "quay_list_tags", "dockerhub_list_tags"):
        monkeypatch.setattr(versions, name, lambda repo, n=name: calls.append(n))

    versions._list_tags(registry, "org/app")

    assert calls == [expected_fn]


def test_tag_exists_dockerhub_uses_http_get(monkeypatch):
    monkeypatch.setattr(versions, "_http_get", lambda url: "body")
    assert versions._tag_exists("dockerhub", "library/postgres", "16.1", "x") is True


def test_tag_exists_dockerhub_false_when_http_get_fails(monkeypatch):
    monkeypatch.setattr(versions, "_http_get", lambda url: None)
    assert versions._tag_exists("dockerhub", "library/postgres", "16.1", "x") is False


def test_tag_exists_non_dockerhub_uses_docker_manifest_inspect(monkeypatch):
    captured = {}

    def _fake_run(argv, **kw):
        captured["argv"] = argv
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(versions.subprocess, "run", _fake_run)
    assert versions._tag_exists("ghcr", "org/app", "1.0", "ghcr.io/org/app:1.0") is True
    assert captured["argv"] == ["docker", "manifest", "inspect", "ghcr.io/org/app:1.0"]


def test_tag_exists_non_dockerhub_false_on_nonzero_returncode(monkeypatch):
    monkeypatch.setattr(
        versions.subprocess,
        "run",
        lambda argv, **kw: type("R", (), {"returncode": 1})(),
    )
    assert versions._tag_exists("ghcr", "org/app", "1.0", "x") is False


@pytest.mark.parametrize(
    "exc", [OSError("boom"), subprocess.TimeoutExpired(cmd="x", timeout=5)]
)
def test_tag_exists_non_dockerhub_false_on_exception(monkeypatch, exc):
    def _raise(argv, **kw):
        raise exc

    monkeypatch.setattr(versions.subprocess, "run", _raise)
    assert versions._tag_exists("ghcr", "org/app", "1.0", "x") is False


@pytest.mark.parametrize(
    "registry,repo,image_base,tag,expected",
    [
        ("ghcr", "org/app", "ghcr.io/org/app", "1.0", "ghcr.io/org/app:1.0"),
        ("quay", "org/app", "quay.io/org/app", "1.0", "quay.io/org/app:1.0"),
        ("dockerhub", "library/postgres", "postgres", "16.1", "postgres:16.1"),
    ],
)
def test_ref_for(registry, repo, image_base, tag, expected):
    assert versions._ref_for(registry, repo, image_base, tag) == expected


# ── resolve_image_tag ─────────────────────────────────────────────────────────


def test_resolve_image_tag_memoized_short_circuit(monkeypatch):
    versions.RESOLVED_IMAGE_TAGS["postgres:16.1"] = "postgres:16.5"
    monkeypatch.setattr(
        versions, "_list_tags", lambda *a: (_ for _ in ()).throw(AssertionError)
    )

    assert versions.resolve_image_tag("postgres:16.1|16|major") == "postgres:16.5"


def test_resolve_image_tag_patch_constraint_short_circuits_to_pin(monkeypatch):
    monkeypatch.setattr(
        versions, "_list_tags", lambda *a: (_ for _ in ()).throw(AssertionError)
    )
    assert versions.resolve_image_tag("postgres:16.1|16|patch") == "postgres:16.1"


def test_resolve_image_tag_skip_version_check_short_circuits_to_pin(monkeypatch):
    monkeypatch.setattr(versions.config, "SKIP_VERSION_CHECK", True)
    monkeypatch.setattr(
        versions, "_list_tags", lambda *a: (_ for _ in ()).throw(AssertionError)
    )
    assert versions.resolve_image_tag("postgres:16.1|16|major") == "postgres:16.1"


def test_resolve_image_tag_falls_back_to_pin_when_no_tags_found(monkeypatch):
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "")
    assert versions.resolve_image_tag("postgres:16.1|16|major") == "postgres:16.1"


def test_resolve_image_tag_falls_back_to_pin_when_nothing_satisfies(monkeypatch):
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "17.0\n18.0")
    assert versions.resolve_image_tag("postgres:16.1|16|major") == "postgres:16.1"


def test_resolve_image_tag_short_circuits_when_best_equals_pin(monkeypatch):
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "16.1\n15.0")
    monkeypatch.setattr(
        versions, "_tag_exists", lambda *a: (_ for _ in ()).throw(AssertionError)
    )
    assert versions.resolve_image_tag("postgres:16.1|16|major") == "postgres:16.1"


def test_resolve_image_tag_reports_pinned_when_loop_lands_back_on_the_pin(
    monkeypatch,
):
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "16.5\n16.1\n15.0")
    monkeypatch.setattr(
        versions, "_tag_exists", lambda registry, repo, tag, test_ref: tag == "16.1"
    )

    result = versions.resolve_image_tag("postgres:16.1|16|major")

    assert result == "postgres:16.1"


def test_resolve_image_tag_upgrades_to_the_newest_working_tag(monkeypatch):
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "16.5\n16.1\n15.0")
    monkeypatch.setattr(versions, "_tag_exists", lambda *a: True)

    result = versions.resolve_image_tag("postgres:16.1|16|major")

    assert result == "postgres:16.5"


def test_resolve_image_tag_upgrades_with_color_on(monkeypatch):
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "16.5\n16.1\n15.0")
    monkeypatch.setattr(versions, "_tag_exists", lambda *a: True)
    monkeypatch.setattr(versions.log, "_colors_on", lambda: True)

    result = versions.resolve_image_tag("postgres:16.1|16|major")

    assert result == "postgres:16.5"


def test_resolve_image_tag_never_downgrades_or_swaps_edition(monkeypatch):
    # a lower major and a different variant are both present but must be
    # rejected -- only the pin's own edition/track, at >= its version, counts.
    monkeypatch.setattr(
        versions, "_list_tags", lambda *a: "16.5-enterprise\n10.0\n16.1"
    )
    monkeypatch.setattr(versions, "_tag_exists", lambda *a: True)

    result = versions.resolve_image_tag("postgres:16.1|16|major")

    assert result == "postgres:16.1"


def test_resolve_image_tag_falls_back_to_pin_when_no_candidate_tag_exists(
    monkeypatch,
):
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "16.5\n16.4")
    monkeypatch.setattr(versions, "_tag_exists", lambda *a: False)

    result = versions.resolve_image_tag("postgres:16.1|16|major")

    assert result == "postgres:16.1"


def test_resolve_image_tag_skips_duplicate_and_too_old_candidates_in_the_loop(
    monkeypatch,
):
    # "16.1" satisfies the constraint/variant but is older than the pin (skips
    # via the ver_ge guard); "16.9" appears twice -- the second occurrence
    # skips via the already-tried guard. Neither ever resolves (_tag_exists
    # always False), so the loop exhausts and falls back to the pin.
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "16.1\n16.9\n16.9")
    monkeypatch.setattr(versions, "_tag_exists", lambda *a: False)

    result = versions.resolve_image_tag("postgres:16.5|16|major")

    assert result == "postgres:16.5"


def test_resolve_image_tag_ghcr_ref_shape(monkeypatch):
    monkeypatch.setattr(versions, "_list_tags", lambda *a: "1.5\n1.0")
    monkeypatch.setattr(versions, "_tag_exists", lambda *a: True)

    result = versions.resolve_image_tag("ghcr.io/org/app:1.0|1|major")

    assert result == "ghcr.io/org/app:1.5"


# ── pull_image_with_fallback ──────────────────────────────────────────────────
# #178: `update` used to pull the smart-resolved newer image but ran the pinned
# version, because the resolved ref was never retagged to the compose-pinned
# ref that the rolling `compose up` references. The retag-when-differs test
# below locks that fix in; the skip-tag-when-equal test locks in that the
# SKIP_VERSION_CHECK/patch path (resolved == pin) stays a plain pull.


def test_pull_image_with_fallback_success_retags_when_resolved_differs(monkeypatch):
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.5")
    calls = []
    monkeypatch.setattr(
        versions.docker, "run", lambda *args, **kw: calls.append(args) or 0
    )

    rc = versions.pull_image_with_fallback("postgres:16.1|16|major")

    assert rc == 0
    assert ("docker", "pull", "postgres:16.5") in calls
    assert ("docker", "tag", "postgres:16.5", "postgres:16.1") in calls


def test_pull_image_with_fallback_success_skips_tag_when_resolved_equals_pin(
    monkeypatch,
):
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.1")
    calls = []
    monkeypatch.setattr(
        versions.docker, "run", lambda *args, **kw: calls.append(args) or 0
    )

    versions.pull_image_with_fallback("postgres:16.1|16|major")

    assert calls == [("docker", "pull", "postgres:16.1")]


def test_pull_image_with_fallback_falls_back_when_resolved_pull_fails(monkeypatch):
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.5")
    calls = []

    def _fake_run(*args, **kw):
        calls.append(args)
        return 0 if args == ("docker", "pull", "postgres:16.1") else 1

    monkeypatch.setattr(versions.docker, "run", _fake_run)

    rc = versions.pull_image_with_fallback("postgres:16.1|16|major")

    assert rc == 0
    assert versions.RESOLVED_IMAGE_TAGS["postgres:16.1"] == "postgres:16.1"
    # we're already back on the pin -- no retag needed
    assert not any(c[:2] == ("docker", "tag") for c in calls)


def test_pull_image_with_fallback_both_pulls_fail(monkeypatch, capfd):
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.5")
    monkeypatch.setattr(versions.docker, "run", lambda *args, **kw: 1)

    rc = versions.pull_image_with_fallback("postgres:16.1|16|major")

    out = capfd.readouterr().out
    assert rc == 0
    assert "also failed" in out


def test_pull_image_with_fallback_no_fallback_attempted_when_resolved_equals_pin(
    monkeypatch, capfd
):
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.1")
    monkeypatch.setattr(versions.docker, "run", lambda *args, **kw: 1)

    rc = versions.pull_image_with_fallback("postgres:16.1|16|major")

    out = capfd.readouterr().out
    assert rc == 0
    assert "may already be cached locally" in out
    assert "also failed" not in out


# ── pull_all_images ────────────────────────────────────────────────────────────


def test_pull_all_images_pulls_every_spec_in_order(monkeypatch):
    specs = ["postgres:16.1|16|major", "redis:7.2|7|minor"]
    monkeypatch.setattr(versions, "third_party_image_specs", lambda: specs)
    calls = []
    monkeypatch.setattr(
        versions, "pull_image_with_fallback", lambda spec: calls.append(spec)
    )

    versions.pull_all_images()

    assert calls == specs


# ── version_drift_report ──────────────────────────────────────────────────────


def test_version_drift_report_reports_up_to_date_when_nothing_drifted(
    monkeypatch, capfd
):
    monkeypatch.setattr(
        versions, "third_party_image_specs", lambda: ["postgres:16.1|16|major"]
    )
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.1")

    rc = versions.version_drift_report(False)

    out = capfd.readouterr().out
    assert rc == 0
    assert "up to date" in out.lower()


def test_version_drift_report_lists_drifted_images_in_text_mode(monkeypatch, capfd):
    monkeypatch.setattr(
        versions,
        "third_party_image_specs",
        lambda: ["postgres:16.1|16|major", "redis:7.2|7|minor"],
    )

    def _resolve(spec):
        return "postgres:16.5" if spec.startswith("postgres") else "redis:7.2"

    monkeypatch.setattr(versions, "resolve_image_tag", _resolve)

    rc = versions.version_drift_report(False)

    out = capfd.readouterr().out
    assert rc == 1
    assert "1 update(s) available" in out
    assert "postgres" in out
    assert "16.1" in out
    assert "16.5" in out


def test_version_drift_report_lists_drifted_images_with_color_on(monkeypatch, capfd):
    monkeypatch.setattr(versions.log, "_colors_on", lambda: True)
    monkeypatch.setattr(
        versions, "third_party_image_specs", lambda: ["postgres:16.1|16|major"]
    )
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.5")

    rc = versions.version_drift_report(False)

    out = capfd.readouterr().out
    assert rc == 1
    assert versions.log._CYAN in out
    assert "postgres" in out


def test_version_drift_report_shows_ok_items_only_when_verbose(monkeypatch, capfd):
    monkeypatch.setattr(versions.config, "VERBOSE", True)
    monkeypatch.setattr(
        versions, "third_party_image_specs", lambda: ["postgres:16.1|16|major"]
    )
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.1")

    versions.version_drift_report(False)

    out = capfd.readouterr().out
    assert "Up to date" in out
    assert "postgres:16.1" in out


def test_version_drift_report_json_mode_with_drift(monkeypatch, capfd):
    monkeypatch.setattr(
        versions, "third_party_image_specs", lambda: ["postgres:16.1|16|major"]
    )
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.5")

    rc = versions.version_drift_report(True)

    out = capfd.readouterr().out
    assert rc == 1
    assert '"updates_available": 1' in out
    assert '"image":"postgres"' in out
    assert '"current":"16.1"' in out
    assert '"available":"16.5"' in out


def test_version_drift_report_json_mode_with_multiple_drift_items(monkeypatch, capfd):
    monkeypatch.setattr(
        versions,
        "third_party_image_specs",
        lambda: ["postgres:16.1|16|major", "redis:7.2|7|minor"],
    )

    def _resolve(spec):
        return "postgres:16.5" if spec.startswith("postgres") else "redis:7.5"

    monkeypatch.setattr(versions, "resolve_image_tag", _resolve)

    rc = versions.version_drift_report(True)

    out = capfd.readouterr().out
    assert rc == 2
    assert '"updates_available": 2' in out
    assert out.count('"image":') == 2
    # the i > 0 branch separates entries with a comma between the two objects
    assert "},\n    {" in out


def test_version_drift_report_json_mode_with_no_drift(monkeypatch, capfd):
    monkeypatch.setattr(
        versions, "third_party_image_specs", lambda: ["postgres:16.1|16|major"]
    )
    monkeypatch.setattr(versions, "resolve_image_tag", lambda spec: "postgres:16.1")

    rc = versions.version_drift_report(True)

    out = capfd.readouterr().out
    assert rc == 0
    assert '"updates_available": 0' in out
    assert '"drift": [' in out
