"""
app_library.py — Streamlit Document Library Page
Lists indexed files and handles file uploads.
"""

import os
import json
import requests
from typing import Dict, Any
import streamlit as st

# ── Backend URL ───────────────────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL.rstrip('/')}/api"

LANG = os.getenv("LANG", "en")
T = {
    "en": {
        "title": "Document Library",
        "upload_title": "Upload Documents",
        "upload_help": "Select PDF, DOCX, or TXT files (max 50 MB each)",
        "no_docs": "No documents indexed yet.",
        "doc_name": "Name",
        "doc_size": "Size",
        "doc_pages": "Pages",
        "doc_chunks": "Chunks",
        "doc_uploaded": "Date",
        "doc_status": "Status",
        "status_ready": "✅ Ready",
        "status_indexing": "⏳ Indexing",
        "status_error": "❌ Error",
        "usage_title": "📊 Usage & Statistics",
        "usage_tokens": "Tokens (est.)",
        "usage_qdrant": "Vectors",
        "usage_files": "Files",
    },
    "ar": {
        "title": "مكتبة المستندات",
        "upload_title": "رفع مستندات",
        "upload_help": "اختر ملفات PDF أو DOCX أو TXT (حتى 50 ميجابايت)",
        "no_docs": "لا توجد مستندات مفهرسة بعد.",
        "doc_name": "الاسم",
        "doc_size": "الحجم",
        "doc_pages": "الصفحات",
        "doc_chunks": "المقاطع",
        "doc_uploaded": "التاريخ",
        "doc_status": "الحالة",
        "status_ready": "✅ جاهز",
        "status_indexing": "⏳ جاري الفهرسة",
        "status_error": "❌ خطأ",
        "usage_title": "📊 الإحصائيات",
        "usage_tokens": "الرموز (تقديري)",
        "usage_qdrant": "المتجهات",
        "usage_files": "الملفات",
    },
}
def tt(key: str) -> str:
    return T.get(LANG, T["en"]).get(key, key)


# ── API Helpers ───────────────────────────────────────────────────────────────
def list_documents():
    try:
        r = requests.get(f"{API_BASE}/documents", timeout=10)
        return r.json() if r.ok else []
    except Exception:
        return []


def upload_file(file):
    files = {"files": (file.name, file, file.type or "application/octet-stream")}
    r = requests.post(f"{API_BASE}/documents/upload", files=files, timeout=60)
    r.raise_for_status()
    return r.json()


# ── Page ──────────────────────────────────────────────────────────────────────
st.title(tt("title"))


# Upload section
st.subheader(tt("upload_title"))
uploaded = st.file_uploader(
    label=tt("upload_help"),
    type=["pdf", "txt", "docx"],
    accept_multiple_files=True,
)

if uploaded:
    for f in uploaded:
        with st.spinner(f"Indexing {f.name}..."):
            try:
                result = upload_file(f)
                if result.get("success"):
                    st.success(f"✅ {f.name} — Indexed successfully")
                else:
                    st.error(f"❌ {f.name} — {result.get('message', 'Upload failed')}")
            except requests.HTTPError as e:
                err = e.response.json().get("detail", str(e)) if e.response else str(e)
                st.error(f"❌ {f.name} — {err}")
            except Exception as e:
                st.error(f"❌ {f.name} — {e}")
    st.rerun()

st.divider()


# Document list
docs = list_documents()

if not docs:
    st.info(tt("no_docs"))
else:
    for d in docs:
        status_label = (
            tt("status_ready") if d.get("status") == "ready"
            else tt("status_indexing") if d.get("status") == "indexing"
            else tt("status_error")
        )
        size_mb = d.get("size", 0) / 1_000_000
        cols = st.columns([3, 1, 1, 1, 2])
        cols[0].write(f"**{d.get('name', '')}**")
        cols[1].write(f"{size_mb:.1f} MB")
        cols[2].write(str(d.get("pages", 0)))
        cols[3].write(str(d.get("chunks", 0)))
        cols[4].write(status_label)
        st.divider()

# Usage stats
with st.expander(tt("usage_title")):
    try:
        r = requests.get(f"{API_BASE}/usage", timeout=5)
        if r.ok:
            u = r.json()
            c1, c2, c3 = st.columns(3)
            c1.metric(tt("usage_tokens"), f"{u.get('used', 0):,}")
            c2.metric(tt("usage_qdrant"), f"{u.get('qdrant_chunks', 0):,}")
            c3.metric(tt("usage_files"), f"{u.get('db_files', 0):,}")
    except Exception:
        st.caption("Usage data unavailable.")
