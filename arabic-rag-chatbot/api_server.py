"""
api_server.py - FastAPI backend for the Arabic RAG system.
Run with: uvicorn api_server:app --reload
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.header import decode_header
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import unicodedata
from urllib.parse import unquote
import uuid

from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text

from config import settings
from database import ChatHistory, FileMetadata, close_db, get_async_session, init_db
from document_processor import DocumentProcessor
from query_router import QueryIntent, QueryRouter
from rag_pipeline import RAGChatbot
from vector_store import VectorStoreManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

moderation_logger = logging.getLogger("moderation")
if not moderation_logger.handlers:
    moderation_handler = logging.StreamHandler()
    moderation_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    moderation_logger.addHandler(moderation_handler)
moderation_logger.setLevel(logging.INFO)
moderation_logger.propagate = False

vs_manager: Optional[VectorStoreManager] = None
chatbot: Optional[RAGChatbot] = None
query_router: Optional[QueryRouter] = None
DEFAULT_USER_ID = "anonymous"
UPLOAD_JOBS: Dict[str, Dict[str, Any]] = {}

PROMPT_INJECTION_PATTERNS = [
    "ignore previous",
    "start your response with",
    "you are now",
    "pretend you are",
    "act as",
    "dan",
]
ARABIC_SLUR_BLOCKLIST = [
    "يا زنجي",
    "زنجي",
    "عبد",
    "متخلف",
    "كلب",
    "حمار",
    "قذر",
    "وسخ",
]

DOCUMENT_INVENTORY_PATTERNS = [
    "what files do you have",
    "what documents do you have",
    "which files do you have",
    "which documents do you have",
    "list documents",
    "list files",
    "available documents",
    "available files",
    "ايش الملفات",
    "ما الملفات",
    "وش الملفات",
    "الملفات الي عندك",
    "الملفات اللي عندك",
    "ما الوثائق",
    "وش الوثائق",
    "ايش الوثائق",
]
DOCUMENT_VISIBILITY_PATTERNS = [
    "can you see the file",
    "can you see my file",
    "can you access the file",
    "is the file uploaded",
    "is my file uploaded",
    "is the document ready",
    "is my document ready",
    "file ready",
    "document ready",
    "تقدر تشوف الملف",
    "تقدر ترى الملف",
    "تشوف الملف",
    "شايف الملف",
    "هل تشوف الملف",
    "هل الملف موجود",
    "هل الملف جاهز",
    "هل المستند جاهز",
    "الملف مرفوع",
    "المستند مرفوع",
    "وصل الملف",
    "وصل المستند",
]
DOCUMENT_NAME_QUERY_PATTERNS = [
    "file named",
    "file name",
    "document named",
    "document name",
    "هل عندك ملف",
    "في عندك ملف",
    "عندك ملف",
    "ملف اسمه",
    "اسم الملف",
    "وثيقة اسمها",
    "الوثيقة",
]
FILE_CONTENT_QUERY_PATTERNS = [
    "what is in the file",
    "what is inside the file",
    "what does the file talk about",
    "what is this file about",
    "summarize this file",
    "summarise this file",
    "file contents",
    "document contents",
    "what is inside",
    "what does it talk about",
    "ايش داخله",
    "وش داخله",
    "ماذا يحتوي",
    "محتوى الملف",
    "ملخص الملف",
    "لخص الملف",
    "ايش يتكلم عنه",
    "وش يتكلم عنه",
    "يتكلم عن ايش",
    "يتكلم عنه",
    "عن ايش",
]


async def cleanup_old_jobs() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    to_delete = [
        job_id
        for job_id, job in UPLOAD_JOBS.items()
        if datetime.fromisoformat(job["updated_at"]) < cutoff and job["status"] in {"completed", "error"}
    ]
    for job_id in to_delete:
        UPLOAD_JOBS.pop(job_id, None)


async def _run_periodic(fn, interval_seconds: int) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await fn()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up application resources."""
    global vs_manager, chatbot, query_router
    logger.info("Starting application...")
    cleanup_task: Optional[asyncio.Task] = None

    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database init error: %s", e)

    try:
        vs_manager = VectorStoreManager()
        chatbot = RAGChatbot(vs_manager)
        query_router = QueryRouter()
        cleanup_task = asyncio.create_task(_run_periodic(cleanup_old_jobs, interval_seconds=3600))
        if settings.RESTORE_CHAT_HISTORY_ON_STARTUP:
            logger.info("Chat history restore is enabled, but history is client-managed per session.")
        logger.info("Application initialized successfully")
    except Exception as e:
        logger.error("Startup error: %s", e)

    yield

    logger.info("Shutting down application...")
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
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
    id: str
    name: str
    size: int
    pages: int
    chunks: int
    uploadedAt: str
    status: str


