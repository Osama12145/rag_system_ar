"""
app_chat.py — Streamlit Chat Interface
Displays conversation history and handles user queries.
"""

import os
import json
import requests
from typing import List, Dict, Any
import streamlit as st

# ── Backend URL ───────────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL.rstrip('/')}/api"

# ── Translation strings ───────────────────────────────────────────────────────
LANG = os.getenv("LANG", "en")
T = {
    "en": {
        "title": "Chat",
        "input_placeholder": "Type your question here...",
        "clear_chat": "Clear Chat",
    },
    "ar": {
        "title": "محادثة",
        "input_placeholder": "اكتب سؤالك هنا...",
        "clear_chat": "مسح المحادثة",
    },
}
def tt(key: str) -> str:
    return T.get(LANG, T["en"]).get(key, key)


# ── Session State ────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "session_id" not in st.session_state:
    st.session_state["session_id"] = None

if "last_citations" not in st.session_state:
    st.session_state["last_citations"] = []


# ── API Helpers ───────────────────────────────────────────────────────────────

def send_chat_message(message: str, session_id: str = None, language: str = LANG):
    payload = {
        "message": message,
        "sourceCheck": True,
        "deepResearch": False,
        "reasoning": False,
        "language": language,
        "sessionId": session_id,
    }
    r = requests.post(f"{API_BASE}/chat", json=payload, stream=True, timeout=90)
    r.raise_for_status()
    full = ""
    for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
        if chunk:
            full += chunk
            yield chunk
    # Extract trailing citations if present
    if "[CITATIONS]" in full:
        try:
            parts = full.split("[CITATIONS]", 1)
            if len(parts) > 1:
                st.session_state["last_citations"] = json.loads(parts[1])
        except Exception:
            pass


def load_history(session_id: str = None):
    try:
        params = {"session_id": session_id} if session_id else {}
        r = requests.get(f"{API_BASE}/chat/history", params=params, timeout=10)
        if r.ok:
            data = r.json()
            return data.get("history", []), data.get("session_id")
    except Exception as e:
        st.error(f"Failed to load history: {e}")
    return [], None


# ── Page ─────────────────────────────────────────────────────────────────────
st.title(tt("title"))


# Load existing history on first run
if not st.session_state["messages"]:
    history, sess_id = load_history()
    for msg in history:
        st.session_state["messages"].append({
            "role": msg["role"],
            "content": msg["content"],
        })
    if sess_id:
        st.session_state["session_id"] = sess_id


# ── Render Chat ───────────────────────────────────────────────────────────────
chat_container = st.container()

with chat_container:
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Citations after last AI response
    if st.session_state.get("last_citations"):
        with st.expander(f"📎 Sources ({len(st.session_state['last_citations'])} docs)"):
            for c in st.session_state["last_citations"]:
                st.markdown(
                    f"**{c['document']}** — score: {c.get('score', 'N/A')}\n\n"
                    f"> {c['snippet']}"
                )

# ── Input ─────────────────────────────────────────────────────────────────────
if prompt := st.chat_input(tt("input_placeholder")):
    # User message
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with chat_container:
        with st.chat_message("user"):
            st.write(prompt)

    # Assistant response
    with chat_container:
        with st.chat_message("assistant"):
            full = st.write_stream(
                send_chat_message(
                    message=prompt,
                    session_id=st.session_state["session_id"],
                    language=LANG,
                )
            )

    st.session_state["messages"].append({"role": "assistant", "content": full})
    st.rerun()
