# 🚀 Coolify Deployment Guide — Arabic RAG Chatbot

This guide covers deploying the Arabic RAG Chatbot on Coolify using the **dual-container architecture**:
- **Backend**: FastAPI (`api` service)
- **Frontend**: Streamlit (`streamlit` service)
- **Databases**: External PostgreSQL & Qdrant (already provisioned in Coolify)

---

## 📦 Prerequisites

1. Two Coolify resources already created:
   - `postgresql-database-x0kwsk40gs4ccog84gccc04g` — PostgreSQL instance
   - `qdrant-eso00kc0k8ww0k4g00wkcw0g` — Qdrant vector database
2. Your API keys ready: `OPENROUTER_API_KEY`, `COHERE_API_KEY`, (optional `LANGCHAIN_API_KEY`)

---

## 🐳 Docker Images in Coolify

You will create **two separate services** in Coolify:

| Service  | Dockerfile      | Port | Healthcheck URL           |
|----------|-----------------|------|---------------------------|
| Backend  | `Dockerfile.backend` | 8000 | `http://localhost:8000/health` |
| Frontend | `Dockerfile.frontend`| 8501 | `http://localhost:8501/_stcore/health` |

---

## 🎯 Step-by-Step Setup

### 1. Repository Setup

Push your code to a Git repository (GitHub, GitLab, or Bitbucket). Ensure these files are in the repo root:
- `api_server.py`
- `rag_pipeline.py`
- `vector_store.py`
- `document_processor.py`
- `config.py`
- `database.py`
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `app_streamlit.py`, `app_chat.py`, `app_library.py`
- `requirements.txt`
- `.env.example`

### 2. Create Backend Service in Coolify

1. **Sources** → Add service → **Build from Git**
2. Repository: Select your RAG chatbot repo
3. **Build Settings → Dockerfile**:
   - Dockerfile path: `Dockerfile.backend`
   - Build context: `/` (repo root)
4. **Instance Settings → Ports**:
   - Port: `8000`
5. **Environment Variables** (add these):

| Key                        | Value (example)                                                                 |
|----------------------------|---------------------------------------------------------------------------------|
| `OPENROUTER_API_KEY`       | `sk-or-v1-...` (your actual key)                                               |
| `COHERE_API_KEY`           | `I4qBZs7...`                                                                   |
| `QDRANT_URL`               | `http://qdrant-eso00kc0k8ww0k4g00wkcw0g:6333`                                 |
| `QDRANT_COLLECTION_NAME`   | `company-documents`                                                            |
| `DATABASE_URL`             | `postgresql+asyncpg://postgres:YOUR_PASSWORD@postgresql-database-xxxx:5432/chatbot_db` |
| `LANGCHAIN_TRACING_V2`     | `true` (optional)                                                              |
| `LANGCHAIN_API_KEY`        | (optional, your LangSmith key)                                                |
| `ALLOWED_ORIGINS`          | `http://localhost:3000,http://YOUR_FRONTEND_DOMAIN:8501`                      |
| `BACKEND_URL`              | `http://localhost:8000` (internal reference for app)                          |

6. **Healthcheck**:
   - Path: `/health`
   - Interval: `30s`
7. **Deploy** the backend service.

### 3. Create Frontend Service in Coolify

1. **Sources** → Add service → **Build from Git**
2. Repository: the **same repo** as above
3. **Build Settings → Dockerfile**:
   - Dockerfile path: `Dockerfile.frontend`
   - Build context: `/`
4. **Instance Settings → Ports**:
   - Port: `8501`
5. **Environment Variables**:

