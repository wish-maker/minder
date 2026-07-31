"""Unit tests for rate-limit store bounding (#211 LOW).

The in-memory rate-limit store pruned old timestamps within a key but never removed
emptied keys, so every user/IP × path combination left a permanent entry. The prune
helper now deletes a key once it empties, keeping the store bounded.
"""

from shared.auth.jwt_middleware import _prune_rate_limit_key


def test_prunes_old_timestamps_keeps_fresh():
    store = {"u:/p": [1.0, 5.0, 9.0]}
    _prune_rate_limit_key(store, "u:/p", window_start=4.0)
    assert store["u:/p"] == [5.0, 9.0]


def test_removes_key_when_it_empties():
    store = {"u:/p": [1.0, 2.0]}
    _prune_rate_limit_key(store, "u:/p", window_start=10.0)
    assert "u:/p" not in store  # bounded: no leftover empty-list entry


def test_missing_key_is_noop():
    store = {"other": [1.0]}
    _prune_rate_limit_key(store, "u:/p", window_start=0.0)
    assert store == {"other": [1.0]}
