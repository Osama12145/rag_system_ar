"""
database.py - SQLAlchemy Async Database Setup
Provides async PostgreSQL connectivity with declarative models.
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
import logging

logger = logging.getLogger(__name__)

# ── SQLAlchemy Setup ──────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/chatbot_db")

# Create async engine
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "False").lower() == "true",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
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
    logger.info("Database tables initialized successfully")


async def close_db() -> None:
    """Dispose engine connections (call at app shutdown)."""
    await engine.dispose()
    logger.info("Database connections closed")
