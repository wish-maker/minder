"""Unit tests for rag-pipeline's ConversationRepository ordering.

Regression cover for the conversational-RAG context bug: `get_history` must return
the MOST RECENT `max_turns` (not the first N of the whole conversation) and hand them
back oldest-first so `build_context` reads as a chronological Q/A window.

The module imports only stdlib (json/logging/datetime), so it loads by path — no
FastAPI app or DB driver needed; a tiny fake pool simulates asyncpg's
`ORDER BY timestamp DESC LIMIT $3` semantics.
"""

import asyncio
import importlib.util
import json
from pathlib import Path

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

    def __init__(self, turns):
        self._turns = turns
        self.last_query = ""

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


class _FakePool:
    def __init__(self, turns):
        self._conn = _FakeConn(turns)

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
