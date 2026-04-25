"""
database.py - SQLAlchemy Async Database Setup
Provides async database connectivity with declarative models.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import Column, String, Integer, DateTime, Text, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
import logging
from config import settings

logger = logging.getLogger(__name__)

# ── SQLAlchemy Setup ──────────────────────────────────────────────────────────

DATABASE_URL = settings.DATABASE_URL

# Create async engine
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    **(
        {}
        if DATABASE_URL.startswith("sqlite")
        else {"pool_size": 10, "max_overflow": 20}
    ),
)

# Async session factory
AsyncSessionFactory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


# ── Models ────────────────────────────────────────────────────────────────────

class FileMetadata(Base):
    """Persistent file records (one row per uploaded document)."""
    __tablename__ = "file_metadata"

    file_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, default="anonymous", index=True)
    filename = Column(String, nullable=False, index=True)
    file_size = Column(Integer, nullable=False)  # bytes
    upload_date = Column(DateTime(timezone=True), nullable=False)
    collection_name = Column(String, nullable=False, default="company-documents")
    pages = Column(Integer, default=0)
    chunks = Column(Integer, default=0)
    status = Column(String, default="ready")  # ready | indexing | error
    error_message = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "file_id": self.file_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "upload_date": self.upload_date.isoformat() if self.upload_date else None,
            "collection_name": self.collection_name,
            "pages": self.pages,
            "chunks": self.chunks,
            "status": self.status,
            "error_message": self.error_message,
        }


class ChatHistory(Base):
    """Conversation messages — supports multiple sessions."""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, default="anonymous", index=True)
    session_id = Column(String, nullable=False, index=True)
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_message": self.user_message,
            "ai_response": self.ai_response,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ── Lifecycle Helpers ─────────────────────────────────────────────────────────

@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session (auto-commit/rollback on exit)."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables if they don't exist (call at app startup)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_legacy_columns(conn)
    logger.info("Database tables initialized successfully")


async def close_db() -> None:
    """Dispose engine connections (call at app shutdown)."""
    await engine.dispose()
    logger.info("Database connections closed")


async def _ensure_legacy_columns(conn) -> None:
    """Add newer columns/indexes to legacy databases created before those fields existed."""

    def has_column(sync_conn, table_name: str, column_name: str) -> bool:
        inspector = inspect(sync_conn)
        return column_name in {column["name"] for column in inspector.get_columns(table_name)}

    if not await conn.run_sync(has_column, "file_metadata", "user_id"):
        await conn.execute(
            text("ALTER TABLE file_metadata ADD COLUMN user_id VARCHAR NOT NULL DEFAULT 'anonymous'")
        )

    if not await conn.run_sync(has_column, "chat_history", "user_id"):
        await conn.execute(
            text("ALTER TABLE chat_history ADD COLUMN user_id VARCHAR NOT NULL DEFAULT 'anonymous'")
        )

    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_file_metadata_user_id ON file_metadata (user_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_history_user_id ON chat_history (user_id)"))
