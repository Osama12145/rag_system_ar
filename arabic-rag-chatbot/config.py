"""
config.py - Configuration Management
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """
    Centralized settings management using Pydantic.
    Values are loaded from .env file automatically.
    """

    # LangSmith Observability
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: str = "company-intelligence-rag"

    # API Keys (required)
    OPENROUTER_API_KEY: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None

    # Qdrant Vector DB
    # Use "local" for file-based local mode (no Docker needed) — overridden by .env
    # In Coolify, use the internal service URL — default below
    QDRANT_URL: str = "local"
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION_NAME: str = "company-documents"
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_API_BASE: str = "https://openrouter.ai/api/v1"
    EMBEDDING_DIMENSIONS: int = 1024

    # PostgreSQL Database (via asyncpg driver)
    # Format: postgresql+asyncpg://user:password@host:port/dbname
    # In Coolify, DATABASE_URL is injected by platform
    DATABASE_URL: str = "sqlite+aiosqlite:///./app_data.db"

    # Startup behavior
    RESTORE_CHAT_HISTORY_ON_STARTUP: bool = False

    # LLM Configuration
    LLM_MODEL: str = "openai/gpt-oss-120b"
    TEMPERATURE: float = 0.1
    MAX_TOKENS: int = 1500

    # RAG Configuration
    TOP_K_DOCUMENTS: int = 5
    SIMILARITY_THRESHOLD: float = 0.2

    # Chunking Strategy
    CHUNK_SIZE: int = 1200
    CHUNK_OVERLAP: int = 150

    # File-targeted retrieval tuning
    FILE_CONTEXT_LEAD_CHUNKS: int = 6
    FILE_CONTEXT_TOP_K: int = 8
    FILE_CONTEXT_MAX_CHARS: int = 18000

    # OCR Configuration
    OCR_PROVIDER: str = "excai"
    EXCAI_OCR_API_KEY: Optional[str] = None
    EXCAI_OCR_BASE_URL: str = "https://api-ocr.excai.ai/api/v1"
    EXCAI_OCR_TIMEOUT_SECONDS: int = 180
    OCR_REMOTE_SCANNED_RATIO_THRESHOLD: float = 0.5
    OCR_REMOTE_MIN_NATIVE_CHARS: int = 400

    # System Prompt (base — language is injected at request time)
    SYSTEM_PROMPT: str = (
        "You are a helpful company assistant. "
        "Answer questions ONLY based on the provided company documents. "
        "If you can't find the answer, say: "
        "'I couldn't find information about this topic in the company documents.' "
        "NEVER make up information. Be concise and professional."
    )

    # App Settings
    APP_NAME: str = "Company Intelligence RAG"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # CORS — comma-separated list of allowed frontend origins
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()

# Initialize LangSmith tracing environment variables if enabled
if settings.LANGCHAIN_TRACING_V2.lower() == "true" and settings.LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
