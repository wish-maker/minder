"""Unit tests for the tag cache (scripts/setup/cache.py) -- cache_file,
cache_expired, load_cached_tags, and cache_tags had zero direct unit tests
(18%). Pure filesystem functions, exercised against tmp_path; the two OSError
fallback branches use a small duck-typed fake (not a global Path patch, which
would affect pytest's own internals -- see test_setup_doctor_run.py).
"""

import os
import time

from scripts.setup import cache


class _FakePath:
    """Duck-types just enough of pathlib.Path for cache.py's call sites,
    without ever touching the real (process-shared) Path class."""

    def __init__(self, real_path, *, stat_error=None, read_error=None):
        self._real = real_path
        self._stat_error = stat_error
        self._read_error = read_error

    def is_file(self):
        return self._real.is_file()

    def stat(self):
        if self._stat_error is not None:
            raise self._stat_error
        return self._real.stat()

    def read_text(self, encoding="utf-8"):
        if self._read_error is not None:
            raise self._read_error
        return self._real.read_text(encoding=encoding)

    @property
    def parent(self):
        return self._real.parent

    def __fspath__(self):
        return str(self._real)

    def __str__(self):
        return str(self._real)

    def open(self, *args, **kwargs):
        return self._real.open(*args, **kwargs)


def test_cache_file_replaces_slashes_in_repo_name():
    path = cache.cache_file("docker.io", "library/postgres")
    assert path == cache.config.CACHE_DIR / "docker.io" / "library--postgres.json"


def test_cache_expired_true_when_file_missing(tmp_path):
    assert cache.cache_expired(tmp_path / "nope.json") is True


def test_cache_expired_false_for_a_fresh_file(tmp_path):
    p = tmp_path / "fresh.json"
    p.write_text("{}")
    assert cache.cache_expired(p) is False


def test_cache_expired_true_for_a_stale_file(tmp_path, monkeypatch):
    p = tmp_path / "stale.json"
    p.write_text("{}")
    old_time = time.time() - (cache.config.CACHE_TTL_HOURS * 3600) - 60
    os.utime(p, (old_time, old_time))
    assert cache.cache_expired(p) is True


def test_cache_expired_treats_stat_oserror_as_epoch_zero_so_expired(tmp_path):
    p = tmp_path / "weird.json"
    p.write_text("{}")
    fake = _FakePath(p, stat_error=OSError("boom"))
    assert cache.cache_expired(fake) is True


def test_load_cached_tags_returns_empty_when_expired(tmp_path):
    assert cache.load_cached_tags(tmp_path / "missing.json") == ""


def test_load_cached_tags_parses_tags_array_from_json(tmp_path):
    p = tmp_path / "tags.json"
    p.write_text(
        '{\n  "timestamp": "2026-01-01T00:00:00Z",\n'
        '  "tags": [\n    "1.0.0",\n    "1.1.0",\n    "latest"\n  ]\n}\n'
    )
    assert cache.load_cached_tags(p) == "1.0.0\n1.1.0\nlatest"


def test_load_cached_tags_returns_empty_when_no_tags_block_present(tmp_path):
    p = tmp_path / "no_tags.json"
    p.write_text('{"timestamp": "2026-01-01T00:00:00Z"}\n')
    assert cache.load_cached_tags(p) == ""


def test_load_cached_tags_returns_empty_when_file_vanishes_between_checks(tmp_path):
    """TOCTOU: cache_expired() sees the file, but it's gone by load_cached_tags'
    own is_file() re-check -- the defensive `if not path.is_file()` guard."""
    p = tmp_path / "vanishing.json"
    p.write_text('{"tags": ["1.0.0"]}\n')

    class _VanishingPath(_FakePath):
        def __init__(self, real_path):
            super().__init__(real_path)
            self._is_file_calls = 0

        def is_file(self):
            self._is_file_calls += 1
            return self._is_file_calls == 1

    assert cache.load_cached_tags(_VanishingPath(p)) == ""


def test_load_cached_tags_returns_empty_on_read_error(tmp_path):
    p = tmp_path / "unreadable.json"
    p.write_text('{"tags": ["1.0.0"]}\n')
    fake = _FakePath(p, read_error=OSError("boom"))
    assert cache.load_cached_tags(fake) == ""


def test_cache_tags_writes_expected_json_shape_and_logs_debug(tmp_path, monkeypatch):
    debug_calls = []
    monkeypatch.setattr(cache.log, "debug", lambda msg: debug_calls.append(msg))
    target = tmp_path / "sub" / "repo.json"

    cache.cache_tags(target, "1.0.0\n1.1.0\nlatest", "2026-01-01T00:00:00Z")

    content = target.read_text(encoding="utf-8")
    assert content == (
        "{\n"
        '  "timestamp": "2026-01-01T00:00:00Z",\n'
        '  "tags": [\n'
        '    "1.0.0",\n'
        '    "1.1.0",\n'
        '    "latest"\n'
        "  ]\n"
        "}\n"
    )
    assert len(debug_calls) == 1
    assert str(target) in debug_calls[0]


def test_cache_tags_round_trips_through_load_cached_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.log, "debug", lambda msg: None)
    target = tmp_path / "roundtrip.json"

    cache.cache_tags(target, "a\nb\nc", "2026-01-01T00:00:00Z")

    assert cache.load_cached_tags(target) == "a\nb\nc"
