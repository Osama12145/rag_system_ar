"""
rag_pipeline.py - RAG Pipeline
Combines retrieval and generation for document-based Q&A.
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from typing import List, Tuple, Generator, Optional, Callable
import logging
from datetime import datetime
from config import settings
from vector_store import VectorStoreManager

logger = logging.getLogger(__name__)

# Language-specific system prompts
SYSTEM_PROMPTS = {
    "ar": (
        "أنت مساعد شركة ذكي ومفيد. "
        "أجب على الأسئلة فقط بناءً على وثائق الشركة المقدمة. "
        "إذا لم تجد الإجابة في الوثائق، قل: 'لم أجد معلومات حول هذا الموضوع في وثائق الشركة.' "
        "لا تخترع معلومات أبداً. كن موجزاً ومهنياً وأجب دائماً باللغة العربية."
    ),
    "en": (
        "You are a helpful company assistant. "
        "Answer questions ONLY based on the provided company documents. "
        "If you can't find the answer in the documents, say: "
        "'I couldn't find information about this topic in the company documents.' "
        "NEVER make up information. Be concise and professional. Always respond in English."
    ),
}

# RAG prompt template (language-agnostic wrapper)
PROMPT_TEMPLATE = PromptTemplate(
    input_variables=["context", "question"],
    template="""Context from company documents:
{context}

User question:
{question}

Answer based strictly on the context above:""",
)


class RAGChatbot:
    """
    RAG-based Chatbot that answers questions using company documents.
    """

    def __init__(self, vs_manager: VectorStoreManager = None):
        self.vs_manager = vs_manager or VectorStoreManager()

        # Initialize LLM via OpenRouter
        self.llm = ChatOpenAI(
            model_name=settings.LLM_MODEL,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
        )

        self.conversation_history: List = []
        logger.info("RAG Chatbot initialized")

    def retrieve_context(self, query: str) -> Tuple[str, List[dict]]:
        """Retrieve relevant context from the document store."""
        logger.info(f"Searching for: {query[:80]}")
        search_results = self.vs_manager.search_documents(query)

        if not search_results:
            logger.warning("No relevant documents found")
            return "", []

        context_parts = []
        sources = []

        for doc, score in search_results:
            source_name = doc.metadata.get("source", "Unknown")
            context_parts.append(f"[Source: {source_name}]\n{doc.page_content}")
            sources.append(
                {
                    "source": source_name,
                    "score": float(score),
                    "content_preview": doc.page_content[:150],
                }
            )

        context = "\n---\n".join(context_parts)
        logger.info(f"Found {len(sources)} relevant documents")
        return context, sources

    def build_messages(self, question: str, context: str, language: str = "en") -> List:
        """Build the message list for the LLM."""
        messages = []

        # Language-specific system prompt
        system_prompt = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["en"])
        messages.append(SystemMessage(content=system_prompt))

        # Recent conversation history (last 10 messages = 5 exchanges)
        recent_history = self.conversation_history[-10:]
        messages.extend(recent_history)

        # Current question with context
        if context:
            formatted_question = PROMPT_TEMPLATE.format(context=context, question=question)
        else:
            formatted_question = question

        messages.append(HumanMessage(content=formatted_question))
        return messages

    def stream_chat(
        self,
        user_query: str,
        include_sources: bool = True,
        language: str = "en",
        on_response_complete: Optional[Callable[[str], None]] = None,
    ) -> Generator[str, None, None]:
        """
        Stream the response chunk by chunk.
        Yields text chunks, then optionally ends with [CITATIONS]{...} JSON.

        Args:
            on_response_complete: Optional callback invoked with the full AI response
                after streaming completes (before the CITATIONS payload, if any).
        """
        logger.info(f"Stream query [{language}]: {user_query[:80]}")
        try:
            import json

            context, sources = self.retrieve_context(user_query)
            messages = self.build_messages(user_query, context, language)

            self.conversation_history.append(HumanMessage(content=user_query))

            full_response = ""
            for chunk in self.llm.stream(messages):
                token = chunk.content
                if token:
                    full_response += token
                    yield token

            self.conversation_history.append(AIMessage(content=full_response))

            # Invoke completion callback (e.g., persist to DB) before sending citations
            if on_response_complete:
                try:
                    on_response_complete(full_response)
                except Exception as cb_err:
                    logger.error(f"on_response_complete callback error: {cb_err}")

            if include_sources and sources:
                sources_payload = json.dumps(
                    [
                        {
                            "id": f"c{i + 1}",
                            "document": s["source"].split("/")[-1].split("\\")[-1],
                            "page": 1,
                            "snippet": s["content_preview"],
                            "score": round(s["score"], 2),
                        }
                        for i, s in enumerate(sources)
                    ],
                    ensure_ascii=False,
                )
                yield f"[CITATIONS]{sources_payload}"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            if language == "ar":
                yield "عذراً، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى."
            else:
                yield "Sorry, an error occurred while processing your request. Please try again."

    def chat(self, user_query: str, include_sources: bool = True, language: str = "en") -> dict:
        """Synchronous chat — collects the full streamed response."""
        logger.info(f"Chat query [{language}]: {user_query[:80]}")
        try:
            context, sources = self.retrieve_context(user_query)
            messages = self.build_messages(user_query, context, language)
            response = self.llm.invoke(messages)
            answer = response.content

            self.conversation_history.append(HumanMessage(content=user_query))
            self.conversation_history.append(AIMessage(content=answer))

            return {
                "answer": answer,
                "sources": sources if include_sources else None,
                "timestamp": datetime.now().isoformat(),
                "context_found": len(sources) > 0,
            }
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "answer": "Sorry, an error occurred while processing your request.",
                "sources": None,
                "error": str(e),
            }

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
        logger.info("Conversation history cleared")

    def get_conversation_summary(self) -> str:
        """Get a readable summary of the current conversation."""
        lines = ["Conversation Summary:"]
        for msg in self.conversation_history:
            if isinstance(msg, HumanMessage):
                lines.append(f"  User: {msg.content[:100]}...")
            elif isinstance(msg, AIMessage):
                lines.append(f"  Bot:  {msg.content[:100]}...")
        return "\n".join(lines)
