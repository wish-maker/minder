"""
Repositories Package

This package contains data access layer components that provide
CRUD operations with PostgreSQL persistence.
"""

from .conversation_repository import ConversationRepository

__all__ = [
    "ConversationRepository",
]
