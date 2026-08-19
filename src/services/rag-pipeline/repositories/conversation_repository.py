"""
Conversation Repository

Data access layer for conversation history.
Provides conversation turn storage with PostgreSQL persistence.

This is a repository layer component for data access.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
                    ORDER BY timestamp DESC
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
                await conn.execute(
                    """
                    DELETE FROM conversation_turns
                    WHERE user_id = $1 AND conversation_id = $2
                    """,
                    user_id,
                    conversation_id,
                )

            logger.info(f"🗑️ Cleared conversation: {user_id}:{conversation_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to clear conversation: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")

    async def is_owner(self, user_id: str, conversation_id: str) -> bool:
        """Whether ``user_id`` has ever stored a turn under this conversation_id
        directly (i.e. asked the first/any question in it under their own
        identity, not via a share). Used to gate ``share_conversation`` -- only
        someone who actually owns a conversation can mark it shared (#875)."""
        if not user_id or not conversation_id:
            return False
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM conversation_turns
                WHERE user_id = $1 AND conversation_id = $2
                LIMIT 1
                """,
                user_id,
                conversation_id,
            )
        return row is not None

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

            # Parse result to get deleted count
            deleted_count = int(result.split()[-1]) if result else 0

            logger.info(f"🗑️ Cleaned up {deleted_count} expired conversation turns")
            return deleted_count

        except Exception as e:
            logger.error(f"❌ Failed to cleanup expired conversations: {e}")
            raise RuntimeError(f"Database operation failed: {str(e)}")