class DocumentUploadResponse(BaseModel):
    message: str
    file_id: str
    success: bool
    document: Optional[DocumentRecord] = None
    job_id: Optional[str] = None
    status: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    initialized: bool
    total_vectors: Optional[int] = None
    db_connected: bool = False


def normalize_user_id(user_id: Optional[str]) -> str:
    value = (user_id or "").strip()
    return value[:128] if value else DEFAULT_USER_ID


def normalize_upload_filename(filename: Optional[str]) -> str:
    raw_name = (filename or "").strip()
    if not raw_name:
        return ""

    decoded_parts: List[str] = []
    try:
        for value, encoding in decode_header(raw_name):
            if isinstance(value, bytes):
                decoded_parts.append(value.decode(encoding or "utf-8", errors="replace"))
            else:
                decoded_parts.append(value)
    except Exception:
        decoded_parts = [raw_name]

    decoded_name = "".join(decoded_parts)
    decoded_name = unquote(decoded_name).replace("\x00", "")
    basename = os.path.basename(decoded_name) or os.path.basename(raw_name)
    safe_name = basename.replace("/", "_").replace("\\", "_").strip()
    return unicodedata.normalize("NFC", safe_name)


def normalize_search_text(value: str) -> str:
    lowered = unicodedata.normalize("NFC", (value or "").strip().lower())
    lowered = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", lowered)
    lowered = lowered.replace("\u0640", "")
    lowered = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", lowered)
    translation_table = str.maketrans(
        {
            "أ": "ا",
            "إ": "ا",
            "آ": "ا",
            "ٱ": "ا",
            "ى": "ي",
            "ئ": "ي",
            "ؤ": "و",
            "ة": "ه",
        }
    )
    lowered = lowered.translate(translation_table)
    lowered = re.sub(r"[^\w\u0600-\u06FF.\- ]+", " ", lowered, flags=re.UNICODE)
    return " ".join(lowered.split())


def contains_blocked_arabic_term(query_text: str) -> bool:
    normalized_query = normalize_search_text(query_text)
    if not normalized_query:
        return False

    normalized_tokens = set(normalized_query.split())
    for term in ARABIC_SLUR_BLOCKLIST:
        normalized_term = normalize_search_text(term)
        if not normalized_term:
            continue

        term_tokens = normalized_term.split()
        if len(term_tokens) == 1:
            if normalized_term in normalized_tokens:
                return True
            continue

        if re.search(rf"(^|\s){re.escape(normalized_term)}($|\s)", normalized_query):
            return True

    return False


def detect_query_language(query_text: str, ui_language: str = "en") -> str:
    text_value = (query_text or "").strip()
    if not text_value:
        return ui_language

    meaningful_chars = [char for char in text_value if not char.isspace()]
    if not meaningful_chars:
        return ui_language

    arabic_chars = [char for char in meaningful_chars if "\u0600" <= char <= "\u06FF"]
    arabic_ratio = len(arabic_chars) / len(meaningful_chars)

    if arabic_ratio > 0.60:
        return "ar"
    if arabic_ratio < 0.20:
        return "en"
    return ui_language


