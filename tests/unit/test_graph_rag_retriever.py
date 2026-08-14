"""Unit tests for graph-rag's core/graph_retriever.py and core/graph_constructor.py.

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
clearing needed beyond a straightforward fresh import). `_load()` is called
FRESH inside each test (not once at module scope) specifically so a second
independent module under the same service's `core` package -- graph_constructor,
added below -- can share this one fresh-import site instead of each owning its
own: this session's own precedent (documented in
test_internal_write_endpoints_require_auth.py) is that a SECOND independent
module-level fresh-import site for the same service crashes the whole pytest
run -- confirmed live while adding the graph_constructor tests below.
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


def _load_constructor():
    """Same fresh-import as _load(), for core.graph_constructor -- call sites
    for both must each evict+reimport "core" themselves since either can run
    in any order relative to the other across this file's tests."""
    if str(_SERVICE_DIR) not in sys.path:
        sys.path.insert(0, str(_SERVICE_DIR))
    for stale in list(sys.modules):
        if stale == "core" or stale.startswith("core."):
            del sys.modules[stale]
    import importlib

    return importlib.import_module("core.graph_constructor")


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


# --- core/graph_constructor.py: create_document_node -------------------------
#
# Found in a background audit: create_document_node's MERGE only had an
# ON CREATE SET clause, never ON MATCH SET. The route docstring calls
# re-POSTing the same document_id an "upsert," and entities/relationships
# elsewhere in graph_constructor.py DO have ON MATCH SET -- but the Document
# node itself didn't, so once created, its title/source/metadata were frozen
# forever regardless of what a later re-ingest sent.


class _FakeConstructorResult:
    async def single(self):
        return {"d": "unused"}  # any truthy value -- just checked for not-None


class _FakeConstructorSession:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return _FakeConstructorResult()


class _FakeConstructorDriver:
    def __init__(self):
        self.fake_session = _FakeConstructorSession()

    def session(self):
        return self.fake_session


def _make_constructor(monkeypatch):
    module = _load_constructor()
    monkeypatch.setattr(
        module.AsyncGraphDatabase,
        "driver",
        lambda *a, **k: _FakeConstructorDriver(),
    )
    return module.KnowledgeGraphConstructor("bolt://fake:7687", "neo4j", "pw")


async def test_create_document_node_query_includes_on_match_set(monkeypatch):
    constructor = _make_constructor(monkeypatch)
    ok = await constructor.create_document_node(
        document_id="doc-1", title="Original Title", source="upload"
    )
    assert ok is True

    query, kwargs = constructor.driver.fake_session.calls[0]
    assert "ON MATCH SET" in query
    assert "d.title = $title" in query.split("ON MATCH SET")[1]
    assert kwargs["title"] == "Original Title"


async def test_reingest_sends_the_new_title_as_the_on_match_value(monkeypatch):
    """Two calls for the same document_id -- the second must carry the NEW
    title as a bound parameter the ON MATCH SET clause can apply."""
    constructor = _make_constructor(monkeypatch)
    await constructor.create_document_node(document_id="doc-1", title="Draft")
    await constructor.create_document_node(document_id="doc-1", title="Final Title")

    calls = constructor.driver.fake_session.calls
    assert len(calls) == 2
    assert calls[1][1]["title"] == "Final Title"


# --- core/graph_constructor.py: delete_document -------------------------------
#
# Found in the same audit: the three delete statements (RELATES_TO edges,
# DETACH DELETE the Document, then a global orphan scan) each ran as their own
# auto-commit statement, not one transaction -- a concurrent construct-graph
# call could MERGE a fresh edge onto a momentarily-orphaned entity between the
# document delete and the orphan scan, then have that entity deleted out from
# under it a moment later. The orphan scan was also unscoped -- `MATCH
# (e:Entity) WHERE NOT (e)--() DELETE e` deletes ANY orphaned entity anywhere
# in the graph, not just ones freed by this document's deletion.


