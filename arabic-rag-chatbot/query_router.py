"""
query_router.py - Lightweight LLM query router for the document assistant.

The router classifies ambiguous user messages before RAG. It does not answer
the user; it only returns an intent that api_server.py maps to a trusted
handler such as metadata lookup, help text, refusal, or document RAG.
"""

import asyncio
from enum import Enum
import json
import logging
import re
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from config import settings

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    METADATA_STATUS = "metadata_status"
    LATEST_DOCUMENT = "latest_document"
    DOCUMENT_INVENTORY = "document_inventory"
    DOCUMENT_CONTENT = "document_content"
    HELP = "help"
    OUT_OF_SCOPE = "out_of_scope"


class QueryRoute(BaseModel):
    intent: QueryIntent = QueryIntent.DOCUMENT_CONTENT
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    target_file_hint: Optional[str] = None
    reason: str = ""


ROUTER_SYSTEM_PROMPT = """You are a query router for a document intelligence app.

Classify the user's message into exactly one intent:

- metadata_status: asking whether uploaded files are visible, uploaded, ready, indexed, or accessible.
- latest_document: asking about the latest uploaded file/document, or "last file", not asking about its content.
- document_inventory: asking to list available uploaded documents/files.
- document_content: asking about the content of uploaded documents, including summaries, extraction, comparison, questions, or facts in files.
- help: asking how to use the app, what they can ask, or what file types/features are supported.
- out_of_scope: asking for information unrelated to uploaded documents or app usage.

Important:
- Do not answer the user.
- Return only valid JSON.
- If unsure between document_content and another intent, choose document_content.
- Arabic and English are both supported.

JSON shape:
{
  "intent": "metadata_status | latest_document | document_inventory | document_content | help | out_of_scope",
  "confidence": 0.0,
  "target_file_hint": null,
  "reason": "short reason"
}
"""


class QueryRouter:
    def __init__(self):
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY is required to initialize the query router.")

        self.llm = ChatOpenAI(
            model_name=settings.LLM_MODEL,
            temperature=0,
            max_tokens=180,
            openai_api_key=settings.OPENROUTER_API_KEY,
            openai_api_base="https://openrouter.ai/api/v1",
        )

    def _parse_json_object(self, text_value: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(text_value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", text_value, flags=re.DOTALL)
        if not match:
            raise ValueError("Router response did not contain a JSON object")

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("Router JSON was not an object")
        return parsed

    async def classify(self, user_message: str, language: str = "en") -> QueryRoute:
        messages = [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"UI language: {language}\n"
                    f"User message:\n{user_message}\n\n"
                    "Classify this message."
                )
            ),
        ]

        try:
            response = await asyncio.to_thread(self.llm.invoke, messages)
            content = str(response.content or "").strip()
            payload = self._parse_json_object(content)
            return QueryRoute.model_validate(payload)
        except (ValidationError, ValueError, json.JSONDecodeError) as parse_error:
            logger.warning("Query router parse error, falling back to document_content: %s", parse_error)
        except Exception as route_error:
            logger.warning("Query router failed, falling back to document_content: %s", route_error)

        return QueryRoute(
            intent=QueryIntent.DOCUMENT_CONTENT,
            confidence=0.0,
            reason="router_fallback",
        )