def validate_input(query_text: str, session_id: str) -> None:
    text_value = (query_text or "").strip()
    normalized = text_value.lower()

    if len(text_value) < 2:
        moderation_logger.warning("blocked: short_query from %s", session_id)
        raise HTTPException(status_code=400, detail="هذا الطلب لا يمكن معالجته")

    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern in normalized:
            moderation_logger.warning("blocked: prompt_injection from %s", session_id)
            raise HTTPException(status_code=400, detail="هذا الطلب لا يمكن معالجته")

    if contains_blocked_arabic_term(text_value):
        moderation_logger.warning("blocked: abusive_language from %s", session_id)
        raise HTTPException(status_code=400, detail="هذا الطلب لا يمكن معالجته")


def is_document_inventory_query(query: str) -> bool:
    normalized_query = normalize_search_text(query)
    return any(pattern in normalized_query for pattern in DOCUMENT_INVENTORY_PATTERNS)


def is_document_visibility_query(query: str) -> bool:
    normalized_query = normalize_search_text(query)
    return any(pattern in normalized_query for pattern in DOCUMENT_VISIBILITY_PATTERNS)


async def get_user_documents_for_collection(user_id: str) -> List[tuple]:
    async with get_async_session() as db:
        result = await db.execute(
            text(
                """
                SELECT file_id, filename, pages, chunks, status
                FROM file_metadata
                WHERE user_id = :uid
                ORDER BY upload_date DESC
                """
            ),
            {"uid": user_id},
        )
        return result.fetchall()


async def find_matching_file_ids(user_id: str, user_query: str) -> List[str]:
    normalized_query = normalize_search_text(user_query)
    if not normalized_query:
        return []

    rows = await get_user_documents_for_collection(user_id)
    matched_file_ids: List[str] = []
    for file_id, filename, _pages, _chunks, _status in rows:
        normalized_name = normalize_search_text(filename or "")
        stem = normalize_search_text(Path(filename or "").stem)
        if normalized_name and normalized_name in normalized_query:
            matched_file_ids.append(file_id)
            continue
        if stem and stem in normalized_query:
            matched_file_ids.append(file_id)
            continue

        stem_tokens = [token for token in stem.split() if len(token) >= 3]
        if stem_tokens and any(token in normalized_query for token in stem_tokens):
            matched_file_ids.append(file_id)

    return matched_file_ids


def is_specific_file_query(query: str) -> bool:
    normalized_query = normalize_search_text(query)
    return any(pattern in normalized_query for pattern in DOCUMENT_NAME_QUERY_PATTERNS)


def is_file_content_query(query: str) -> bool:
    normalized_query = normalize_search_text(query)
    return any(pattern in normalized_query for pattern in FILE_CONTENT_QUERY_PATTERNS)


async def build_specific_file_response(user_id: str, user_query: str, language: str) -> Optional[str]:
    matched_file_ids = await find_matching_file_ids(user_id, user_query)
    if not matched_file_ids:
        return None

    rows = await get_user_documents_for_collection(user_id)
    matched_documents = [row for row in rows if row[0] in matched_file_ids]
    if not matched_documents:
        return None

    document_lines = [
        f"- {filename} ({pages or 0} pages, {chunks or 0} chunks, {status or 'ready'})"
        for _file_id, filename, pages, chunks, status in matched_documents
    ]

    if language == "ar":
        return "نعم، عندي هذه الملفات المطابقة:\n" + "\n".join(document_lines)
    return "Yes, I have these matching documents:\n" + "\n".join(document_lines)


async def build_document_inventory_response(user_id: str, language: str) -> str:
    rows = await get_user_documents_for_collection(user_id)
    if not rows:
        return "لا توجد ملفات مرفوعة حالياً." if language == "ar" else "There are no uploaded documents right now."

    document_lines = [
        f"- {filename} ({pages or 0} pages, {chunks or 0} chunks, {status or 'ready'})"
        for _file_id, filename, pages, chunks, status in rows
    ]

    if language == "ar":
        return "الملفات المتوفرة حالياً هي:\n" + "\n".join(document_lines)
    return "The currently available documents are:\n" + "\n".join(document_lines)


