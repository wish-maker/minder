"""Unit tests for rag-pipeline's ConversationRepository ordering.

Regression cover for the conversational-RAG context bug: `get_history` must return
the MOST RECENT `max_turns` (not the first N of the whole conversation) and hand them
back oldest-first so `build_context` reads as a chronological Q/A window.

The module imports only stdlib (json/logging/datetime), so it loads by path — no
FastAPI app or DB driver needed; a tiny fake pool simulates asyncpg's
`ORDER BY timestamp DESC LIMIT $3` semantics.

Also covers `__init__`/`store_turn`/`clear_conversation`/`cleanup_expired`, which had
zero direct tests (only `get_history`/`build_context`'s ordering was locked down) --
their validation guards and the "any DB exception becomes a RuntimeError, never a raw
driver exception" wrapping pattern were entirely unexercised.
"""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "repositories"
    / "conversation_repository.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("conversation_repository_uut", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cr = _load()
ConversationRepository = cr.ConversationRepository


class _FakeConn:
    """Simulates a single asyncpg connection over an in-memory turn list."""

    def __init__(self, turns, execute_result="", raises=None):
        self._turns = turns
        self.last_query = ""
        self.execute_calls = []
        self._execute_result = execute_result
        self._raises = raises

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def fetch(self, query, user_id, conversation_id, max_turns):
        self.last_query = query
        rows = [
            t
            for t in self._turns
            if t["user_id"] == user_id and t["conversation_id"] == conversation_id
        ]
        reverse = "DESC" in query.upper()
        rows = sorted(rows, key=lambda t: t["timestamp"], reverse=reverse)
        return [
            {
                "question": t["question"],
                "answer": t["answer"],
                "timestamp": t["timestamp"],
                "metadata": json.dumps(t.get("metadata", {})),
            }
            for t in rows[:max_turns]
        ]

    async def execute(self, query, *params):
        if self._raises:
            raise self._raises
        self.last_query = query
        self.execute_calls.append(params)
        return self._execute_result


class _FakePool:
    def __init__(self, turns=None, execute_result="", raises=None):
        self._conn = _FakeConn(
            turns or [], execute_result=execute_result, raises=raises
        )

    def acquire(self):
        return self._conn


def _mk_turns(n):
    # timestamps strictly increasing: turn i is older than turn i+1
    return [
        {
            "user_id": "u",
            "conversation_id": "c",
            "question": f"q{i}",
            "answer": f"a{i}",
            "timestamp": i,
            "metadata": {"i": i},
        }
        for i in range(n)
    ]


def test_get_history_returns_most_recent_turns_oldest_first():
    pool = _FakePool(_mk_turns(10))
    repo = ConversationRepository(pool)
    history = asyncio.run(repo.get_history("u", "c", max_turns=3))

    # The 3 MOST RECENT turns (q7,q8,q9) — NOT the first 3 (q0,q1,q2) —
    # returned oldest-first.
    assert [t["question"] for t in history] == ["q7", "q8", "q9"]
    # Query must select newest-first so LIMIT keeps the recent tail.
    assert "DESC" in pool._conn.last_query.upper()


def test_get_history_shorter_than_window_returns_all_chronological():
    pool = _FakePool(_mk_turns(2))
    repo = ConversationRepository(pool)
    history = asyncio.run(repo.get_history("u", "c", max_turns=5))
    assert [t["question"] for t in history] == ["q0", "q1"]


def test_build_context_uses_recent_turns_in_order():
    pool = _FakePool(_mk_turns(10))
    repo = ConversationRepository(pool)
    ctx = asyncio.run(repo.build_context("u", "c", max_turns=2))
    assert ctx == "Q: q8\nA: a8\nQ: q9\nA: a9"


def test_build_context_empty_conversation_is_blank():
    pool = _FakePool([])
    repo = ConversationRepository(pool)
    assert asyncio.run(repo.build_context("u", "c", max_turns=3)) == ""


class TestInit:
    def test_rejects_a_none_pool(self):
        with pytest.raises(ValueError, match="db_pool cannot be None"):
            ConversationRepository(None)

    def test_rejects_a_non_positive_ttl(self):
        with pytest.raises(ValueError, match="default_ttl_days must be positive"):
            ConversationRepository(_FakePool(), default_ttl_days=0)


