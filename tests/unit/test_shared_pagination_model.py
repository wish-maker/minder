"""Unit tests for the shared ``PaginatedList[T]`` list envelope (#501).

Guards the one canonical `{items, total, limit, offset}` shape every service's
list endpoint returns, plus its two constructors (`from_page` wraps an
already-sliced page; `paginate` slices an in-memory sequence and wraps in one
call). Pure logic — no FastAPI app or service import needed.
"""

import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

# shared/ is imported as the top-level `shared` package across services (they put
# /app/src on sys.path); mirror that here so `from shared.models import ...` resolves.
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from shared.models import PaginatedList  # noqa: E402


class _Item(BaseModel):
    id: int


def test_from_page_wraps_precomputed_page_and_total():
    env = PaginatedList.from_page([_Item(id=1)], total=42, limit=10, offset=20)
    assert env.total == 42
    assert env.limit == 10
    assert env.offset == 20
    assert [i.id for i in env.items] == [1]


def test_paginate_slices_and_reports_preslice_total():
    items = [_Item(id=i) for i in range(10)]
    env = PaginatedList.paginate(items, limit=3, offset=6)
    # slice is items[6:9]; total stays the full pre-slice count
    assert [i.id for i in env.items] == [6, 7, 8]
    assert env.total == 10
    assert env.limit == 3
    assert env.offset == 6


def test_paginate_offset_past_end_yields_empty_page_but_full_total():
    items = [_Item(id=i) for i in range(3)]
    env = PaginatedList.paginate(items, limit=5, offset=10)
    assert env.items == []
    assert env.total == 3


def test_more_pages_predicate_holds():
    # offset + len(items) < total  ⇔  another page exists
    items = [_Item(id=i) for i in range(10)]
    first = PaginatedList.paginate(items, limit=4, offset=0)
    assert first.offset + len(first.items) < first.total  # more follows
    last = PaginatedList.paginate(items, limit=4, offset=8)
    assert last.offset + len(last.items) == last.total  # no more


def test_negative_bounds_rejected():
    with pytest.raises(ValidationError):
        PaginatedList.from_page([], total=-1, limit=10, offset=0)
    with pytest.raises(ValidationError):
        PaginatedList.from_page([], total=0, limit=10, offset=-5)


def test_serializes_to_canonical_json_keys():
    env = PaginatedList.from_page([_Item(id=7)], total=1, limit=50, offset=0)
    dumped = env.model_dump()
    assert set(dumped) == {"items", "total", "limit", "offset"}
    assert dumped["items"] == [{"id": 7}]
