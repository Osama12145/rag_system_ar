"""
api_server.py - FastAPI backend for the Arabic RAG system.
Run with: uvicorn api_server:app --reload
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import logging
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text

from config import settings
from database import ChatHistory, FileMetadata, close_db, get_async_session, init_db
from document_processor import DocumentProcessor
from rag_pipeline import RAGChatbot
from vector_store import VectorStoreManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

vs_manager: Optional[VectorStoreManager] = None
chatbot: Optional[RAGChatbot] = None
DEFAULT_USER_ID = "anonymous"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up application resources."""
    global vs_manager, chatbot
    logger.info("Starting application...")

    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database init error: %s", e)

    try:
        vs_manager = VectorStoreManager()
        chatbot = RAGChatbot(vs_manager)
        if settings.RESTORE_CHAT_HISTORY_ON_STARTUP:
            logger.info("Chat history restore is enabled, but history is client-managed per session.")
        logger.info("Application initialized successfully")
    except Exception as e:
        logger.error("Startup error: %s", e)

    yield

    logger.info("Shutting down application...")
    await close_db()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="Company Intelligence RAG API",
    description="API for querying company documents via RAG",
    version="1.2.0",
    lifespan=lifespan,
)

allowed_origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-User-Id"],
)


class ChatRequest(BaseModel):
    """Chat request payload."""

    message: str = Field(default="", max_length=4000)
    query: Optional[str] = None
    sourceCheck: bool = True
    deepResearch: bool = False
    reasoning: bool = False
    language: str = "en"
    history: Optional[List[Dict[str, Any]]] = None
    sessionId: Optional[str] = None

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_message_or_query(self):
        if not self.message and not (self.query or "").strip():
            raise ValueError("message or query must not be empty")
        return self


class DocumentRecord(BaseModel):
    """Single document metadata record returned to the frontend."""

    id: str
    name: str
    size: int
    pages: int
    chunks: int
    uploadedAt: str
    status: str


class DocumentUploadResponse(BaseModel):
    """Document upload response."""

    message: str
    file_id: str
    success: bool
    document: Optional[DocumentRecord] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    initialized: bool
    total_vectors: Optional[int] = None
    db_connected: bool = False


def normalize_user_id(user_id: Optional[str]) -> str:
    """Normalize user identity values coming from the frontend."""
    value = (user_id or "").strip()
    return value[:128] if value else DEFAULT_USER_ID


