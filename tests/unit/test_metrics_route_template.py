"""Unit tests for shared.metrics bounded-cardinality labelling (#503).

The HTTP metrics must label `endpoint` with the matched route TEMPLATE
(`/items/{item_id}`), not the concrete path (`/items/aaa`), so a Counter/Histogram
doesn't grow one Prometheus time series per distinct id value.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.metrics import http_requests_in_progress, setup_metrics


def _make_app() -> FastAPI:
    app = FastAPI()
    setup_metrics(app)

    @app.get("/items/{item_id}")
    async def get_item(item_id: str):
        return {"id": item_id}

    return app


def test_parameterized_route_collapses_to_one_series():
    client = TestClient(_make_app())
    client.get("/items/aaa")
    client.get("/items/bbb")
    metrics = client.get("/metrics").text

    # The route template is labelled; the concrete ids never become their own series.
    assert 'endpoint="/items/{item_id}"' in metrics
    assert 'endpoint="/items/aaa"' not in metrics
    assert 'endpoint="/items/bbb"' not in metrics


def test_unmatched_paths_bucketed_together():
    client = TestClient(_make_app())
    client.get("/nope/xyz")
    client.get("/nope/abc")
    metrics = client.get("/metrics").text

    # 404 / scanner traffic collapses to one bucket, not a series per random URL.
    assert 'endpoint="__unmatched__"' in metrics
    assert 'endpoint="/nope/xyz"' not in metrics
    assert 'endpoint="/nope/abc"' not in metrics


def test_in_progress_gauge_has_no_endpoint_label():
    # in_progress must be method-only (bounded) — it can't know the route pre-routing.
    assert tuple(http_requests_in_progress._labelnames) == ("method",)
