"""Unit tests for marketplace /plugins pagination alignment (#207).

The marketplace list endpoints now accept the platform-standard ``limit``/``offset``
(canonical) alongside the deprecated ``page``/``page_size``, and return both
vocabularies in one response. These guard the pure resolution + response-shaping
helpers so the dual-scheme bridge stays correct and non-breaking.
"""

from services.marketplace.routes.marketplace import (
    _build_list_response,
    _resolve_pagination,
)


def test_limit_offset_win_when_supplied():
    assert _resolve_pagination(25, 5, 1, 10) == (25, 5)


def test_limit_only_defaults_offset_zero():
    assert _resolve_pagination(25, None, 3, 10) == (25, 0)


def test_offset_only_defaults_limit_ten():
    assert _resolve_pagination(None, 40, 3, 10) == (10, 40)


def test_falls_back_to_page_when_no_limit_offset():
    # page=2, page_size=10 → offset 10
    assert _resolve_pagination(None, None, 2, 10) == (10, 10)
    assert _resolve_pagination(None, None, 1, 25) == (25, 0)


def test_response_populates_both_vocabularies():
    r = _build_list_response([], total_count=25, limit=10, offset=10)
    # canonical
    assert (r.total, r.limit, r.offset) == (25, 10, 10)
    # deprecated page-based (offset 10 / limit 10 → page 2 of 3)
    assert (r.page, r.page_size, r.total_pages) == (2, 10, 3)
    assert r.count == 0


def test_response_zero_limit_is_guarded():
    # defensive: never divide by zero
    r = _build_list_response([], total_count=0, limit=0, offset=0)
    assert (r.page, r.total_pages) == (1, 0)
