"""Shared list-response envelope (#501).

One canonical shape for every paginated `list` endpoint across services, so a
cross-service client sees the same `{items, total, limit, offset}` structure
everywhere instead of each service hand-rolling its own (bare arrays in
rag-pipeline, ad-hoc `{plugins, count, ...}` dicts in plugin-registry, a legacy
`page/page_size` scheme in marketplace, ...).

Pairs with ``shared.pagination.paginate`` (the in-memory slicer): ``paginate``
computes ``(page, total)``; ``PaginatedList.from_page`` wraps that into the
envelope without each endpoint re-stating the field plumbing.
"""

from typing import Generic, List, Sequence, TypeVar

from pydantic import BaseModel, Field

from ..pagination import paginate

T = TypeVar("T")


class PaginatedList(BaseModel, Generic[T]):
    """Canonical paginated list envelope.

    ``total`` is the pre-slice count (how many items exist in all), so a caller
    holding ``offset + len(items) < total`` knows another page follows.
    """

    items: List[T]
    total: int = Field(..., ge=0, description="Total items across all pages")
    limit: int = Field(..., ge=0, description="Page size requested")
    offset: int = Field(..., ge=0, description="Items skipped before this page")

    @classmethod
    def from_page(
        cls, items: Sequence[T], total: int, limit: int, offset: int
    ) -> "PaginatedList[T]":
        """Build an envelope from an already-sliced page and its pre-slice total."""
        return cls(items=list(items), total=total, limit=limit, offset=offset)

    @classmethod
    def paginate(
        cls, items: Sequence[T], limit: int, offset: int
    ) -> "PaginatedList[T]":
        """Slice an in-memory sequence and wrap it in one call.

        Convenience for the common case where the endpoint holds the full list
        in memory (rag-pipeline's KB/pipeline dicts): does the ``paginate`` slice
        and the envelope wrap together.
        """
        page, total = paginate(items, limit, offset)
        return cls(items=page, total=total, limit=limit, offset=offset)
