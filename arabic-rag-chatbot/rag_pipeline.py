"""
rag_pipeline.py - RAG Pipeline
Combines retrieval and generation for document-based Q&A.
"""

from datetime import datetime
from enum import Enum
import json
import logging
import re
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from config import settings
from vector_store import VectorStoreManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPTS = {
    "ar": (
        "أنت مساعد شركة ذكي ومفيد. "
        "أجب على الأسئلة فقط بناءً على وثائق الشركة المقدمة. "
        "إذا لم تجد الإجابة في الوثائق، قل: "
        "'لم أجد معلومات حول هذا الموضوع في وثائق الشركة.' "
        "لا تختلق معلومات أبداً. كن موجزاً ومهنياً وأجب دائماً باللغة العربية."
    ),
    "en": (
        "You are a helpful company assistant. "
        "Answer questions ONLY based on the provided company documents. "
        "If you can't find the answer in the documents, say: "
        "'I couldn't find information about this topic in the company documents.' "
        "NEVER make up information. Be concise and professional. Always respond in English."
    ),
}

PROMPT_TEMPLATE = PromptTemplate(
    input_variables=["context", "question"],
    template="""Context from company documents:
{context}

User question:
{question}

Answer based strictly on the context above:""",
)


class RetrievalIntent(str, Enum):
    SUMMARIZE_LATEST = "SUMMARIZE_LATEST"
    SUMMARIZE_NAMED = "SUMMARIZE_NAMED"
    COMPARE = "COMPARE"
    GENERATE_QUESTIONS = "GENERATE_QUESTIONS"
    SEMANTIC_QA = "SEMANTIC_QA"


