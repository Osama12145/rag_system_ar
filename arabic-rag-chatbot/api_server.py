"""
api_server.py - FastAPI Backend with Dual-Database Persistence
PostgreSQL (SQLAlchemy) for metadata + Qdrant for vector search.
Run with: uvicorn api_server:app --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, File, UploadFile, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import text  # SQLAlchemy 2.0: required for raw SQL strings

from rag_pipeline import RAGChatbot
from vector_store import VectorStoreManager
from document_processor import DocumentProcessor
from config import settings
from database import (
    Base,
    FileMetadata,
    ChatHistory,
    get_async_session,
    init_db,
    close_db,
)
from langchain_core.messages import HumanMessage, AIMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
vs_manager: Optional[VectorStoreManager] = None
chatbot: Optional[RAGChatbot] = None


# ============= Lifespan (Startup / Shutdown) =============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up application resources."""
    global vs_manager, chatbot
    logger.info("Starting application...")

    # ── Initialize PostgreSQL tables ──
    try:
        await init_db()
        logger.info("PostgreSQL tables initialized")
    except Exception as e:
        logger.error(f"Database init error: {e}")
        # Continue — Qdrant may still work

    # ── Initialize Vector Store & Chatbot ──
    try:
        vs_manager = VectorStoreManager()
        chatbot = RAGChatbot(vs_manager)

        # Restore conversation from DB if any exists
        await restore_conversation()
        logger.info("Application initialized successfully (vector store + chatbot)")
    except Exception as e:
        logger.error(f"Startup error: {e}")

    yield

    # ── Cleanup ──
    logger.info("Shutting down application...")
    await close_db()
    logger.info("Application shutdown complete")


# ── Helper: Restore recent conversation from DB ─────────────────────────────

async def restore_conversation():
    """Load most recent chat history into memory on startup."""
    if not chatbot:
        return
    try:
        async with get_async_session() as session:
            result = await session.execute(
                text("""
                SELECT user_message, ai_response
                FROM chat_history
                ORDER BY timestamp DESC
                LIMIT 20
                """)
            )
            rows = result.fetchall()
            # Reverse to chronological order
            for user_msg, ai_msg in reversed(rows):
                chatbot.conversation_history.append(HumanMessage(content=user_msg))
                chatbot.conversation_history.append(AIMessage(content=ai_msg))
            logger.info(f"Restored {len(rows)} conversation turns from database")
    except Exception as e:
        logger.warning(f"Could not restore conversation: {e}")


# ============= App =============