class TestStoreTurn:
    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(user_id="", conversation_id="c", question="q", answer="a"),
            dict(user_id="u", conversation_id="", question="q", answer="a"),
            dict(user_id="u", conversation_id="c", question="", answer="a"),
            dict(user_id="u", conversation_id="c", question="q", answer=""),
        ],
    )
    def test_rejects_empty_required_fields(self, kwargs):
        repo = ConversationRepository(_FakePool())
        with pytest.raises(ValueError):
            asyncio.run(repo.store_turn(**kwargs))

    def test_stores_the_turn_and_returns_true(self):
        pool = _FakePool()
        repo = ConversationRepository(pool)
        stored = asyncio.run(repo.store_turn("u", "c", "q", "a", metadata={"k": "v"}))
        assert stored is True
        [params] = pool._conn.execute_calls
        assert params[0] == "u"
        assert params[1] == "c"
        assert params[2] == "q"
        assert params[3] == "a"
        assert json.loads(params[5]) == {"k": "v"}

    def test_defaults_metadata_to_an_empty_object(self):
        pool = _FakePool()
        repo = ConversationRepository(pool)
        asyncio.run(repo.store_turn("u", "c", "q", "a"))
        [params] = pool._conn.execute_calls
        assert json.loads(params[5]) == {}

    def test_wraps_a_database_failure_as_runtimeerror(self):
        pool = _FakePool(raises=ConnectionError("db down"))
        repo = ConversationRepository(pool)
        with pytest.raises(RuntimeError, match="Database operation failed"):
            asyncio.run(repo.store_turn("u", "c", "q", "a"))


class TestGetHistoryValidation:
    def test_rejects_empty_user_id(self):
        repo = ConversationRepository(_FakePool())
        with pytest.raises(ValueError, match="user_id cannot be empty"):
            asyncio.run(repo.get_history("", "c"))

    def test_rejects_empty_conversation_id(self):
        repo = ConversationRepository(_FakePool())
        with pytest.raises(ValueError, match="conversation_id cannot be empty"):
            asyncio.run(repo.get_history("u", ""))

    def test_rejects_non_positive_max_turns(self):
        repo = ConversationRepository(_FakePool())
        with pytest.raises(ValueError, match="max_turns must be positive"):
            asyncio.run(repo.get_history("u", "c", max_turns=0))

    def test_wraps_a_database_failure_as_runtimeerror(self):
        pool = _FakePool(raises=ConnectionError("db down"))
        repo = ConversationRepository(pool)

        # get_history's failure path is on the fetch(), not execute() -- reuse
        # the same raising fake by having fetch also raise via a tiny subclass.
        async def boom(*a, **k):
            raise ConnectionError("db down")

        pool._conn.fetch = boom
        with pytest.raises(RuntimeError, match="Database operation failed"):
            asyncio.run(repo.get_history("u", "c"))


class TestClearConversation:
    def test_rejects_empty_user_id(self):
        repo = ConversationRepository(_FakePool())
        with pytest.raises(ValueError, match="user_id cannot be empty"):
            asyncio.run(repo.clear_conversation("", "c"))

    def test_rejects_empty_conversation_id(self):
        repo = ConversationRepository(_FakePool())
        with pytest.raises(ValueError, match="conversation_id cannot be empty"):
            asyncio.run(repo.clear_conversation("u", ""))

    def test_deletes_and_returns_true(self):
        pool = _FakePool()
        repo = ConversationRepository(pool)
        cleared = asyncio.run(repo.clear_conversation("u", "c"))
        assert cleared is True
        [params] = pool._conn.execute_calls
        assert params == ("u", "c")
        assert "DELETE" in pool._conn.last_query.upper()

    def test_wraps_a_database_failure_as_runtimeerror(self):
        pool = _FakePool(raises=ConnectionError("db down"))
        repo = ConversationRepository(pool)
        with pytest.raises(RuntimeError, match="Database operation failed"):
            asyncio.run(repo.clear_conversation("u", "c"))


class TestCleanupExpired:
    def test_parses_the_deleted_row_count_from_the_execute_result(self):
        pool = _FakePool(execute_result="DELETE 7")
        repo = ConversationRepository(pool)
        assert asyncio.run(repo.cleanup_expired()) == 7

    def test_empty_result_string_is_zero_deleted(self):
        pool = _FakePool(execute_result="")
        repo = ConversationRepository(pool)
        assert asyncio.run(repo.cleanup_expired()) == 0

    def test_passes_the_configured_ttl_as_the_interval_multiplier(self):
        pool = _FakePool(execute_result="DELETE 0")
        repo = ConversationRepository(pool, default_ttl_days=30)
        asyncio.run(repo.cleanup_expired())
        [params] = pool._conn.execute_calls
        assert params == (30,)

    def test_wraps_a_database_failure_as_runtimeerror(self):
        pool = _FakePool(raises=ConnectionError("db down"))
        repo = ConversationRepository(pool)
        with pytest.raises(RuntimeError, match="Database operation failed"):
            asyncio.run(repo.cleanup_expired())
