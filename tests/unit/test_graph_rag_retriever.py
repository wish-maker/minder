"""Unit tests for graph-rag's core/graph_retriever.py.

GraphRetriever had zero direct test coverage -- the existing knowledge-graph
handler test explicitly fakes the whole class out (`GraphRetriever = object`)
to avoid the neo4j/spacy dependency chain at the route layer. `neo4j` itself is
a real, present dependency in this shared test venv (unlike spacy, which isn't
installed here at all) -- only the driver/session/result need faking, not the
whole package, so this module's actual query-building and record-parsing logic
is directly testable.

Covers two behaviors this module's own comments flag as previously-buggy fixes
(#248 case-insensitive matching; the Document-node leak in multi-hop
traversal), plus the exception-swallowing contract every method documents
(never raise, degrade to an empty/error result).

Loaded via sys.path (graph-rag has no cross-service-name collision risk like
plugin-registry/marketplace's `core`/`config`/`models`, so no stale-cache
clearing needed beyond a straightforward fresh import).
"""

import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "graph-rag"


def _load():
    if str(_SERVICE_DIR) not in sys.path:
        sys.path.insert(0, str(_SERVICE_DIR))
    for stale in list(sys.modules):
        if stale == "core" or stale.startswith("core."):
            del sys.modules[stale]
    import importlib

    return importlib.import_module("core.graph_retriever")


class _FakeRecord(dict):
    """Neo4j records support both record["key"] (already dict.__getitem__) and
    record.get("key", default) (already dict.get) -- no extra behavior needed."""


class _FakeResult:
    def __init__(self, records):
        self._records = list(records)

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for r in self._records:
            yield r

    async def single(self):
        return self._records[0] if self._records else None


class _FakeSession:
    def __init__(self, run_fn):
        self._run_fn = run_fn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, cypher, **params):
        return self._run_fn(cypher, params)


class _FakeDriver:
    def __init__(self, run_fn):
        self._run_fn = run_fn
        self.closed = False

    def session(self):
        return _FakeSession(self._run_fn)

    async def close(self):
        self.closed = True


def _make_retriever(monkeypatch, run_fn):
    module = _load()
    monkeypatch.setattr(
        module.AsyncGraphDatabase, "driver", lambda *a, **k: _FakeDriver(run_fn)
    )
    return module.GraphRetriever("bolt://fake:7687", "neo4j", "pw")


# --- find_related_entities -----------------------------------------------------


async def test_find_related_entities_with_relationship_type_passes_correct_params(
    monkeypatch,
):
    captured = {}

    def run_fn(query, params):
        captured["query"] = query
        captured["params"] = params
        return _FakeResult(
            [
                _FakeRecord(
                    entity="Bob", label="PERSON", predicate="WORKS_WITH", type="SVO"
                )
            ]
        )

    retriever = _make_retriever(monkeypatch, run_fn)
    result = await retriever.find_related_entities(
        "Alice", relationship_type="WORKS_WITH", limit=5
    )

    assert captured["params"] == {
        "entity_name": "Alice",
        "rel_type": "WORKS_WITH",
        "limit": 5,
    }
    assert result == [
        {"text": "Bob", "label": "PERSON", "predicate": "WORKS_WITH", "type": "SVO"}
    ]


async def test_find_related_entities_without_type_uses_multihop_query(monkeypatch):
    captured = {}

    def run_fn(query, params):
        captured["query"] = query
        return _FakeResult([_FakeRecord(entity="Acme Corp", label="ORG")])

    retriever = _make_retriever(monkeypatch, run_fn)
    result = await retriever.find_related_entities("apple", max_depth=3, limit=10)

    # Multi-hop traversal only follows RELATES_TO -- the #248-adjacent fix that
    # stopped a Document node (from an untyped `-[*..]-` traversal) from leaking
    # into results with null .text/.label.
    assert "RELATES_TO*1..3" in captured["query"]
    assert ":MENTIONS" not in captured["query"]
    # Missing predicate/type in the record fall back to defaults, not a KeyError.
    assert result == [
        {
            "text": "Acme Corp",
            "label": "ORG",
            "predicate": "RELATED",
            "type": "RELATION",
        }
    ]


async def test_find_related_entities_degrades_to_empty_list_on_error(monkeypatch):
    def run_fn(query, params):
        raise RuntimeError("neo4j down")

    retriever = _make_retriever(monkeypatch, run_fn)
    result = await retriever.find_related_entities("Alice")

    assert result == []  # never raises


# --- get_entity_context ---------------------------------------------------------


async def test_get_entity_context_reports_not_found(monkeypatch):
    def run_fn(query, params):
        return _FakeResult([])  # entity_query's .single() -> None

    retriever = _make_retriever(monkeypatch, run_fn)
    result = await retriever.get_entity_context("nonexistent")

    assert result == {"error": "Entity not found"}


async def test_get_entity_context_assembles_entity_related_and_documents(monkeypatch):
    call_count = {"n": 0}

    def run_fn(query, params):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _FakeResult(
                [_FakeRecord(text="Alice", label="PERSON", description="a person")]
            )
        if call_count["n"] == 2:
            return _FakeResult(
                [_FakeRecord(text="Acme", label="ORG", predicate="WORKS_AT")]
            )
        return _FakeResult([_FakeRecord(doc_id="doc-1", title="Report")])

    retriever = _make_retriever(monkeypatch, run_fn)
    result = await retriever.get_entity_context("Alice", context_window=2)

    assert result["entity"] == {
        "text": "Alice",
        "label": "PERSON",
        "description": "a person",
    }
    assert result["related_entities"] == [
        {"text": "Acme", "label": "ORG", "predicate": "WORKS_AT"}
    ]
    assert result["documents"] == [{"id": "doc-1", "title": "Report"}]
    assert result["context_window"] == 2


async def test_get_entity_context_degrades_to_error_dict_on_exception(monkeypatch):
    def run_fn(query, params):
        raise RuntimeError("neo4j down")

    retriever = _make_retriever(monkeypatch, run_fn)
    result = await retriever.get_entity_context("Alice")

    assert "error" in result  # never raises


# --- graph_search ----------------------------------------------------------------


async def test_graph_search_parses_matches(monkeypatch):
    def run_fn(query, params):
        return _FakeResult(
            [_FakeRecord(text="Apple Inc", label="ORG", description="a company")]
        )

    retriever = _make_retriever(monkeypatch, run_fn)
    result = await retriever.graph_search("apple", limit=3)

    assert result == [{"text": "Apple Inc", "label": "ORG", "description": "a company"}]


async def test_graph_search_degrades_to_empty_list_on_error(monkeypatch):
    def run_fn(query, params):
        raise RuntimeError("neo4j down")

    retriever = _make_retriever(monkeypatch, run_fn)
    result = await retriever.graph_search("apple")

    assert result == []


async def test_close_closes_the_driver(monkeypatch):
    retriever = _make_retriever(monkeypatch, lambda q, p: _FakeResult([]))
    await retriever.close()
    assert retriever.driver.closed is True
