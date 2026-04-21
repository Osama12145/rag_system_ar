"""
app_streamlit.py — Streamlit Frontend for Arabic RAG Chatbot
Connects to the FastAPI backend via BACKEND_URL environment variable.

Run locally:
    streamlit run app_streamlit.py

Deploy (Docker):
    BACKEND_URL=http://localhost:8000 streamlit run app_streamlit.py
"""

import os
import json
import requests
from typing import List, Dict, Any, Optional
import streamlit as st

# ── Backend Configuration ────────────────────────────────────────────────────

# BACKEND_URL should point to the FastAPI service
# Local dev: http://localhost:8000  (default)
# Docker compose (injected into container): http://api:8000
# Coolify: set via environment variable accordingly
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL.rstrip('/')}/api"

# Session state keys
SESSION_KEY = "rag_chat_messages"
SESSION_ID_KEY = "rag_session_id"

# Set page config FIRST (required by Streamlit)
st.set_page_config(
    page_title="Company Intelligence RAG",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Language Detection ───────────────────────────────────────────────────────
# LANG can be "en" or "ar" — controls UI labels
UI_LANG = os.getenv("LANG", "en").lower()
if UI_LANG not in ("en", "ar"):
    UI_LANG = "en"


# ── Translation Strings ──────────────────────────────────────────────────────

T = {
    "en": {
        "title": "Company Intelligence Chat",
        "subtitle": "Ask questions about company documents",
        "input_placeholder": "Type your question here...",
        "language": "Language",
        "search_placeholder": "Search chat history...",
        "clear_chat": "Clear Chat",
        "no_docs": "No documents indexed yet.",
        "status_healthy": "● Connected",
        "status_unhealthy": "● Disconnected",
        "page_chat": "💬 Chat",
        "page_library": "📚 Documents",
        "upload_title": "Upload Documents",
        "upload_help": "Select PDF, DOCX, or TXT files (max 50 MB each)",
        "upload_btn": "Upload & Index",
        "uploading": "Indexing in progress...",
        "doc_name": "Name",
        "doc_size": "Size",
        "doc_pages": "Pg",
        "doc_chunks": "Chk",
        "doc_uploaded": "Date",
        "doc_status": "Status",
        "status_ready": "✅ Ready",
        "status_indexing": "⏳ Indexing",
        "status_error": "❌ Error",
        "error_disconnected": "Backend unreachable — check API server status.",
        "usage_title": "📊 Usage & Statistics",
        "usage_tokens": "Estimated Tokens",
        "usage_qdrant": "Vectors in Qdrant",
        "usage_files": "Indexed Files",
    },
    "ar": {
        "title": "مساعد الشركة الذكي",
        "subtitle": "اطرح أسئلة حول وثائق الشركة",
        "input_placeholder": "اكتب سؤالك هنا...",
        "language": "اللغة",
        "search_placeholder": "بحث في المحادثة...",
        "clear_chat": "مسح المحادثة",
        "no_docs": "لا توجد مستندات مفهرسة بعد.",
        "status_healthy": "● متصل",
        "status_unhealthy": "● غير متصل",
        "page_chat": "💬 محادثة",
        "page_library": "📚 المستندات",
        "upload_title": "رفع مستندات",
        "upload_help": "اختر ملفات PDF أو DOCX أو TXT (حتى 50 ميجابايت لكل ملف)",
        "upload_btn": "رفع وفهرسة",
        "uploading": "جاري الفهرسة...",
        "doc_name": "الاسم",
        "doc_size": "الحجم",
        "doc_pages": "صفح",
        "doc_chunks": "مقاطع",
        "doc_uploaded": "التاريخ",
        "doc_status": "الحالة",
        "status_ready": "✅ جاهز",
        "status_indexing": "⏳ جاري الفهرسة",
        "status_error": "❌ خطأ",
        "error_disconnected": "تعذر الاتصال بالخادم — تحقق من أن API يعمل.",
        "usage_title": "📊 الإحصائيات",
        "usage_tokens": "الرموز المستخدمة",
        "usage_qdrant": "المتجهات في Qdrant",
        "usage_files": "الملفات المفهرسة",
    },
}


def t(key: str, lang: str = UI_LANG) -> str:
    return T.get(lang, T["en"]).get(key, key)


# ── Session State ────────────────────────────────────────────────────────────

if SESSION_KEY not in st.session_state:
    st.session_state[SESSION_KEY] = []
if SESSION_ID_KEY not in st.session_state:
    st.session_state[SESSION_ID_KEY] = None


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Settings")

    # Language selector
    lang = st.radio(
        label=t("language", UI_LANG),
        options=["English", "العربية"],
        index=0 if UI_LANG == "en" else 1,
        horizontal=True,
    )
    # Update UI_LANG based on selection (triggers rerun)
    global UI_LANG
    UI_LANG = "ar" if lang == "العربية" else "en"
    os.environ["LANG"] = UI_LANG

    st.divider()

    # Connection status
    try:
        r = requests.get(f"{API_BASE}/health", timeout=3)
        data = r.json()
        status = "healthy" if data.get("status") in ("healthy", "degraded") else "unhealthy"
    except Exception:
        status = "unhealthy"

    if status == "healthy":
        st.success(t("status_healthy", UI_LANG))
    else:
        st.error(t("status_unhealthy", UI_LANG))

    st.divider()

    # Clear chat button
    if st.button(t("clear_chat", UI_LANG), type="primary", use_container_width=True):
        st.session_state[SESSION_KEY] = []
        st.session_state[SESSION_ID_KEY] = None
        try:
            requests.post(f"{API_BASE}/chat/clear")
        except Exception:
            pass
        st.rerun()


# ── Page Navigation ──────────────────────────────────────────────────────────

# Build page list dynamically so language switch re-runs with new labels
pages = [
    st.Page("app_chat.py", icon="💬", title=t("page_chat", UI_LANG)),
    st.Page("app_library.py", icon="📚", title=t("page_library", UI_LANG)),
]
page = st.navigation(pages)
page.run()
