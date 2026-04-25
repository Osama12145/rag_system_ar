"""
rag_pipeline.py - RAG Pipeline
Combines retrieval and generation for document-based Q&A.
"""

from datetime import datetime
import json
import logging
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

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
        "لا تخترع معلومات أبدا. كن موجزا ومهنيا وأجب دائما باللغة العربية."
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
        """Retrieve relevant context from the document store."""
        logger.info("Searching for: %s", query[:80])
        search_results = self.vs_manager.search_documents(query, user_id=user_id)

        if not search_results:
            logger.warning("No relevant documents found")
            return "", []

        context_parts: List[str] = []
        sources: List[dict] = []

        for doc, score in search_results:
            source_name = doc.metadata.get("source", "Unknown")
            context_parts.append(f"[Source: {source_name}]\n{doc.page_content}")
            sources.append(
                {
                    "source": source_name,
                    "page": doc.metadata.get("page"),
                    "score": float(score),
                    "content_preview": doc.page_content[:150],
                }
            )

        context = "\n---\n".join(context_parts)
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
        """Build the message list for the LLM."""
        messages = [SystemMessage(content=SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["en"]))]
        messages.extend(self._history_to_messages(history))

        formatted_question = (
            PROMPT_TEMPLATE.format(context=context, question=question) if context else question
        )
        messages.append(HumanMessage(content=formatted_question))
        return messages

    def stream_chat(
        self,
        user_query: str,
        include_sources: bool = True,
        language: str = "en",
        history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        on_response_complete: Optional[Callable[[str], None]] = None,
    ) -> Generator[str, None, None]:
        """
        Stream the response chunk by chunk.
        Yields text chunks, then optionally ends with [CITATIONS]{...} JSON.
        """
        logger.info("Stream query [%s]: %s", language, user_query[:80])
        try:
            context, sources = self.retrieve_context(user_query, user_id=user_id)
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
                yield "عذرا، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى."
            else:
                yield "Sorry, an error occurred while processing your request. Please try again."

    def chat(
        self,
        user_query: str,
        include_sources: bool = True,
        language: str = "en",
        history: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
    ) -> dict:
        """Synchronous chat that collects the full streamed response."""
        logger.info("Chat query [%s]: %s", language, user_query[:80])
        try:
            context, sources = self.retrieve_context(user_query, user_id=user_id)
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
        """Compatibility method retained for API callers."""
        logger.info("Conversation history is client-managed; nothing to clear in memory")

    def get_conversation_summary(self) -> str:
        """Compatibility method retained for API callers."""
        return "Conversation history is managed per request."