async def build_document_visibility_response(user_id: str, language: str) -> str:
    rows = await get_user_documents_for_collection(user_id)
    if not rows:
        if language == "ar":
            return (
                "لا توجد ملفات مرفوعة حالياً.\n\n"
                "ارفع ملف PDF أو DOCX أو TXT أولاً، وبعدها تقدر تطلب مني تلخيصه أو تسأل عن محتواه."
            )
        return (
            "I don't see any uploaded documents yet.\n\n"
            "Upload a PDF, DOCX, or TXT file first, then you can ask me to summarize it or answer questions about it."
        )

    ready_rows = [row for row in rows if (row[4] or "ready") == "ready"]
    pending_rows = [row for row in rows if (row[4] or "ready") != "ready"]
    visible_rows = ready_rows or rows

    document_lines = [
        f"- {filename}، {pages or 0} صفحة، {chunks or 0} جزء مفهرس"
        if language == "ar"
        else f"- {filename}, {pages or 0} pages, {chunks or 0} indexed chunks"
        for _file_id, filename, pages, chunks, _status in visible_rows
    ]

    if language == "ar":
        intro = "نعم، عندي الملف التالي مفهرس وجاهز للاستفسار:" if len(visible_rows) == 1 else "نعم، عندي الملفات التالية مفهرسة وجاهزة للاستفسار:"
        if pending_rows and not ready_rows:
            intro = "نعم، وصلتني الملفات التالية، لكنها قد تكون ما زالت قيد الفهرسة:"
        return (
            intro
            + "\n"
            + "\n".join(document_lines)
            + "\n\nتقدر تسألني مثلاً: لخص الملف، ما أهم البنود، أو استخرج المعلومات الرئيسية."
        )

    intro = "Yes, I have this document indexed and ready for questions:" if len(visible_rows) == 1 else "Yes, I have these documents indexed and ready for questions:"
    if pending_rows and not ready_rows:
        intro = "Yes, I can see these documents, but they may still be indexing:"
    return (
        intro
        + "\n"
        + "\n".join(document_lines)
        + "\n\nYou can ask me things like: summarize the file, list the key points, or extract the main information."
    )


async def build_latest_document_response(user_id: str, language: str) -> str:
    rows = await get_user_documents_for_collection(user_id)
    if not rows:
        if language == "ar":
            return (
                "لا يوجد آخر ملف لأنك لم ترفع أي ملفات بعد.\n\n"
                "ارفع ملف PDF أو DOCX أو TXT أولاً، ثم اسألني عنه."
            )
        return (
            "There is no latest document yet because you have not uploaded any files.\n\n"
            "Upload a PDF, DOCX, or TXT file first, then ask me about it."
        )

    _file_id, filename, pages, chunks, status = rows[0]
    if language == "ar":
        return (
            "آخر ملف مرفوع عندك هو:\n"
            f"- {filename}، {pages or 0} صفحة، {chunks or 0} جزء مفهرس، الحالة: {status or 'ready'}\n\n"
            "تقدر تسألني مثلاً: لخص آخر ملف، ما أهم البنود، أو استخرج المعلومات الرئيسية."
        )
    return (
        "Your latest uploaded document is:\n"
        f"- {filename}, {pages or 0} pages, {chunks or 0} indexed chunks, status: {status or 'ready'}\n\n"
        "You can ask me things like: summarize the latest file, list the key points, or extract the main information."
    )


def build_help_response(language: str) -> str:
    if language == "ar":
        return (
            "طريقة الاستخدام:\n"
            "1. ارفع ملف PDF أو DOCX أو TXT.\n"
            "2. انتظر حتى تظهر حالته جاهزة.\n"
            "3. اسأل عن محتواه، مثل: لخص الملف، ما أهم البنود، أو استخرج التواريخ والأسماء.\n\n"
            "أقدر أساعدك أيضاً في معرفة الملفات المرفوعة أو آخر ملف جاهز للاستفسار."
        )
    return (
        "How to use the app:\n"
        "1. Upload a PDF, DOCX, or TXT file.\n"
        "2. Wait until it is indexed and ready.\n"
        "3. Ask about its content, such as: summarize the file, list key points, or extract dates and names.\n\n"
        "I can also help you list uploaded files or identify the latest ready document."
    )