def normalize_intent_text(value: str) -> str:
    normalized = (value or "").strip().lower()
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
    normalized = normalized.translate(translation_table)
    normalized = re.sub(r"[^\w\u0600-\u06FF.\- ]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def detect_retrieval_intent(query: str, available_filenames: Optional[List[str]] = None) -> Dict[str, Any]:
    normalized = normalize_intent_text(query)
    filenames = available_filenames or []

    summarize_keywords = ["summarize", "summarise", "summary", "ملخص", "لخص", "اختصر"]
    latest_keywords = [
        "latest",
        "most recent",
        "last uploaded",
        "newest",
        "uploaded file",
        "اخر ملف",
        "احدث ملف",
        "اخر وثيقه",
        "اخر وثيقة",
        "احدث وثيقه",
        "latest file",
        "recent file",
        "last file",
        "most recently uploaded file",
        "تم رفعه",
        "المرفوع",
        "المرفوعه",
    ]
    compare_keywords = ["compare", "comparison", "difference between", "قارن", "مقارنة", "فرق بين", "الفرق بين"]
    question_gen_keywords = [
        "generate questions",
        "create questions",
        "make questions",
        "5 questions",
        "10 questions",
        "quiz",
        "exam questions",
        "اطرح",
        "اطرح لي",
        "اسال",
        "اسأل",
        "ولد أسئلة",
        "انشئ أسئلة",
        "أنشئ أسئلة",
        "اسئلة",
        "أسئلة",
    ]

    named_files = [
        filename
        for filename in filenames
        if filename and normalize_intent_text(filename) in normalized
    ]
    chapter_match = re.search(
        r"(chapter|chapters|section|sections|الفصل|الفصول|القسم|الاقسام)\s+([\d,\sand\-و]+)",
        normalized,
    )

    if any(normalize_intent_text(keyword) in normalized for keyword in compare_keywords):
        return {
            "intent": RetrievalIntent.COMPARE,
            "named_files": named_files,
            "section_hint": chapter_match.group(0) if chapter_match else None,
        }

    if any(normalize_intent_text(keyword) in normalized for keyword in question_gen_keywords):
        return {
            "intent": RetrievalIntent.GENERATE_QUESTIONS,
            "named_files": named_files,
            "section_hint": chapter_match.group(0) if chapter_match else None,
        }

    if any(normalize_intent_text(keyword) in normalized for keyword in summarize_keywords):
        if named_files:
            return {
                "intent": RetrievalIntent.SUMMARIZE_NAMED,
                "named_files": named_files,
                "section_hint": chapter_match.group(0) if chapter_match else None,
            }
        if any(normalize_intent_text(keyword) in normalized for keyword in latest_keywords):
            return {
                "intent": RetrievalIntent.SUMMARIZE_LATEST,
                "named_files": [],
                "section_hint": chapter_match.group(0) if chapter_match else None,
            }

    return {
        "intent": RetrievalIntent.SEMANTIC_QA,
        "named_files": named_files,
        "section_hint": chapter_match.group(0) if chapter_match else None,
    }


def resolve_compare_target_filenames(query: str, available_filenames: Optional[List[str]] = None) -> List[str]:
    normalized_query = normalize_intent_text(query)
    filenames = available_filenames or []
    if not filenames:
        return []

    arabic_markers = ["ملف عربي", "الملف العربي", "العربي", "وثيقه عربيه", "وثيقة عربية"]
    english_markers = ["ملف انجليزي", "الملف الانجليزي", "الانجليزي", "وثيقه انجليزيه", "وثيقة انجليزية"]

    def looks_arabic_file(name: str) -> bool:
        normalized_name = normalize_intent_text(name)
        return bool(re.search(r"[\u0600-\u06FF]", name)) or "arabic" in normalized_name or " ar " in f" {normalized_name} "

    def looks_english_file(name: str) -> bool:
        normalized_name = normalize_intent_text(name)
        return "english" in normalized_name or " en " in f" {normalized_name} "

    def file_score(name: str) -> int:
        normalized_name = normalize_intent_text(name)
        score = 0
        if looks_arabic_file(name):
            score += 2
        if looks_english_file(name):
            score += 2
        if re.search(r"[\u0600-\u06FF]", name):
            score += 1
        if re.search(r"[A-Za-z]", name):
            score += 1
        return score

    chosen: List[str] = []
    if any(marker in normalized_query for marker in arabic_markers):
        arabic_candidates = [
            filename
            for filename in filenames
            if looks_arabic_file(filename)
        ]
        if arabic_candidates:
            chosen.append(max(arabic_candidates, key=file_score))

    if any(marker in normalized_query for marker in english_markers):
        english_candidates = [
            filename
            for filename in filenames
            if looks_english_file(filename)
        ]
        if english_candidates:
            english_match = max(english_candidates, key=file_score)
            if english_match not in chosen:
                chosen.append(english_match)

    if len(chosen) < 2:
        latest_keywords = ["اخر ملفين", "احدث ملفين", "last two", "latest two"]
        if any(keyword in normalized_query for keyword in latest_keywords):
            remaining = [filename for filename in filenames if filename not in chosen]
            chosen += remaining[: 2 - len(chosen)]

    return chosen


def refers_to_generic_uploaded_document(query: str) -> bool:
    normalized_query = normalize_intent_text(query)
    generic_uploaded_markers = [
        "uploaded file",
        "uploaded document",
        "the uploaded file",
        "the uploaded document",
        "الملف المرفوع",
        "الوثيقة المرفوعة",
        "المرفوع",
    ]
    return any(
        normalize_intent_text(marker) in normalized_query
        for marker in generic_uploaded_markers
    )


class RAGChatbot:
    """RAG-based chatbot that answers questions using indexed company documents."""

    def __init__(self, vs_manager: Optional[VectorStoreManager] = None):
        self.vs_manager = vs_manager or VectorStoreManager()

        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required to initialize the chatbot.")

        self.llm = ChatOpenAI(
            model_name=settings.LLM_MODEL,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
        )
        logger.info("RAG Chatbot initialized")

    def retrieve_context(self, query: str, user_id: Optional[str] = None) -> Tuple[str, List[dict]]:
        logger.info("Searching for: %s", query[:80])
        search_results = self.vs_manager.search_documents(query, user_id=user_id)
        if not search_results:
            logger.warning("No relevant documents found")
            return "", []
        context, sources = self._build_context_from_results(search_results)
        logger.info("Found %s relevant documents", len(sources))
        return context, sources

    def _history_to_messages(self, history: Optional[List[Dict[str, Any]]]) -> List:
        messages: List = []
        for item in history or []:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        return messages[-10:]

    def build_messages(
        self,
        question: str,
        context: str,
        language: str = "en",
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> List:
        messages = [SystemMessage(content=SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["en"]))]
        messages.extend(self._history_to_messages(history))
        formatted_question = PROMPT_TEMPLATE.format(context=context, question=question) if context else question
        response_language_instruction = (
            "أجب باللغة العربية فقط."
            if language == "ar"
            else "Respond in English only."
        )
        formatted_question = f"{response_language_instruction}\n\n{formatted_question}"
        messages.append(HumanMessage(content=formatted_question))
        return messages

    async def stream_chat(
        self,
        user_query: str,
        include_sources: bool = True,
        language: str = "en",
        history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        prefer_full_file_context: bool = False,
        on_response_complete: Optional[Callable[[str], None]] = None,
    ) -> AsyncGenerator[str, None]:
        logger.info("Stream query [%s]: %s", language, user_query[:80])
        try:
            context, sources = await self.retrieve_context_with_filters(
                user_query,
                user_id=user_id,
                file_ids=file_ids,
                prefer_full_file_context=prefer_full_file_context,
            )
            messages = self.build_messages(user_query, context, language, history)

            full_response = ""
            for chunk in self.llm.stream(messages):
                token = chunk.content
                if token:
                    full_response += token
                    yield token

            if on_response_complete:
                try:
                    on_response_complete(full_response)
                except Exception as cb_err:
                    logger.error("on_response_complete callback error: %s", cb_err)

            if include_sources and sources:
                sources_payload = json.dumps(
                    [
                        {
                            "id": f"c{i + 1}",
                            "document": s["source"].split("/")[-1].split("\\")[-1],
                            "page": s.get("page") or 1,
                            "snippet": s["content_preview"],
                            "score": round(s["score"], 2),
                        }
                        for i, s in enumerate(sources)
                    ],
                    ensure_ascii=False,
                )
                yield f"[CITATIONS]{sources_payload}"
        except Exception as e:
            logger.error("Stream error: %s", e)
            if language == "ar":
                yield "عذراً، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى."
            else:
                yield "Sorry, an error occurred while processing your request. Please try again."

    async def chat(
        self,
        user_query: str,
        include_sources: bool = True,
        language: str = "en",
        history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        prefer_full_file_context: bool = False,
    ) -> dict:
        logger.info("Chat query [%s]: %s", language, user_query[:80])
        try:
            context, sources = await self.retrieve_context_with_filters(
                user_query,
                user_id=user_id,
                file_ids=file_ids,
                prefer_full_file_context=prefer_full_file_context,
            )
            messages = self.build_messages(user_query, context, language, history)
            response = self.llm.invoke(messages)
            answer = response.content
            return {
                "answer": answer,
                "sources": sources if include_sources else None,
                "timestamp": datetime.now().isoformat(),
                "context_found": len(sources) > 0,
            }
        except Exception as e:
            logger.error("Error processing query: %s", e)
            return {
                "answer": "Sorry, an error occurred while processing your request.",
                "sources": None,
                "error": str(e),
            }

    def clear_history(self):
        logger.info("Conversation history is client-managed; nothing to clear in memory")

    def get_conversation_summary(self) -> str:
        return "Conversation history is managed per request."

    async def retrieve_context_with_filters(
        self,
        query: str,
        user_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        prefer_full_file_context: bool = False,
    ) -> Tuple[str, List[dict]]:
        logger.info("Searching for: %s", query[:80])

        available_filenames = self.vs_manager.list_user_source_files(user_id=user_id)
        intent_result = detect_retrieval_intent(query, available_filenames=available_filenames)
        intent = intent_result["intent"]
        named_files = intent_result["named_files"]

        resolved_file_ids = list(file_ids or [])
        if named_files:
            named_file_ids = self.vs_manager.get_file_ids_by_source_files(
                user_id=user_id,
                source_files=named_files,
            )
            for file_id in named_file_ids:
                if file_id not in resolved_file_ids:
                    resolved_file_ids.append(file_id)

        if intent == RetrievalIntent.COMPARE and len(resolved_file_ids) < 2:
            compare_target_filenames = resolve_compare_target_filenames(query, available_filenames=available_filenames)
            if compare_target_filenames:
                compare_file_ids = self.vs_manager.get_file_ids_by_source_files(
                    user_id=user_id,
                    source_files=compare_target_filenames,
                )
                for file_id in compare_file_ids:
                    if file_id not in resolved_file_ids:
                        resolved_file_ids.append(file_id)

        if intent == RetrievalIntent.SUMMARIZE_LATEST:
            latest_file_id = self.vs_manager.get_latest_file_id(user_id=user_id)
            if not latest_file_id:
                logger.warning("Qdrant latest document lookup failed for user %s, falling back to DB", user_id)
                latest_file_id = await self.vs_manager.get_latest_file_id_from_db(user_id=user_id)
            if not latest_file_id:
                logger.warning("No latest document found for user %s", user_id)
                return "", []
            documents = self.vs_manager.get_documents_by_file_ids(user_id=user_id, file_ids=[latest_file_id])
            return self._build_context_from_documents(documents)

        if intent in {RetrievalIntent.SUMMARIZE_NAMED, RetrievalIntent.GENERATE_QUESTIONS}:
            if not resolved_file_ids:
                if intent == RetrievalIntent.GENERATE_QUESTIONS and refers_to_generic_uploaded_document(query):
                    latest_file_id = self.vs_manager.get_latest_file_id(user_id=user_id)
                    if not latest_file_id:
                        logger.warning(
                            "Qdrant latest document lookup failed for question generation, falling back to DB for user %s",
                            user_id,
                        )
                        latest_file_id = await self.vs_manager.get_latest_file_id_from_db(user_id=user_id)
                    if latest_file_id:
                        resolved_file_ids.append(latest_file_id)

            if not resolved_file_ids:
                logger.warning("Document-scoped intent detected but no matching file was found")
                return "", []
            documents = self.vs_manager.get_documents_by_file_ids(
                user_id=user_id,
                file_ids=resolved_file_ids,
            )
            return self._build_context_from_documents(documents)

        if intent == RetrievalIntent.COMPARE:
            if len(resolved_file_ids) < 2:
                logger.warning("Compare intent detected without at least two matching documents")
                return "", []
            merged_results: List[Tuple[Any, float]] = []
            for compare_file_id in resolved_file_ids:
                file_results = self.vs_manager.search_documents(
                    query,
                    top_k=max(settings.TOP_K_DOCUMENTS, 4),
                    threshold=0.0,
                    user_id=user_id,
                    file_ids=[compare_file_id],
                )
                merged_results.extend(file_results)
            if not merged_results:
                logger.warning("No comparison results found")
                return "", []
            return self._build_context_from_results(merged_results)

        if prefer_full_file_context and resolved_file_ids:
            context, sources = self.retrieve_full_file_context(
                query,
                user_id=user_id,
                file_ids=resolved_file_ids,
            )
            if context:
                logger.info("Using direct file context for %s matched file(s)", len(resolved_file_ids))
                return context, sources

        search_results = self.vs_manager.search_documents(
            query,
            user_id=user_id,
            file_ids=resolved_file_ids or None,
        )
        if not search_results:
            logger.warning("No relevant documents found")
            return "", []
        context, sources = self._build_context_from_results(search_results)
        logger.info("Semantic QA found %s relevant documents", len(sources))
        return context, sources

    def retrieve_full_file_context(
        self,
        query: str,
        user_id: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
    ) -> Tuple[str, List[dict]]:
        if not file_ids:
            return "", []

        direct_documents = self.vs_manager.get_documents_by_file_ids(user_id=user_id, file_ids=file_ids)
        if not direct_documents:
            return "", []

        relevant_results = self.vs_manager.search_documents(
            query,
            top_k=max(settings.TOP_K_DOCUMENTS, settings.FILE_CONTEXT_TOP_K),
            threshold=0.0,
            user_id=user_id,
            file_ids=file_ids,
        )

        merged_results: List[Tuple[Any, float]] = []
        seen_keys = set()

        def add_result(doc: Any, score: float) -> None:
            doc_key = (
                str(doc.metadata.get("file_id", "")),
                int(doc.metadata.get("page_number") or 1),
                int(doc.metadata.get("chunk_index") or 0),
            )
            if doc_key in seen_keys:
                return
            seen_keys.add(doc_key)
            merged_results.append((doc, score))

        for doc in direct_documents[: settings.FILE_CONTEXT_LEAD_CHUNKS]:
            add_result(doc, 1.0)

        for doc, score in relevant_results:
            add_result(doc, float(score))

        context_parts: List[str] = []
        sources: List[dict] = []
        current_chars = 0
        for doc, score in merged_results:
            source_name = doc.metadata.get("source_file", doc.metadata.get("source", "Unknown"))
            page_number = int(doc.metadata.get("page_number") or doc.metadata.get("page") or 1)
            part = f"[Source: {source_name} | Page: {page_number}]\n{doc.page_content}"
            if context_parts and current_chars + len(part) > settings.FILE_CONTEXT_MAX_CHARS:
                break
            context_parts.append(part)
            current_chars += len(part)
            sources.append(
                {
                    "source": source_name,
                    "page": page_number,
                    "score": float(score),
                    "content_preview": doc.page_content[:150],
                }
            )

        if not context_parts:
            return "", []
        return "\n---\n".join(context_parts), sources

    def _build_context_from_documents(self, documents: List[Any]) -> Tuple[str, List[dict]]:
        if not documents:
            return "", []

        context_parts: List[str] = []
        sources: List[dict] = []
        for doc in documents:
            source_name = doc.metadata.get("source_file") or doc.metadata.get("source", "Unknown")
            page_number = int(doc.metadata.get("page_number") or doc.metadata.get("page") or 1)
            context_parts.append(f"[Source: {source_name} | Page: {page_number}]\n{doc.page_content}")
            sources.append(
                {
                    "source": source_name,
                    "page": page_number,
                    "score": 1.0,
                    "content_preview": doc.page_content[:150],
                }
            )

        return "\n---\n".join(context_parts), sources

    def _build_context_from_results(self, search_results: List[Tuple[Any, float]]) -> Tuple[str, List[dict]]:
        context_parts: List[str] = []
        sources: List[dict] = []
        for doc, score in search_results:
            source_name = doc.metadata.get("source_file") or doc.metadata.get("source", "Unknown")
            page_number = int(doc.metadata.get("page_number") or doc.metadata.get("page") or 1)
            context_parts.append(f"[Source: {source_name} | Page: {page_number}]\n{doc.page_content}")
            sources.append(
                {
                    "source": source_name,
                    "page": page_number,
                    "score": float(score),
                    "content_preview": doc.page_content[:150],
                }
            )
        return "\n---\n".join(context_parts), sources