class _FakeTxResult:
    def __init__(self, records=None, relationships_deleted=0, nodes_deleted=0):
        from types import SimpleNamespace

        self._records = list(records or [])
        self._counters = SimpleNamespace(
            relationships_deleted=relationships_deleted, nodes_deleted=nodes_deleted
        )

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        for r in self._records:
            yield r

    async def consume(self):
        from types import SimpleNamespace

        return SimpleNamespace(counters=self._counters)


class _FakeDeleteTx:
    """Routes on query text. `orphan_map` maps (text, label) -> nodes_deleted
    for the per-entity orphan-check query."""

    def __init__(self, mentioned, rels_deleted, docs_deleted, orphan_map):
        self.mentioned = mentioned
        self.rels_deleted = rels_deleted
        self.docs_deleted = docs_deleted
        self.orphan_map = orphan_map
        self.entity_orphan_check_calls = []

    async def run(self, query, **kwargs):
        if "MENTIONS" in query:
            return _FakeTxResult(
                records=[{"text": t, "label": lbl} for t, lbl in self.mentioned]
            )
        if "RELATES_TO" in query:
            return _FakeTxResult(relationships_deleted=self.rels_deleted)
        if "DETACH DELETE d" in query:
            return _FakeTxResult(nodes_deleted=self.docs_deleted)
        # Per-entity orphan-check/delete -- the scoped replacement for the old
        # global `MATCH (e:Entity) WHERE NOT (e)--() DELETE e` scan.
        key = (kwargs.get("text"), kwargs.get("label"))
        self.entity_orphan_check_calls.append(key)
        return _FakeTxResult(nodes_deleted=self.orphan_map.get(key, 0))


class _FakeDeleteSession:
    def __init__(self, tx):
        self._tx = tx
        self.execute_write_called = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute_write(self, fn):
        self.execute_write_called = True
        return await fn(self._tx)


class _FakeDeleteDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


def _make_constructor_for_delete(
    monkeypatch, mentioned, rels_deleted, docs_deleted, orphan_map
):
    module = _load_constructor()
    tx = _FakeDeleteTx(mentioned, rels_deleted, docs_deleted, orphan_map)
    session = _FakeDeleteSession(tx)
    monkeypatch.setattr(
        module.AsyncGraphDatabase,
        "driver",
        lambda *a, **k: _FakeDeleteDriver(session),
    )
    constructor = module.KnowledgeGraphConstructor("bolt://fake:7687", "neo4j", "pw")
    return constructor, tx, session


async def test_delete_document_runs_in_a_single_transaction(monkeypatch):
    constructor, tx, session = _make_constructor_for_delete(
        monkeypatch, mentioned=[], rels_deleted=0, docs_deleted=1, orphan_map={}
    )
    await constructor.delete_document("doc-1")
    assert session.execute_write_called is True


async def test_delete_document_only_checks_entities_this_document_touched(monkeypatch):
    """The orphan check must be scoped to entities this document actually
    MENTIONS, not a global scan that would also re-check (and possibly
    delete) unrelated orphaned entities elsewhere in the graph."""
    mentioned = [("Alice", "PERSON"), ("Acme Corp", "ORG")]
    constructor, tx, session = _make_constructor_for_delete(
        monkeypatch,
        mentioned=mentioned,
        rels_deleted=2,
        docs_deleted=1,
        orphan_map={("Alice", "PERSON"): 1, ("Acme Corp", "ORG"): 0},
    )

    result = await constructor.delete_document("doc-1")

    assert set(tx.entity_orphan_check_calls) == set(mentioned)
    assert result == {
        "document_deleted": 1,
        "relationships_deleted": 2,
        "orphan_entities_deleted": 1,
    }


async def test_delete_document_with_no_mentioned_entities_checks_nothing(monkeypatch):
    constructor, tx, session = _make_constructor_for_delete(
        monkeypatch, mentioned=[], rels_deleted=0, docs_deleted=1, orphan_map={}
    )
    result = await constructor.delete_document("doc-1")

    assert tx.entity_orphan_check_calls == []
    assert result["orphan_entities_deleted"] == 0
