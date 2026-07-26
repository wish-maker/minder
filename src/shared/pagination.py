"""Tiny list-pagination helper shared across services (#147/C6).

Slices an in-memory sequence for a `limit`/`offset` page and reports the pre-slice
total, so list endpoints can add pagination without each re-implementing the maths.
The caller validates the bounds via FastAPI `Query(..., ge=..., le=...)`.
"""

from typing import List, Sequence, Tuple, TypeVar

T = TypeVar("T")


def paginate(items: Sequence[T], limit: int, offset: int) -> Tuple[List[T], int]:
    """Return ``(page_slice, total_count)`` for ``items[offset : offset + limit]``."""
    total = len(items)
    return list(items)[offset : offset + limit], total