async def save_chat_message_for_user(
    session_id: str,
    user_id: str,
    user_message: str,
    ai_response: str,
):
    """Persist a chat exchange for the current user."""
    if not user_message and not ai_response:
        return
    try:
        async with get_async_session() as session:
            session.add(
                ChatHistory(
                    user_id=user_id,
                    session_id=session_id,
                    user_message=user_message,
                    ai_response=ai_response,
                    timestamp=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception as e:
        logger.error("Failed to save chat history: %s", e)


def persist_chat_message(session_id: str, user_id: str, user_message: str, ai_response: str) -> None:
    """Persist chat history whether or not the current thread has a running event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        thread = threading.Thread(
            target=lambda: asyncio.run(save_chat_message_for_user(session_id, user_id, user_message, ai_response)),
            daemon=True,
        )
        thread.start()
    else:
        loop.create_task(save_chat_message_for_user(session_id, user_id, user_message, ai_response))


def build_document_record(
    *,
    file_id: str,
    filename: str,
    file_size: int,
    pages: int,
    chunks: int,
    upload_date: datetime,
    status: str,
) -> DocumentRecord:
    if isinstance(upload_date, str):
        try:
            parsed_upload_date = datetime.fromisoformat(upload_date)
        except ValueError:
            parsed_upload_date = None
    else:
        parsed_upload_date = upload_date

    return DocumentRecord(
        id=file_id,
        name=filename,
        size=file_size,
        pages=pages,
        chunks=chunks,
        uploadedAt=parsed_upload_date.strftime("%Y-%m-%d") if parsed_upload_date else "",
        status=status,
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check system health status."""
    qdrant_ok = chatbot is not None
    db_ok = False

    try:
        async with get_async_session() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.warning("DB health check failed: %s", e)

    stats = vs_manager.get_index_stats() if vs_manager else {}
    return HealthResponse(
        status="healthy" if qdrant_ok and db_ok else "degraded",
        initialized=chatbot is not None,
        total_vectors=stats.get("total_vectors"),
        db_connected=db_ok,
    )


@app.post("/api/chat")
async def chat(request: ChatRequest, x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")):
    """Stream a response from the chatbot."""
    if not chatbot:
        raise HTTPException(status_code=503, detail="Chatbot not initialized. Check API keys and vector store config.")

    try:
        user_message = request.message or (request.query or "").strip()
        user_id = normalize_user_id(x_user_id)
        session_id = request.sessionId or str(uuid.uuid4())
        logger.info("New query [%s]: %s", request.language, user_message[:80])

        generator = chatbot.stream_chat(
            user_query=user_message,
            include_sources=request.sourceCheck,
            language=request.language,
            history=request.history,
            user_id=user_id,
            on_response_complete=lambda response: persist_chat_message(session_id, user_id, user_message, response),
        )
        return StreamingResponse(generator, media_type="text/plain")
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/history")
async def get_chat_history(
    session_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Return persisted conversation history."""
    try:
        user_id = normalize_user_id(x_user_id)
        async with get_async_session() as db:
            if session_id:
                selected_session_id = session_id
            else:
                sid_result = await db.execute(
                    text(
                        """
                        SELECT session_id
                        FROM chat_history
                        WHERE user_id = :uid
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """
                    ),
                    {"uid": user_id},
                )
                selected_session_id = sid_result.scalar_one_or_none()
                if not selected_session_id:
                    return {"history": [], "message_count": 0, "session_id": None}

            result = await db.execute(
                text(
                    """
                    SELECT user_message, ai_response, timestamp
                    FROM chat_history
                    WHERE session_id = :sid AND user_id = :uid
                    ORDER BY timestamp ASC
                    """
                ),
                {"sid": selected_session_id, "uid": user_id},
            )
            rows = result.fetchall()

        history: List[Dict[str, str]] = []
        for user_message, ai_response, timestamp in rows:
            iso_timestamp = timestamp.isoformat()
            history.append({"role": "user", "content": user_message, "timestamp": iso_timestamp})
            history.append({"role": "assistant", "content": ai_response, "timestamp": iso_timestamp})

        return {
            "history": history,
            "message_count": len(rows),
            "session_id": selected_session_id,
        }
    except Exception as e:
        logger.error("Chat history error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/clear")
async def clear_history(
    session_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Clear conversation history."""
    try:
        user_id = normalize_user_id(x_user_id)
        async with get_async_session() as db:
            selected_session_id = session_id
            if not selected_session_id:
                sid_result = await db.execute(
                    text(
                        """
                        SELECT session_id
                        FROM chat_history
                        WHERE user_id = :uid
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """
                    ),
                    {"uid": user_id},
                )
                selected_session_id = sid_result.scalar_one_or_none()

            if selected_session_id:
                await db.execute(
                    text("DELETE FROM chat_history WHERE session_id = :sid AND user_id = :uid"),
                    {"sid": selected_session_id, "uid": user_id},
                )
                await db.commit()

            if chatbot:
                chatbot.clear_history()

        return {"message": "History cleared"}
    except Exception as e:
        logger.error("Clear history error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions")
async def list_sessions(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")):
    """Return distinct conversation sessions."""
    try:
        user_id = normalize_user_id(x_user_id)
        async with get_async_session() as db:
            result = await db.execute(
                text(
                    """
                    SELECT
                        session_id,
                        MAX(timestamp) AS updated_at,
                        COUNT(*) AS message_count,
                        MAX(user_message) AS preview_text
                    FROM chat_history
                    WHERE user_id = :uid
                    GROUP BY session_id
                    ORDER BY updated_at DESC
                    LIMIT 20
                    """
                ),
                {"uid": user_id},
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
        logger.error("List sessions error: %s", e)
        return {"sessions": []}


@app.get("/api/documents", response_model=List[DocumentRecord])
async def list_documents(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")):
    """Return indexed documents from the metadata store."""
    try:
        user_id = normalize_user_id(x_user_id)
        async with get_async_session() as db:
            result = await db.execute(
                text(
                    """
                    SELECT file_id, filename, file_size, pages, chunks, upload_date, status
                    FROM file_metadata
                    WHERE user_id = :uid
                    ORDER BY upload_date DESC
                    """
                ),
                {"uid": user_id},
            )
            rows = result.fetchall()

        return [
            build_document_record(
                file_id=row[0],
                filename=row[1],
                file_size=row[2] or 0,
                pages=row[3] or 0,
                chunks=row[4] or 0,
                upload_date=row[5],
                status=row[6] or "ready",
            )
            for row in rows
        ]
    except Exception as e:
        logger.error("List documents error: %s", e)
        return []


@app.post("/api/documents/upload", response_model=DocumentUploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Upload and index new documents."""
    if not vs_manager:
        raise HTTPException(status_code=503, detail="Vector Store not initialized")

    max_size_bytes = 50 * 1024 * 1024
    user_id = normalize_user_id(x_user_id)
    temp_root = Path("./temp_uploads") / user_id
    temp_dir = temp_root / str(uuid.uuid4())
    temp_dir.mkdir(parents=True, exist_ok=True)

    saved_files: List[Path] = []
    file_ids: List[str] = []
    file_sizes: Dict[str, int] = {}
    file_ids_by_name: Dict[str, str] = {}
    upload_date = datetime.now(timezone.utc)

    try:
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="Each uploaded file must have a filename.")
            if not any(file.filename.lower().endswith(ext) for ext in [".pdf", ".txt", ".docx"]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Only PDF, TXT, and DOCX files are accepted: {file.filename}",
                )

            content = await file.read()
            if len(content) > max_size_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large (max 50 MB): {file.filename}",
                )

            file_id = str(uuid.uuid4())
            file_path = temp_dir / file.filename
            file_ids.append(file_id)
            file_sizes[file_id] = len(content)

            with open(file_path, "wb") as f:
                f.write(content)
            saved_files.append(file_path)

            try:
                async with get_async_session() as session:
                    session.add(
                        FileMetadata(
                            file_id=file_id,
                            user_id=user_id,
                            filename=file.filename,
                            file_size=file_sizes[file_id],
                            upload_date=upload_date,
                            collection_name=settings.QDRANT_COLLECTION_NAME,
                            status="indexing",
                            pages=0,
                            chunks=0,
                        )
                    )
                    await session.commit()
            except Exception as db_err:
                logger.error("DB insert failed for %s: %s", file.filename, db_err)
            file_ids_by_name[file.filename] = file_id

        processor = DocumentProcessor()
        documents = processor.process_documents(str(temp_dir))
        total_chunks = len(documents)

        for doc in documents:
            source_name = doc.metadata.get("source", "")
            doc.metadata["user_id"] = user_id
            if source_name in file_ids_by_name:
                doc.metadata["file_id"] = file_ids_by_name[source_name]

        if documents and not vs_manager.add_documents_to_vectorstore(documents):
            raise RuntimeError("Failed to index uploaded documents into Qdrant.")

        chunks_per_file: Dict[str, int] = {}
        pages_per_file: Dict[str, int] = {}
        for doc in documents:
            src = doc.metadata.get("source", "")
            chunks_per_file[src] = chunks_per_file.get(src, 0) + 1
            page_num = doc.metadata.get("page")
            if isinstance(page_num, int):
                pages_per_file[src] = max(pages_per_file.get(src, 0), page_num + 1)

        first_document: Optional[DocumentRecord] = None
        for file_id, file_path in zip(file_ids, saved_files):
            filename = file_path.name
            pages = pages_per_file.get(filename, 0)
            chunks = chunks_per_file.get(filename, 0)
            try:
                async with get_async_session() as db:
                    await db.execute(
                        text(
                            """
                            UPDATE file_metadata
                            SET status = 'ready',
                                chunks = :chunks,
                                pages = :pages,
                                error_message = NULL
                            WHERE file_id = :fid
                            """
                        ),
                        {"chunks": chunks, "pages": pages, "fid": file_id},
                    )
                    await db.commit()
            except Exception as upd_err:
                logger.error("Failed to update metadata for %s (%s): %s", filename, file_id, upd_err)

            if first_document is None:
                first_document = build_document_record(
                    file_id=file_id,
                    filename=filename,
                    file_size=file_sizes[file_id],
                    pages=pages,
                    chunks=chunks,
                    upload_date=upload_date,
                    status="ready",
                )

        return DocumentUploadResponse(
            message=f"Successfully indexed {total_chunks} chunks from {len(saved_files)} file(s)",
            file_id=file_ids[0] if file_ids else "",
            success=True,
            document=first_document,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload error: %s", e)
        for file_id in file_ids:
            try:
                async with get_async_session() as db:
                    await db.execute(
                        text(
                            """
                            UPDATE file_metadata
                            SET status = 'error',
                                error_message = :error_message
                            WHERE file_id = :fid
                            """
                        ),
                        {"fid": file_id, "error_message": str(e)},
                    )
                    await db.commit()
            except Exception as mark_err:
                logger.error("Failed to mark upload %s as error: %s", file_id, mark_err)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for file_path in saved_files:
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception as cleanup_err:
                logger.warning("Failed to remove temp file %s: %s", file_path, cleanup_err)
        try:
            temp_dir.rmdir()
        except Exception:
            pass


@app.get("/api/documents/stats")
async def get_document_stats(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")):
    """Get vector index and file statistics."""
    file_count = 0
    total_chunks = 0
    try:
        user_id = normalize_user_id(x_user_id)
        async with get_async_session() as db:
            result = await db.execute(
                text("SELECT COUNT(*), SUM(chunks) FROM file_metadata WHERE user_id = :uid"),
                {"uid": user_id},
            )
            file_count, total_chunks = result.fetchone()
            file_count = file_count or 0
            total_chunks = total_chunks or 0
    except Exception as e:
        logger.error("DB stats error: %s", e)

    return {
        "collection_name": settings.QDRANT_COLLECTION_NAME,
        "total_chunks": total_chunks,
        "indexed_files": file_count,
        "chunks_per_file": total_chunks,
    }


@app.delete("/api/documents")
async def clear_all_documents(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")):
    """Delete all documents from Qdrant and file metadata."""
    success_qdrant = False
    success_db = False
    user_id = normalize_user_id(x_user_id)

    try:
        if vs_manager:
            success_qdrant = vs_manager.delete_documents_for_user(user_id)
    except Exception as e:
        logger.error("Qdrant clear error: %s", e)

    try:
        async with get_async_session() as db:
            await db.execute(text("DELETE FROM file_metadata WHERE user_id = :uid"), {"uid": user_id})
            await db.commit()
        success_db = True
    except Exception as e:
        logger.error("Database clear error: %s", e)

    if success_qdrant and success_db:
        return {"message": "All documents deleted from Qdrant and metadata store"}
    if success_qdrant or success_db:
        return {"message": "Partial deletion completed. Check logs for details."}
    raise HTTPException(status_code=500, detail="Failed to delete documents from both stores")


@app.post("/api/search")
async def search(
    query: str,
    top_k: int = 5,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Search indexed documents directly via Qdrant."""
    if not vs_manager:
        raise HTTPException(status_code=503, detail="Vector Store not initialized")

    try:
        user_id = normalize_user_id(x_user_id)
        results = vs_manager.search_documents(query, top_k=top_k, user_id=user_id)
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


@app.get("/api/usage")
async def get_usage(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")):
    """Return a rough usage estimate."""
    db_files = 0
    qdrant_chunks = 0
    try:
        user_id = normalize_user_id(x_user_id)
        async with get_async_session() as db:
            result = await db.execute(
                text("SELECT COUNT(*), SUM(chunks) FROM file_metadata WHERE user_id = :uid"),
                {"uid": user_id},
            )
            db_files, qdrant_chunks = result.fetchone()
            db_files = db_files or 0
            qdrant_chunks = qdrant_chunks or 0
    except Exception:
        db_files = 0
        qdrant_chunks = 0

    estimated_tokens = (qdrant_chunks + db_files) * 500
    return {
        "used": estimated_tokens,
        "total": 1_000_000,
        "qdrant_chunks": qdrant_chunks,
        "db_files": db_files,
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Company Intelligence RAG API",
        "version": "1.2.0",
        "docs": "/docs",
        "status": "healthy" if chatbot else "initializing",
        "databases": {
            "qdrant": chatbot is not None,
            "metadata": True,
        },
    }