| Key           | Value                                     |
|---------------|-------------------------------------------|
| `BACKEND_URL` | `http://api.internal:8000` (or your backend's internal URL) |
| `LANG`        | `en` (or `ar` for Arabic)                |

6. **Healthcheck**:
   - Path: `/_stcore/health`
   - Interval: `30s`
7. **Deploy** the frontend service.

### 4. Configure Dependencies

In the **Frontend service** settings:
- **Dependencies** (or "Depends On"): Add `api` service and select:
  - **Condition**: `service_healthy`
  - **Restart**: `restart`

Or via **docker-compose overrides** in Coolify:

```yaml
services:
  frontend:
    depends_on:
      api:
        condition: service_healthy
```

---

## 🔐 Environment Variables — Summary

### Backend (`api`) service

```bash
# Required — LLM & Embeddings provider keys
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxx
COHERE_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Required — External databases (replace with your Coolify resource URLs/credentials)
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@postgresql-database-x0kwsk40gs4ccog84gccc04g:5432/chatbot_db
QDRANT_URL=http://qdrant-eso00kc0k8ww0k4g00wkcw0g:6333

# Optional — Observability
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
LANGCHAIN_PROJECT=company-intelligence-rag

# Required — CORS (add your frontend's URL)
ALLOWED_ORIGINS=http://localhost:8501,https://your-custom-domain.com
```

### Frontend (`streamlit`) service

```bash
# Required — Backend location
BACKEND_URL=http://api.internal:8000
# Or externally: BACKEND_URL=https://api.your-domain.com

# Optional — Language default
LANG=en
```

---

## 🔍 Verification Checklist

After deployment:

- [ ] **Backend**: `GET /health` returns `{"status": "healthy", "db_connected": true, ...}`
- [ ] **Frontend**: Streamlit loads (port 8501), shows "Connected" in sidebar
- [ ] **Upload** a PDF → document appears in Library → chat works
- [ ] **Chat history** persists after page refresh
- [ ] **Database**: PostgreSQL `chat_history` table grows with messages
- [ ] **Qdrant**: Vector count increases in your Coolify resource dashboard

---

## 🛠️ Troubleshooting

### Backend won't start → `database.py` import error
- Ensure `asyncpg` is in `requirements.txt`
- Rebuild the image in Coolify (clear build cache if needed)

### Backend healthcheck fails
- Check that `DATABASE_URL` format is correct:
  ```
  postgresql+asyncpg://user:password@host:port/dbname
  ```
  (note: the driver is `postgresql+asyncpg`, not just `postgresql`)
- Verify the PostgreSQL resource allows connections from the backend service (network policies in Coolify)

### Frontend shows "Backend unreachable"
- Check `BACKEND_URL` points to the backend's **internal** URL (`http://api:8000`) or **external** URL
- In Coolify, use the internal network name (shown in "Internal URL" for the service)

### CORS errors in browser
- Add your frontend domain to `ALLOWED_ORIGINS` in backend env vars
- Restart backend after changing CORS

### Uploads succeed but Library is empty
- Check `file_metadata` table in PostgreSQL has rows
- If backend logs show `DB insert failed`, verify `DATABASE_URL` credentials

### Chat history lost after refresh
- The `chat_history` table is being written — check PostgreSQL table
- `restore_conversation()` loads last 20 turns on startup

---

## 📁 Project Structure after Refactor

```
arabic-rag-chatbot/
├── api_server.py           # FastAPI app (dual-persistence)
├── database.py             # SQLAlchemy async models & session mgmt
├── rag_pipeline.py         # RAG chatbot with chat-history restoration
├── vector_store.py         # Qdrant client (local or remote)
├── document_processor.py   # PDF/DOCX/TXT loader
├── config.py               # Settings from .env
├── requirements.txt        # Python deps (FastAPI + Streamlit)
│
├── Dockerfile.backend      # Multi-stage build for FastAPI
├── Dockerfile.frontend     # Multi-stage build for Streamlit
├── docker-compose.yml      # Local dev setup (api + streamlit)
│
├── app_streamlit.py        # Streamlit entry point
├── app_chat.py             # Chat page component
├── app_library.py          # Library page component
│
├── .env                    # Your secrets (never commit)
├── .env.example            # Template for env setup
└── COOLIFY.md              # This file — Coolify deployment notes
```

---

## 🧪 Local Testing (Before Push)

```bash
# 1. Create local Docker network equivalent
docker-compose up -d          # uses docker-compose.yml (pulls your local DB if needed)

# 2. Test API directly
curl http://localhost:8000/health

# 3. Test Streamlit frontend
open http://localhost:8501
```

---

## 📊 Coolify Resource Naming

Your Coolify resource names:
- **PostgreSQL**: `postgresql-database-x0kwsk40gs4ccog84gccc04g`
  - Internal URL: `postgresql-database-x0kwsk40gs4ccog84gccc04g:5432`
  - Construct `DATABASE_URL` as:
    ```
    postgresql+asyncpg://postgres:<PASSWORD>@postgresql-database-x0kwsk40gs4ccog84gccc04g:5432/chatbot_db
    ```
- **Qdrant**: `qdrant-eso00kc0k8ww0k4g00wkcw0g`
  - Internal URL: `http://qdrant-eso00kc0k8ww0k4g00wkcw0g:6333`

Coolify automatically injects these internal URLs into your service's DNS — use them in `DATABASE_URL` and `QDRANT_URL`.

---

## 🔄 Updates & Rollbacks

Coolify provides:
- **Rollbacks**: Service → Rollback to previous deployment
- **Rolling updates**: Set "Rolling update" strategy to avoid downtime
- **Healthchecks**: Backend `health` endpoint ensures only healthy instances serve traffic

---

**Need help?** Check the backend logs in Coolify → Logs tab. Frontend logs appear under the Streamlit service.