def build_out_of_scope_response(language: str) -> str:
    if language == "ar":
        return (
            "لا أقدر أجاوب على هذا السؤال من خارج الملفات المرفوعة.\n\n"
            "ارفع مستنداً أو اسأل عن محتوى الملفات الموجودة، وسأجاوبك بناءً عليها مع المصادر."
        )
    return (
        "I can’t answer that from outside the uploaded documents.\n\n"
        "Upload a document or ask about the existing files, and I’ll answer based on them with sources."
    )


def stream_direct_response(
    background_tasks: BackgroundTasks,
    session_id: str,
    user_id: str,
    user_message: str,
    response_text: str,
) -> StreamingResponse:
    response_holder = {"ai_response": response_text}
    queue_chat_persistence(background_tasks, session_id, user_id, user_message, response_holder)
    return StreamingResponse(
        stream_plain_text_response(response_text),
        media_type="text/plain",
        background=background_tasks,
    )


def stream_plain_text_response(text_value: str):
    yield text_value


async def save_chat_message_for_user(
    session_id: str,
    user_id: str,
    user_message: str,
    response_holder: Dict[str, str],
) -> None:
    ai_response = (response_holder.get("ai_response") or "").strip()
    if not user_message.strip() and not ai_response:
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
    except Exception as e:
        logger.error("Failed to save chat history: %s", e)


def queue_chat_persistence(
    background_tasks: BackgroundTasks,
    session_id: str,
    user_id: str,
    user_message: str,
    response_holder: Dict[str, str],
) -> None:
    background_tasks.add_task(
        save_chat_message_for_user,
        session_id,
        user_id,
        user_message,
        response_holder,
    )


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


