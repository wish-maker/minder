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


class _FakeTransaction:
    """No-op async context manager standing in for asyncpg's conn.transaction()."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    """Simulates a single asyncpg connection over an in-memory turn list, an
    in-memory conversation_shares mapping, and an in-memory conversation_owners
    mapping (conversation_id -> owner_user_id, first-write-wins -- #893)."""

    def __init__(self, turns, execute_result="", raises=None, shares=None, owners=None):
        self._turns = turns
        self._shares = dict(shares or {})
        self._owners = dict(owners or {})
        self.last_query = ""
        self.execute_calls = []
        self._execute_result = execute_result
        self._raises = raises

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return _FakeTransaction()

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

    async def fetchrow(self, query, *params):
        self.last_query = query
        if self._raises:
            raise self._raises
        if "conversation_shares" in query:
            (conversation_id,) = params
            owner = self._shares.get(conversation_id)
            return {"owner_user_id": owner} if owner is not None else None
        if "conversation_owners" in query:
            (conversation_id,) = params
            owner = self._owners.get(conversation_id)
            return {"owner_user_id": owner} if owner is not None else None
        # is_owner's backward-compat fallback: earliest conversation_turns row.
        (conversation_id,) = params
        matches = sorted(
            (t for t in self._turns if t["conversation_id"] == conversation_id),
            key=lambda t: t["timestamp"],
        )
        return {"owner_user_id": matches[0]["user_id"]} if matches else None

    async def execute(self, query, *params):
        if self._raises:
            raise self._raises
        self.last_query = query
        self.execute_calls.append(params)
        if "INSERT INTO conversation_shares" in query:
            conversation_id, owner_user_id = params
            self._shares.setdefault(conversation_id, owner_user_id)
        elif "INSERT INTO conversation_owners" in query:
            conversation_id, owner_user_id = params
            self._owners.setdefault(conversation_id, owner_user_id)
        elif "INSERT INTO conversation_turns" in query:
            user_id, conversation_id, question, answer, timestamp, metadata = params
            self._turns.append(
                {
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "question": question,
                    "answer": answer,
                    "timestamp": timestamp,
                    "metadata": json.loads(metadata),
                }
            )
        return self._execute_result


class _FakePool:
    def __init__(
        self, turns=None, execute_result="", raises=None, shares=None, owners=None
    ):
        self._conn = _FakeConn(
            turns or [],
            execute_result=execute_result,
            raises=raises,
            shares=shares,
            owners=owners,
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
        # store_turn now also records first-ownership (#893) -- the turn
        # insert is the second of the two execute() calls.
        _owner_params, turn_params = pool._conn.execute_calls
        assert turn_params[0] == "u"
        assert turn_params[1] == "c"
        assert turn_params[2] == "q"
        assert turn_params[3] == "a"
        assert json.loads(turn_params[5]) == {"k": "v"}

    def test_records_first_ownership_alongside_the_turn(self):
        pool = _FakePool()
        repo = ConversationRepository(pool)
        asyncio.run(repo.store_turn("u", "c", "q", "a"))
        assert pool._conn._owners == {"c": "u"}

    def test_defaults_metadata_to_an_empty_object(self):
        pool = _FakePool()
        repo = ConversationRepository(pool)
        asyncio.run(repo.store_turn("u", "c", "q", "a"))
        _owner_params, turn_params = pool._conn.execute_calls
        assert json.loads(turn_params[5]) == {}

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


class TestSharing:
    """#875: conversations are per-user by default -- these cover the explicit
    opt-in that lets a second user continue one anyway."""

    def test_is_owner_true_when_user_has_a_turn_in_this_conversation(self):
        pool = _FakePool(_mk_turns(1))  # user_id="u", conversation_id="c"
        repo = ConversationRepository(pool)
        assert asyncio.run(repo.is_owner("u", "c")) is True

    def test_is_owner_false_for_a_different_user(self):
        pool = _FakePool(_mk_turns(1))
        repo = ConversationRepository(pool)
        assert asyncio.run(repo.is_owner("someone-else", "c")) is False

    def test_is_owner_false_for_empty_ids(self):
        pool = _FakePool(_mk_turns(1))
        repo = ConversationRepository(pool)
        assert asyncio.run(repo.is_owner("", "c")) is False
        assert asyncio.run(repo.is_owner("u", "")) is False

    def test_share_conversation_by_the_owner_succeeds(self):
        pool = _FakePool(_mk_turns(1))
        repo = ConversationRepository(pool)
        assert asyncio.run(repo.share_conversation("u", "c")) is True
        assert pool._conn._shares["c"] == "u"

    def test_share_conversation_by_a_non_owner_raises_permission_error(self):
        pool = _FakePool(_mk_turns(1))
        repo = ConversationRepository(pool)
        with pytest.raises(PermissionError):
            asyncio.run(repo.share_conversation("intruder", "c"))
        assert "c" not in pool._conn._shares

    def test_share_conversation_is_idempotent(self):
        pool = _FakePool(_mk_turns(1), shares={"c": "u"})
        repo = ConversationRepository(pool)
        # Already shared by "u" -- sharing again by the same owner is a no-op,
        # not an error.
        assert asyncio.run(repo.share_conversation("u", "c")) is True
        assert pool._conn._shares["c"] == "u"

    def test_share_conversation_rejects_empty_ids(self):
        repo = ConversationRepository(_FakePool())
        with pytest.raises(ValueError, match="user_id cannot be empty"):
            asyncio.run(repo.share_conversation("", "c"))
        with pytest.raises(ValueError, match="conversation_id cannot be empty"):
            asyncio.run(repo.share_conversation("u", ""))

    def test_resolve_storage_user_id_defaults_to_the_requester_when_unshared(self):
        pool = _FakePool()
        repo = ConversationRepository(pool)
        resolved = asyncio.run(repo.resolve_storage_user_id("alice", "conv1"))
        assert resolved == "alice"

    def test_resolve_storage_user_id_returns_the_owner_once_shared(self):
        pool = _FakePool(shares={"conv1": "alice"})
        repo = ConversationRepository(pool)
        # bob is asking, but conv1 was shared by alice -- his turns must land
        # in (and read from) alice's bucket so they both see the same history.
        resolved = asyncio.run(repo.resolve_storage_user_id("bob", "conv1"))
        assert resolved == "alice"

    def test_two_users_histories_stay_separate_until_shared(self):
        """The core #875 fix, end to end through the repository: alice's and
        bob's turns under the SAME conversation_id never mix unless alice
        explicitly shares it."""
        pool = _FakePool()
        repo = ConversationRepository(pool)

        alice_id = asyncio.run(
            repo.resolve_storage_user_id("alice", "conv-shared-test")
        )
        asyncio.run(
            repo.store_turn(alice_id, "conv-shared-test", "alice's question", "answer")
        )
        bob_id = asyncio.run(repo.resolve_storage_user_id("bob", "conv-shared-test"))
        asyncio.run(
            repo.store_turn(bob_id, "conv-shared-test", "bob's question", "answer")
        )

        # Unshared: alice's own lookup must not see bob's turn, and vice versa.
        alice_history = asyncio.run(repo.get_history("alice", "conv-shared-test"))
        assert [t["question"] for t in alice_history] == ["alice's question"]
        bob_history = asyncio.run(repo.get_history("bob", "conv-shared-test"))
        assert [t["question"] for t in bob_history] == ["bob's question"]

        # alice shares it; bob's turns from now on land in alice's bucket, and
        # he can see her (and now their shared) history.
        asyncio.run(repo.share_conversation("alice", "conv-shared-test"))
        bob_id_after_share = asyncio.run(
            repo.resolve_storage_user_id("bob", "conv-shared-test")
        )
        assert bob_id_after_share == "alice"
        asyncio.run(
            repo.store_turn(
                bob_id_after_share, "conv-shared-test", "bob's follow-up", "answer"
            )
        )
        shared_history = asyncio.run(repo.get_history("alice", "conv-shared-test"))
        assert [t["question"] for t in shared_history] == [
            "alice's question",
            "bob's follow-up",
        ]

    def test_a_later_user_reusing_the_same_conversation_id_cannot_hijack_ownership(
        self,
    ):
        """#893: alice starts conversation_id X first. bob later legitimately
        starts his OWN private thread under the same client-supplied id X
        (allowed, per-user-private-by-default). bob must NOT be able to claim
        ownership just because he also has a turn stored under X -- only
        alice, the true first-writer, may share it."""
        pool = _FakePool()
        repo = ConversationRepository(pool)

        asyncio.run(repo.store_turn("alice", "conv-X", "alice's first question", "a"))
        asyncio.run(repo.store_turn("bob", "conv-X", "bob's own question", "a"))

        assert asyncio.run(repo.is_owner("alice", "conv-X")) is True
        assert asyncio.run(repo.is_owner("bob", "conv-X")) is False

        with pytest.raises(PermissionError):
            asyncio.run(repo.share_conversation("bob", "conv-X"))
        assert "conv-X" not in pool._conn._shares

        assert asyncio.run(repo.share_conversation("alice", "conv-X")) is True
        assert pool._conn._shares["conv-X"] == "alice"

    def test_is_owner_falls_back_to_earliest_turn_when_no_owners_row_exists(self):
        """Pre-migration data: conversation_turns rows exist with no
        corresponding conversation_owners row yet (#893's backward-compat path)."""
        turns = [
            {
                "user_id": "alice",
                "conversation_id": "legacy-conv",
                "question": "q0",
                "answer": "a0",
                "timestamp": 0,
                "metadata": {},
            },
            {
                "user_id": "bob",
                "conversation_id": "legacy-conv",
                "question": "q1",
                "answer": "a1",
                "timestamp": 1,
                "metadata": {},
            },
        ]
        pool = _FakePool(turns)
        repo = ConversationRepository(pool)
        assert asyncio.run(repo.is_owner("alice", "legacy-conv")) is True
        assert asyncio.run(repo.is_owner("bob", "legacy-conv")) is False


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
