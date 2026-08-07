"""Unit tests for `doctor`'s weak-secret detection (scripts/setup/doctor.py).

_WEAK_RE used to be a case-sensitive, exact-match-only list that missed the
actual placeholder shape .env.example ships (CHANGEME_POSTGRES_SECRET_32_CHARS
etc, uppercase with a suffix) -- broadened to catch that pattern too.
"""

import pytest

from scripts.setup.doctor import _WEAK_RE


@pytest.mark.parametrize(
    "value",
    [
        "admin",
        "ADMIN",
        "password",
        "Password",
        "secret",
        "changeme",
        "CHANGEME",
        "CHANGEME_POSTGRES_SECRET_32_CHARS",
        "changeme_jwt_secret_minimum_64_chars_recommended",
        "replace_me",
        "minder",
    ],
)
def test_weak_values_detected(value):
    assert _WEAK_RE.match(value)


@pytest.mark.parametrize(
    "value",
    [
        "a-genuinely-random-32-char-secret-xyz",
        "correct-horse-battery-staple-9f3a",
        "",
        "administrator",  # must not partially match "admin" -- full-string anchor
        "mysecretpassword",  # must not partially match "secret"/"password"
    ],
)
def test_strong_or_unrelated_values_not_flagged(value):
    assert not _WEAK_RE.match(value)