app = FastAPI(
    title="Company Intelligence RAG API",
    description="API for querying company documents via RAG (Retrieval-Augmented Generation)",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS — restricted to known frontend origins only
ALLOWED_ORIGINS = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


# ============= Pydantic Models =============

class ChatRequest(BaseModel):
    """Chat request payload (matches frontend structure)."""
    message: str = Field(default="", max_length=4000)
    query: Optional[str] = None  # Fallback
    sourceCheck: bool = True
    deepResearch: bool = False
    reasoning: bool = False
    language: str = "en"
    history: Optional[List[Dict[str, Any]]] = None
    sessionId: Optional[str] = None  # Optional client-provided session id

    @validator("message")
    def message_not_empty(cls, v, values):
        query = values.get("query") or ""
        if not v.strip() and not query.strip():
            raise ValueError("message or query must not be empty")
        return v


class DocumentRecord(BaseModel):
    """Single document metadata record returned to the frontend."""
    id: str
    name: str
    size: int
    pages: int
    chunks: int
    uploadedAt: str
    status: str  # "ready" | "indexing" | "error"


class DocumentUploadResponse(BaseModel):
    """Document upload response."""
    message: str
    file_id: str
    success: bool


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    initialized: bool
    total_vectors: Optional[int] = None
    db_connected: bool = False


# ============= Health Check =============

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check system health status (Qdrant + PostgreSQL)."""
    qdrant_ok = chatbot is not None
    db_ok = False

    # Check DB connectivity
    try:
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")

    try:
        stats = vs_manager.get_index_stats() if vs_manager else {}
        return HealthResponse(
            status="healthy" if qdrant_ok and db_ok else "degraded",
            initialized=chatbot is not None,
            total_vectors=stats.get("total_vectors"),
            db_connected=db_ok,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= Chat Endpoints =============

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Stream a response to the chatbot using chunked transfer.
    Optionally appends [CITATIONS]{...} at end of stream.
    Persists conversation to PostgreSQL.
    """
    if not chatbot:
        raise HTTPException(status_code=503, detail="Chatbot not initialized. Please wait...")

    try:
        user_msg = request.message.strip() if request.message.strip() else (request.query or "").strip()
        logger.info(f"New query [{request.language}]: {user_msg[:80]}")

        # Determine session ID (client-provided or new)
        session_id = request.sessionId or str(uuid.uuid4())

        generator = chatbot.stream_chat(
            user_query=user_msg,
            include_sources=request.sourceCheck,
            language=request.language,
            on_response_complete=lambda response: asyncio.create_task(
                save_chat_message(session_id, user_msg, response)
            ),
        )

        return StreamingResponse(generator, media_type="text/plain")

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def save_chat_message(session_id: str, user_message: str, ai_response: str):
    """Persist a chat exchange to PostgreSQL."""
    if not user_message and not ai_response:
        return
    try:
        async with get_async_session() as session:
            record = ChatHistory(
                session_id=session_id,
                user_message=user_message,
                ai_response=ai_response,
                timestamp=datetime.now(timezone.utc),
            )
            session.add(record)
            await session.commit()
            logger.debug(f"Saved chat message for session {session_id}")
    except Exception as e:
        logger.error(f"Failed to save chat history: {e}")


@app.get("/api/chat/history")
async def get_chat_history(session_id: Optional[str] = None):
    """
    Get conversation history.
    If session_id provided, return messages for that session.
    Otherwise return the most recent session.
    """
    try:
        async with get_async_session() as db:
            if session_id:
                stmt = text("""
                SELECT user_message, ai_response, timestamp
                FROM chat_history
                WHERE session_id = :sid
                ORDER BY timestamp ASC
    """)
                result = await db.execute(stmt, {"sid": session_id})
            else:
                # Get the most recent session_id
                sid_result = await db.execute(text("SELECT session_id FROM chat_history ORDER BY timestamp DESC LIMIT 1"))
                recent_sid = sid_result.scalar_one_or_none()
                if not recent_sid:
                    return {"history": [], "message_count": 0, "session_id": None}
                stmt = text("""
                SELECT user_message, ai_response, timestamp
                FROM chat_history
                WHERE session_id = :sid
                ORDER BY timestamp ASC
    """)
                result = await db.execute(stmt, {"sid": recent_sid})
                session_id = recent_sid

            rows = result.fetchall()
            history = [
                {"role": "user", "content": row[0], "timestamp": row[2].isoformat()}
                for row in rows
            ] + [
                {"role": "assistant", "content": row[1], "timestamp": row[2].isoformat()}
                for row in rows
            ]
            # Sort by timestamp
            history.sort(key=lambda x: x["timestamp"])

            return {
                "history": history,
                "message_count": len(rows),
                "session_id": session_id,
            }
    except Exception as e:
        logger.error(f"Chat history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/clear")
async def clear_history(session_id: Optional[str] = None):
    """
    Clear conversation history.
    If session_id provided, delete only that session.
    Otherwise delete the most recent session.
    """
    try:
        async with get_async_session() as db:
            if session_id:
                await db.execute(
                    text("DELETE FROM chat_history WHERE session_id = :sid"),
                    {"sid": session_id},
                )
            else:
                # Get most recent session_id and delete it
                sid_result = await db.execute(text("SELECT session_id FROM chat_history ORDER BY timestamp DESC LIMIT 1"))
                recent_sid = sid_result.scalar_one_or_none()
                if recent_sid:
                    await db.execute(
                        text("DELETE FROM chat_history WHERE session_id = :sid"),
                        {"sid": recent_sid},
                    )

            # Also clear in-memory history
            if chatbot:
                chatbot.clear_history()

            return {"message": "History cleared"}
    except Exception as e:
        logger.error(f"Clear history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Sessions Endpoint =============

@app.get("/api/sessions")
async def list_sessions():
    """
    Return distinct conversation sessions derived from chat_history table.
    """
    try:
        async with get_async_session() as db:
            result = await db.execute(
                text("""
                SELECT
                    session_id,
                    MAX(timestamp) as updated_at,
                    COUNT(*) as message_count,
                    MAX(user_message) as preview_text
                FROM chat_history
                GROUP BY session_id
                ORDER BY updated_at DESC
                LIMIT 20
                """)
            )
            rows = result.fetchall()
            sessions = [
                {
                    "id": row[0],
                    "title": (row[3] or "Session")[:60],
                    "preview": (row[3] or "Session")[:60],
                    "updatedAt": row[1].strftime("%Y-%m-%d") if row[1] else datetime.now().strftime("%Y-%m-%d"),
                    "messageCount": row[2],
                }
                for row in rows
            ]
            return {"sessions": sessions}
    except Exception as e:
        logger.error(f"List sessions error: {e}")
        return {"sessions": []}


# ============= Document Management =============

@app.get("/api/documents", response_model=List[DocumentRecord])
async def list_documents():
    """
    Return list of indexed documents from PostgreSQL file_metadata table.
    """
    try:
        async with get_async_session() as db:
            result = await db.execute(
                text("""
                SELECT file_id, filename, file_size, pages, chunks, upload_date, status
                FROM file_metadata
                ORDER BY upload_date DESC
                """)
            )
            rows = result.fetchall()
            docs: List[Dict[str, Any]] = []
            for row in rows:
                docs.append(
                    DocumentRecord(
                        id=row[0],
                        name=row[1],
                        size=row[2],
                        pages=row[3] or 0,
                        chunks=row[4] or 0,
                        uploadedAt=row[5].strftime("%Y-%m-%d") if row[5] else "",
                        status=row[6] or "ready",
                    )
                )
            return docs
    except Exception as e:
        logger.error(f"List documents error: {e}")
        return []


@app.post("/api/documents/upload", response_model=DocumentUploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None,
):
    """
    Upload and index new PDF documents.
    Persistence flow:
    1. Create FileMetadata row (status=indexing)
    2. Save files to ./temp_uploads
    3. Process & embed → Qdrant
    4. Update FileMetadata row (status=ready, chunks populated)
    """
    if not vs_manager:
        raise HTTPException(status_code=503, detail="Vector Store not initialized")

    # ── Security: Validate files ──
    MAX_SIZE_BYTES = 50 * 1024 * 1024
    for file in files:
        if not any(file.filename.lower().endswith(ext) for ext in [".pdf", ".txt", ".docx"]):
            raise HTTPException(status_code=400, detail=f"Only PDF, TXT, and DOCX files are accepted: {file.filename}")
        content = await file.read()
        if len(content) > MAX_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large (max 50 MB): {file.filename}")
        await file.seek(0)

    temp_dir = Path("./temp_uploads")
    temp_dir.mkdir(exist_ok=True)

    saved_files: List[Path] = []
    file_ids: List[str] = []

    try:
        # ── Phase 1: Persist FileMetadata rows (status=indexing) ──
        for file in files:
            file_id = str(uuid.uuid4())
            file_ids.append(file_id)
            file_path = temp_dir / file.filename

            # Save file to disk
            with open(file_path, "wb") as f:
                f.write(await file.read())
            saved_files.append(file_path)

            # Insert metadata into PostgreSQL
            try:
                async with get_async_session() as session:
                    meta = FileMetadata(
                        file_id=file_id,
                        filename=file.filename,
                        file_size=file.size,
                        upload_date=datetime.now(timezone.utc),
                        collection_name=settings.QDRANT_COLLECTION_NAME,
                        status="indexing",
                        pages=0,
                        chunks=0,
                    )
                    session.add(meta)
                    await session.commit()
                    logger.info(f"Persisted FileMetadata: {file_id} → {file.filename}")
            except Exception as db_err:
                logger.error(f"DB insert failed for {file.filename}: {db_err}")
                # Continue processing — at worst Qdrant has data but DB is out of sync

        # ── Phase 2: Process documents, embed, store in Qdrant ──
        processor = DocumentProcessor()
        documents = processor.process_documents(str(temp_dir))

        if documents:
            vs_manager.add_documents_to_vectorstore(documents)
            total_chunks = len(documents)
        else:
            total_chunks = 0

        # ── Phase 3: Update FileMetadata with final counts (by file_id, not filename) ──
        # Build a map from filename → total chunk count
        chunks_per_file: Dict[str, int] = {}
        for doc in documents:
            src = doc.metadata.get("source", "")
            chunks_per_file[src] = chunks_per_file.get(src, 0) + 1

        # Update each file individually using its file_id
        for file_id, file_path in zip(file_ids, saved_files):
            filename = file_path.name
            chunks_for_this = chunks_per_file.get(filename, 0)
            try:
                async with get_async_session() as db:
                    await db.execute(
                        text("""
                        UPDATE file_metadata
                        SET status = 'ready',
                            chunks = :chunks,
                            pages = :pages
                        WHERE file_id = :fid
                        """),
                        {
                            "chunks": chunks_for_this,
                            "pages": 0,  # TODO: extract actual page count from PDF
                            "fid": file_id,
                        },
                    )
                    await db.commit()
            except Exception as upd_err:
                logger.error(f"Failed to update metadata for {filename} (file_id={file_id}): {upd_err}")

        return DocumentUploadResponse(
            message=f"Successfully indexed {total_chunks} chunks from {len(saved_files)} file(s)",
            file_id=file_ids[0] if file_ids else "",
            success=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents/stats")
async def get_document_stats():
    """Get vector index and file statistics."""
    try:
        async with get_async_session() as db:
            result = await db.execute(text("SELECT COUNT(*), SUM(chunks) FROM file_metadata"))
            file_count, total_chunks = result.fetchone()
            file_count = file_count or 0
            total_chunks = total_chunks or 0
    except Exception as e:
        logger.error(f"DB stats error: {e}")
        file_count = 0
        total_chunks = 0

    try:
        vs_stats = vs_manager.get_index_stats() if vs_manager else {}
        qdrant_vectors = vs_stats.get("total_vectors", 0)
    except Exception:
        qdrant_vectors = 0

    return {
        "collection_name": settings.QDRANT_COLLECTION_NAME,
        "total_chunks": qdrant_vectors,
        "indexed_files": file_count,
        "chunks_per_file": total_chunks,
    }


@app.delete("/api/documents")
async def clear_all_documents():
    """
    Delete all documents from Qdrant AND file_metadata table.
    Destructive — use with caution.
    """
    success_qdrant = False
    success_db = False

    # Delete from Qdrant
    try:
        success_qdrant = vs_manager.delete_all_documents()
    except Exception as e:
        logger.error(f"Qdrant clear error: {e}")

    # Delete from PostgreSQL
    try:
        async with get_async_session() as db:
            await db.execute(text("DELETE FROM file_metadata"))
            await db.commit()
        success_db = True
    except Exception as e:
        logger.error(f"PostgreSQL clear error: {e}")

    if success_qdrant and success_db:
        return {"message": "All documents deleted from Qdrant and PostgreSQL"}
    elif success_qdrant or success_db:
        return {"message": "Partial deletion — check logs"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete documents from both stores")


# ============= Search Endpoint =============

@app.post("/api/search")
async def search(query: str, top_k: int = 5):
    """Search documents directly via Qdrant."""
    if not vs_manager:
        raise HTTPException(status_code=503, detail="Vector Store not initialized")
    try:
        results = vs_manager.search_documents(query, top_k=top_k)
        return {
            "query": query,
            "results_count": len(results),
            "results": [
                {
                    "source": doc.metadata.get("source"),
                    "score": score,
                    "preview": doc.page_content[:200],
                }
                for doc, score in results
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= Usage / Token Stats =============

@app.get("/api/usage")
async def get_usage():
    """Return vector store usage + DB file count as a proxy for token usage."""
    qdrant_chunks = 0
    try:
        stats = vs_manager.get_index_stats()
        qdrant_chunks = stats.get("total_vectors", 0)
    except Exception:
        pass

    db_files = 0
    try:
        async with get_async_session() as db:
            result = await db.execute(text("SELECT COUNT(*) FROM file_metadata"))
            db_files = result.scalar_one_or_none() or 0
    except Exception:
        pass

    estimated_tokens = (qdrant_chunks + db_files) * 500  # rough heuristic
    return {
        "used": estimated_tokens,
        "total": 1_000_000,
        "qdrant_chunks": qdrant_chunks,
        "db_files": db_files,
    }


# ============= Root =============

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Company Intelligence RAG API",
        "version": "1.1.0",
        "docs": "/docs",
        "status": "healthy" if chatbot else "initializing",
        "databases": {
            "qdrant": chatbot is not None,
            "postgresql": True,  # DB init happens at startup
        },
    }