async def process_upload_job(
    job_id: str,
    user_id: str,
    temp_dir: Path,
    saved_files: List[Path],
    file_ids: List[str],
    file_sizes: Dict[str, int],
    file_ids_by_name: Dict[str, str],
    upload_date: datetime,
) -> None:
    try:
        UPLOAD_JOBS[job_id].update(
            {
                "status": "processing",
                "progress": 15,
                "message": "Extracting document text",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        processor = DocumentProcessor()
        documents = await processor.process_documents_async(
            str(temp_dir),
            upload_timestamp=upload_date.isoformat(),
        )

        UPLOAD_JOBS[job_id].update(
            {
                "status": "indexing",
                "progress": 55,
                "message": "Indexing document chunks",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        for doc in documents:
            source_name = doc.metadata.get("source", "")
            doc.metadata["user_id"] = user_id
            doc.metadata["upload_timestamp"] = upload_date.isoformat()
            if source_name in file_ids_by_name:
                doc.metadata["file_id"] = file_ids_by_name[source_name]

        if documents:
            indexed_ok = await vs_manager.add_documents_to_vectorstore_async(documents)
            if not indexed_ok:
                raise RuntimeError("Failed to index uploaded documents into Qdrant.")

        chunks_per_file: Dict[str, int] = {}
        pages_per_file: Dict[str, int] = {}
        for doc in documents:
            src = doc.metadata.get("source", "")
            chunks_per_file[src] = chunks_per_file.get(src, 0) + 1
            page_number = doc.metadata.get("page_number") or doc.metadata.get("page")
            if isinstance(page_number, int):
                pages_per_file[src] = max(pages_per_file.get(src, 0), page_number)

        first_document: Optional[DocumentRecord] = None
        for file_id, file_path in zip(file_ids, saved_files):
            filename = file_path.name
            pages = pages_per_file.get(filename, 0)
            chunks = chunks_per_file.get(filename, 0)

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

        UPLOAD_JOBS[job_id].update(
            {
                "status": "completed",
                "progress": 100,
                "message": f"Successfully indexed {len(documents)} chunks from {len(saved_files)} file(s)",
                "document": first_document.model_dump() if first_document else None,
                "file_ids": file_ids,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception as e:
        logger.error("Upload job %s failed: %s", job_id, e)
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
            except Exception as mark_err:
                logger.error("Failed to mark upload %s as error: %s", file_id, mark_err)

        UPLOAD_JOBS[job_id].update(
            {
                "status": "error",
                "progress": 100,
                "message": str(e),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
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


@app.get("/health", response_model=HealthResponse)
async def health_check():
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
async def chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    if not chatbot:
        raise HTTPException(status_code=503, detail="Chatbot not initialized. Check API keys and vector store config.")

    try:
        user_message = request.message or (request.query or "").strip()
        user_id = normalize_user_id(x_user_id)
        session_id = request.sessionId or str(uuid.uuid4())

        validate_input(user_message, session_id)

        detected_language = detect_query_language(
            user_message,
            ui_language=request.language or "en",
        )
        logger.info("New query [%s]: %s", detected_language, user_message[:80])

        if is_document_visibility_query(user_message):
            visibility_response = await build_document_visibility_response(user_id, detected_language)
            return stream_direct_response(background_tasks, session_id, user_id, user_message, visibility_response)

        if is_document_inventory_query(user_message):
            inventory_response = await build_document_inventory_response(user_id, detected_language)
            return stream_direct_response(background_tasks, session_id, user_id, user_message, inventory_response)

        if is_specific_file_query(user_message):
            specific_file_response = await build_specific_file_response(user_id, user_message, detected_language)
            if specific_file_response:
                return stream_direct_response(background_tasks, session_id, user_id, user_message, specific_file_response)

        if query_router:
            route = await query_router.classify(user_message, detected_language)
            logger.info(
                "Query route intent=%s confidence=%.2f reason=%s",
                route.intent.value,
                route.confidence,
                route.reason[:80],
            )

            if route.intent == QueryIntent.METADATA_STATUS:
                visibility_response = await build_document_visibility_response(user_id, detected_language)
                return stream_direct_response(background_tasks, session_id, user_id, user_message, visibility_response)

            if route.intent == QueryIntent.LATEST_DOCUMENT:
                latest_response = await build_latest_document_response(user_id, detected_language)
                return stream_direct_response(background_tasks, session_id, user_id, user_message, latest_response)

            if route.intent == QueryIntent.DOCUMENT_INVENTORY:
                inventory_response = await build_document_inventory_response(user_id, detected_language)
                return stream_direct_response(background_tasks, session_id, user_id, user_message, inventory_response)

            if route.intent == QueryIntent.HELP:
                help_response = build_help_response(detected_language)
                return stream_direct_response(background_tasks, session_id, user_id, user_message, help_response)

            if route.intent == QueryIntent.OUT_OF_SCOPE:
                out_of_scope_response = build_out_of_scope_response(detected_language)
                return stream_direct_response(background_tasks, session_id, user_id, user_message, out_of_scope_response)

        if not await get_user_documents_for_collection(user_id):
            visibility_response = await build_document_visibility_response(user_id, detected_language)
            return stream_direct_response(background_tasks, session_id, user_id, user_message, visibility_response)

        matched_file_ids = await find_matching_file_ids(user_id, user_message)
        prefer_full_file_context = bool(matched_file_ids and is_file_content_query(user_message))
        response_holder: Dict[str, str] = {"ai_response": ""}

        def handle_response_complete(response_text: str) -> None:
            response_holder["ai_response"] = response_text

        async def stream_response():
            try:
                async for chunk in chatbot.stream_chat(
                    user_query=user_message,
                    include_sources=request.sourceCheck,
                    language=detected_language,
                    history=request.history,
                    user_id=user_id,
                    file_ids=matched_file_ids or None,
                    prefer_full_file_context=prefer_full_file_context,
                    on_response_complete=handle_response_complete,
                ):
                    yield chunk
            finally:
                queue_chat_persistence(
                    background_tasks,
                    session_id,
                    user_id,
                    user_message,
                    response_holder,
                )

        return StreamingResponse(
            stream_response(),
            media_type="text/plain",
            background=background_tasks,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/history")
async def get_chat_history(
    session_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
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
            history.append(
                {
                    "user_message": user_message,
                    "ai_response": ai_response,
                    "timestamp": iso_timestamp,
                }
            )

        return {"history": history, "message_count": len(rows), "session_id": selected_session_id}
    except Exception as e:
        logger.error("Chat history error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/clear")
async def clear_history(
    session_id: Optional[str] = None,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
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

            if chatbot:
                chatbot.clear_history()

        return {"message": "History cleared"}
    except Exception as e:
        logger.error("Clear history error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions")
async def list_sessions(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")):
    try:
        user_id = normalize_user_id(x_user_id)
        async with get_async_session() as db:
            result = await db.execute(
                text(
                    """
                    WITH session_rollup AS (
                        SELECT
                            session_id,
                            MAX(timestamp) AS updated_at,
                            COUNT(*) AS message_count
                        FROM chat_history
                        WHERE user_id = :uid
                        GROUP BY session_id
                    )
                    SELECT
                        session_rollup.session_id,
                        session_rollup.updated_at,
                        session_rollup.message_count,
                        chat_history.user_message AS preview_text
                    FROM session_rollup
                    JOIN chat_history
                        ON chat_history.session_id = session_rollup.session_id
                        AND chat_history.user_id = :uid
                        AND chat_history.timestamp = session_rollup.updated_at
                    ORDER BY session_rollup.updated_at DESC
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
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
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
    job_id = str(uuid.uuid4())

    try:
        for file in files:
            normalized_filename = normalize_upload_filename(file.filename)
            if not normalized_filename:
                raise HTTPException(status_code=400, detail="Each uploaded file must have a filename.")
            if not any(normalized_filename.lower().endswith(ext) for ext in [".pdf", ".txt", ".docx"]):
                raise HTTPException(
                    status_code=400,
                    detail=f"Only PDF, TXT, and DOCX files are accepted: {normalized_filename}",
                )

            file_id = str(uuid.uuid4())
            file_path = temp_dir / normalized_filename
            file_ids.append(file_id)

            file_size = 0
            with open(file_path, "wb") as f:
                while chunk := await file.read(1024 * 1024):
                    file_size += len(chunk)
                    if file_size > max_size_bytes:
                        file_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File too large (max 50 MB): {normalized_filename}",
                        )
                    f.write(chunk)

            file_sizes[file_id] = file_size
            saved_files.append(file_path)
            file_ids_by_name[normalized_filename] = file_id

            async with get_async_session() as session:
                session.add(
                    FileMetadata(
                        file_id=file_id,
                        user_id=user_id,
                        filename=normalized_filename,
                        file_size=file_sizes[file_id],
                        upload_date=upload_date,
                        collection_name=settings.QDRANT_COLLECTION_NAME,
                        status="indexing",
                        pages=0,
                        chunks=0,
                    )
                )

        UPLOAD_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "message": "Upload accepted",
            "user_id": user_id,
            "file_ids": file_ids,
            "document": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        background_tasks.add_task(
            process_upload_job,
            job_id,
            user_id,
            temp_dir,
            saved_files,
            file_ids,
            file_sizes,
            file_ids_by_name,
            upload_date,
        )

        return DocumentUploadResponse(
            message="Upload accepted and processing started",
            file_id=file_ids[0] if file_ids else "",
            success=True,
            job_id=job_id,
            status="queued",
            document=build_document_record(
                file_id=file_ids[0],
                filename=saved_files[0].name,
                file_size=file_sizes[file_ids[0]],
                pages=0,
                chunks=0,
                upload_date=upload_date,
                status="indexing",
            )
            if file_ids and saved_files
            else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload enqueue error: %s", e)
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
            except Exception as mark_err:
                logger.error("Failed to mark upload %s as error: %s", file_id, mark_err)

        for file_path in saved_files:
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception:
                pass
        try:
            temp_dir.rmdir()
        except Exception:
            pass

        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/upload/status/{job_id}")
async def get_upload_status(
    job_id: str,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    user_id = normalize_user_id(x_user_id)
    job = UPLOAD_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Upload job not found")
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not allowed to access this upload job")

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "file_ids": job.get("file_ids", []),
        "document": job.get("document"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
    }


@app.get("/api/documents/stats")
async def get_document_stats(x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")):
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
