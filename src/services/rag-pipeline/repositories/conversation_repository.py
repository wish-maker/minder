"""
Conversation Repository

Data access layer for conversation history.
Provides conversation turn storage with PostgreSQL persistence.

This is a repository layer component for data access.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConversationRepository:
    """
    Conversation repository for data access

    Manages conversation history persistence with PostgreSQL.
    Provides storage and retrieval of conversation turns.

    Features:
    - PostgreSQL-backed persistence
    - JSON metadata storage
    - TTL-based expiration
    - Turn ordering maintained

    Attributes:
        db_pool: PostgreSQL connection pool
        default_ttl_days: Default TTL in days (default: 1)

    Example:
        >>> repo = ConversationRepository(db_pool)
        >>> repo.store_turn(user_id, conv_id, question, answer)
        >>> history = repo.get_history(user_id, conv_id, max_turns=5)
    """

    def __init__(self, db_pool: Any, default_ttl_days: int = 1):
        """
        Initialize conversation repository

        Args:
            db_pool: PostgreSQL connection pool
            default_ttl_days: Default TTL for conversations

        Raises:
            ValueError: If db_pool invalid or ttl invalid
        """
        if db_pool is None:
            raise ValueError("db_pool cannot be None")

        if default_ttl_days <= 0:
            raise ValueError(
                f"default_ttl_days must be positive, got {default_ttl_days}"
            )

        self.db_pool = db_pool
        self.default_ttl_days = default_ttl_days

        logger.info(
            f"✅ ConversationRepository initialized: ttl={default_ttl_days} days"
        )

    async def store_turn(
        self,
        user_id: str,
        conversation_id: str,
        question: str,
        answer: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Store conversation turn

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            question: User question
            answer: Assistant answer
            metadata: Optional metadata dict

        Returns:
            True if stored successfully

        Raises:
            ValueError: If required fields invalid
            RuntimeError: If database operation fails
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")

        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")

        if not question:
            raise ValueError("question cannot be empty")

        if not answer:
            raise ValueError("answer cannot be empty")

        # naive TIMESTAMP column → naive-UTC datetime object (was naive-LOCAL).
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
        metadata_json = json.dumps(metadata or {})

        try:
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    # #893: record the true first-writer of this conversation_id,
                    # atomically, at the moment of the first-ever turn stored under
                    # it -- ON CONFLICT DO NOTHING means whichever writer's insert
                    # lands first wins this row; every later writer's insert (e.g.
                    # a second user legitimately starting their own private thread
                    # under the same client-supplied id, #875) is a no-op that
                    # leaves the true first-writer recorded. is_owner() reads this
                    # instead of "has this user ever written here," which any
                    # later writer would also satisfy.
                    await conn.execute(
                        """
                        INSERT INTO conversation_owners (conversation_id, owner_user_id)
                        VALUES ($1, $2)
                        ON CONFLICT (conversation_id) DO NOTHING
                        """,
                        conversation_id,
                        user_id,
                    )
                    await conn.execute(
                        """
                        INSERT INTO conversation_turns (user_id, conversation_id, question, answer, timestamp, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        user_id,
                        conversation_id,
                        question,
                        answer,
                        timestamp,
                        metadata_json,
                    )

            logger.debug(f"💾 Stored conversation turn: {user_id}:{conversation_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to store conversation turn: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def get_history(
        self, user_id: str, conversation_id: str, max_turns: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            max_turns: Maximum number of turns to retrieve

        Returns:
            List of the ``max_turns`` MOST RECENT conversation turn dicts,
            returned oldest-first (chronological order).

        Raises:
            ValueError: If parameters invalid
            RuntimeError: If database operation fails
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")

        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")

        if max_turns <= 0:
            raise ValueError(f"max_turns must be positive, got {max_turns}")

        try:
            async with self.db_pool.acquire() as conn:
                # Take the most-recent `max_turns` (ORDER BY DESC + LIMIT), then
                # reverse below to hand them back oldest-first. A plain
                # `ORDER BY timestamp ASC LIMIT $3` keeps the FIRST N turns of the
                # whole conversation, so once it grows past max_turns the model
                # silently loses all recent context — the opposite of what a
                # short conversational window should do.
                rows = await conn.fetch(
                    """
                    SELECT question, answer, timestamp, metadata
                    FROM conversation_turns
                    WHERE user_id = $1 AND conversation_id = $2
                    ORDER BY timestamp DESC, id DESC
                    LIMIT $3
                    """,
                    user_id,
                    conversation_id,
                    max_turns,
                )

            turns = []
            for row in reversed(rows):
                turn = {
                    "question": row["question"],
                    "answer": row["answer"],
                    "timestamp": row["timestamp"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                }
                turns.append(turn)

            logger.debug(
                f"📖 Retrieved {len(turns)} conversation turns: {user_id}:{conversation_id}"
            )
            return turns

        except Exception as e:
            logger.error(f"❌ Failed to get conversation history: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def build_context(
        self, user_id: str, conversation_id: str, max_turns: int = 3
    ) -> str:
        """
        Build conversational context string

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            max_turns: Maximum turns to include

        Returns:
            Formatted context string

        Raises:
            ValueError: If parameters invalid
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")

        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")

        turns = await self.get_history(user_id, conversation_id, max_turns)

        if not turns:
            return ""

        context_parts = []
        for turn in turns[-max_turns:]:
            context_parts.append(f"Q: {turn['question']}")
            context_parts.append(f"A: {turn['answer']}")

        context_str = "\n".join(context_parts)
        logger.debug(f"🔄 Built conversation context: {len(turns)} turns")

        return context_str

    async def clear_conversation(self, user_id: str, conversation_id: str) -> bool:
        """
        Clear conversation history

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier

        Returns:
            True if cleared successfully

        Raises:
            ValueError: If parameters invalid
            RuntimeError: If database operation fails
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")

        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")

        try:
            async with self.db_pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        DELETE FROM conversation_turns
                        WHERE user_id = $1 AND conversation_id = $2
                        """,
                        user_id,
                        conversation_id,
                    )
                    # Reclaim the owner/share rows once the conversation_id has
                    # no turns left at all -- otherwise a cleared conversation
                    # keeps a stale owner row (inflating /mine's total, #940) and
                    # a stale share row silently redirects a later fresh turn to
                    # the old owner's bucket (resolve_storage_user_id). Guarded on
                    # "no turns remain" so clearing one user's private turns under
                    # a collided id doesn't drop another user's still-live thread.
                    # Mirrors cleanup_expired's reclamation, scoped to this id.
                    await conn.execute(
                        """
                        DELETE FROM conversation_shares
                        WHERE conversation_id = $1
                          AND NOT EXISTS (
                              SELECT 1 FROM conversation_turns
                              WHERE conversation_id = $1
                          )
                        """,
                        conversation_id,
                    )
                    await conn.execute(
                        """
                        DELETE FROM conversation_owners
                        WHERE conversation_id = $1
                          AND NOT EXISTS (
                              SELECT 1 FROM conversation_turns
                              WHERE conversation_id = $1
                          )
                        """,
                        conversation_id,
                    )

            logger.info(f"🗑️ Cleared conversation: {user_id}:{conversation_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to clear conversation: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def is_owner(self, user_id: str, conversation_id: str) -> bool:
        """Whether ``user_id`` is the TRUE first-writer of this conversation_id
        (#893) -- i.e. the one recorded in ``conversation_owners`` at the
        moment of the very first turn ever stored under it, not merely
        "has ever stored a turn here" (which a later, unrelated user who
        legitimately started their own private thread under the same
        client-supplied id would also satisfy -- see #875's per-user-private
        default). Used to gate ``share_conversation`` -- only the real owner
        may mark a conversation shared.

        Falls back to the earliest ``conversation_turns`` row's user_id when
        no ``conversation_owners`` row exists yet -- covers a conversation
        whose turns were stored before this table existed. Not race-prone:
        by the time anyone calls share, at least one turn already exists and
        conversation_turns is read-only here.
        """
        if not user_id or not conversation_id:
            return False
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT owner_user_id FROM conversation_owners WHERE conversation_id = $1",
                conversation_id,
            )
            if row is None:
                row = await conn.fetchrow(
                    """
                    SELECT user_id AS owner_user_id FROM conversation_turns
                    WHERE conversation_id = $1
                    ORDER BY timestamp ASC
                    LIMIT 1
                    """,
                    conversation_id,
                )
        return row is not None and row["owner_user_id"] == user_id

    async def list_owned_conversations(
        self, owner_user_id: str, limit: int = 20, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List conversations OWNED (first-written, per ``is_owner``) by
        ``owner_user_id``, most recently active first.

        Returns ``(items, total)`` where each item is
        ``{"conversation_id", "last_activity", "snippet"}`` (the most recent
        turn's question, for a picklist-style display) and ``total`` is the
        pre-slice count of this user's owned conversations.

        Deliberately scoped to ``conversation_owners.owner_user_id`` rather
        than ``conversation_turns.user_id`` -- the latter is the *storage*
        identity (which for a shared conversation is the owner's id
        regardless of who actually asked, per ``resolve_storage_user_id``),
        not "conversations this caller started." A participant in a
        conversation someone else shared with them will not see it here;
        this lists only what the caller themselves began.

        Raises:
            ValueError: If required fields invalid.
            RuntimeError: If database operation fails.
        """
        if not owner_user_id:
            raise ValueError("owner_user_id cannot be empty")
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")

        try:
            async with self.db_pool.acquire() as conn:
                # `total` must match the reachable item set exactly: count only
                # owner rows that still have a turn stored under the OWNER's own
                # id. Without the EXISTS guard, an owner row whose turns were
                # cleared/expired (or captured under a colliding id by another
                # user) inflates `total` past what the INNER LATERAL below can
                # ever return -> a short/empty last page while `total` insists
                # more exist (#940).
                total = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM conversation_owners co
                    WHERE co.owner_user_id = $1
                      AND EXISTS (
                          SELECT 1 FROM conversation_turns ct
                          WHERE ct.conversation_id = co.conversation_id
                            AND ct.user_id = co.owner_user_id
                      )
                    """,
                    owner_user_id,
                )
                # The LATERAL is scoped to `ct.user_id = co.owner_user_id`, NOT
                # conversation_id alone: conversation_id is client-supplied and
                # globally-namespaced, so a different user's private turn under
                # the same id must never surface as this owner's snippet (#937).
                # A shared conversation's turns are all stored under the owner id
                # (resolve_storage_user_id), so the owner still sees them.
                # `ct.id`/`co.conversation_id` tiebreakers make paging
                # deterministic when timestamps collide.
                rows = await conn.fetch(
                    """
                    SELECT co.conversation_id AS conversation_id,
                           latest.timestamp AS last_activity,
                           latest.question AS snippet
                    FROM conversation_owners co
                    JOIN LATERAL (
                        SELECT ct.question, ct.timestamp
                        FROM conversation_turns ct
                        WHERE ct.conversation_id = co.conversation_id
                          AND ct.user_id = co.owner_user_id
                        ORDER BY ct.timestamp DESC, ct.id DESC
                        LIMIT 1
                    ) latest ON TRUE
                    WHERE co.owner_user_id = $1
                    ORDER BY latest.timestamp DESC, co.conversation_id
                    LIMIT $2 OFFSET $3
                    """,
                    owner_user_id,
                    limit,
                    offset,
                )

            items = [
                {
                    "conversation_id": row["conversation_id"],
                    "last_activity": row["last_activity"],
                    "snippet": row["snippet"][:200],
                }
                for row in rows
            ]

            logger.debug(
                f"📖 Listed {len(items)}/{total} owned conversations for {owner_user_id}"
            )
            return items, int(total or 0)

        except Exception as e:
            logger.error(f"❌ Failed to list owned conversations: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def share_conversation(self, user_id: str, conversation_id: str) -> bool:
        """Mark a conversation as shared so any authenticated user can continue
        it (#875's optional half -- default scoping is per-user, this is the
        explicit opt-in). Only the actual owner (see ``is_owner``) may do this.

        Returns:
            True once shared (idempotent -- sharing an already-shared
            conversation is a no-op, not an error).

        Raises:
            PermissionError: ``user_id`` does not own ``conversation_id``.
            ValueError: If required fields invalid.
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")
        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")

        if not await self.is_owner(user_id, conversation_id):
            raise PermissionError(
                f"user {user_id!r} does not own conversation {conversation_id!r}"
            )

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO conversation_shares (conversation_id, owner_user_id)
                    VALUES ($1, $2)
                    ON CONFLICT (conversation_id) DO NOTHING
                    """,
                    conversation_id,
                    user_id,
                )
            logger.info(f"🔗 Shared conversation: {user_id}:{conversation_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to share conversation: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def resolve_storage_user_id(
        self, requesting_user_id: str, conversation_id: str
    ) -> str:
        """The actual user_id a turn should be read from / written to for this
        conversation_id (#875): the conversation's owner if it has been
        explicitly shared (so every participant's turns land in, and are read
        from, the same bucket), otherwise the requester's own identity
        (private, per-user history -- the default).
        """
        if not conversation_id:
            return requesting_user_id
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT owner_user_id FROM conversation_shares WHERE conversation_id = $1",
                conversation_id,
            )
        return row["owner_user_id"] if row is not None else requesting_user_id

    async def cleanup_expired(self) -> int:
        """
        Clean up expired conversations (older than TTL)

        Also drops any `conversation_owners`/`conversation_shares` row whose
        conversation_id no longer has a matching `conversation_turns` row
        (#893's first-owner/sharing tables would otherwise grow unbounded
        forever, one row pair per conversation ever started or shared, with
        nothing ever reclaiming them once that conversation's turns expire).

        Returns:
            Number of turns deleted

        Raises:
            RuntimeError: If database operation fails
        """
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM conversation_turns
                    WHERE timestamp < NOW() - INTERVAL '1 day' * $1
                    """,
                    self.default_ttl_days,
                )
                async with conn.transaction():
                    await conn.execute(
                        """
                        DELETE FROM conversation_shares
                        WHERE conversation_id NOT IN (
                            SELECT DISTINCT conversation_id FROM conversation_turns
                        )
                        """
                    )
                    await conn.execute(
                        """
                        DELETE FROM conversation_owners
                        WHERE conversation_id NOT IN (
                            SELECT DISTINCT conversation_id FROM conversation_turns
                        )
                        """
                    )

            # Parse result to get deleted count
            deleted_count = int(result.split()[-1]) if result else 0

            logger.info(f"🗑️ Cleaned up {deleted_count} expired conversation turns")
            return deleted_count

        except Exception as e:
            logger.error(f"❌ Failed to cleanup expired conversations: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")
