# Coolify Deployment Guide

This repository should be deployed on Coolify as two services from the same Git repo:

- `backend`: FastAPI app from `arabic-rag-chatbot/Dockerfile.backend`
- `frontend`: React app from `arabic-rag-chatbot/Dockerfile.frontend`

The frontend is served by Nginx and proxies `/api/*` and `/health` to the backend over Coolify's internal network. That means the browser talks to a single origin and you avoid CORS headaches.

## 1. Create the Backend Service

- Source: `Build from Git`
- Dockerfile path: `arabic-rag-chatbot/Dockerfile.backend`
- Build context: repo root
- Port: `8000`
- Health check path: `/health`

Required environment variables:

```env
OPENROUTER_API_KEY=...
COHERE_API_KEY=...
QDRANT_URL=http://YOUR_QDRANT_INTERNAL_HOST:6333
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@YOUR_POSTGRES_INTERNAL_HOST:5432/postgres
ALLOWED_ORIGINS=https://YOUR_FRONTEND_DOMAIN
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=company-intelligence-rag
```

Notes:

- `QDRANT_URL` and `DATABASE_URL` must use the Coolify internal hostnames shown on the resource pages.
- Do not use local placeholders like `http://qdrant:6333` unless that is the exact internal hostname Coolify shows for your project.
- If you are using a custom frontend domain, include it in `ALLOWED_ORIGINS`.

## 2. Create the Frontend Service

- Source: `Build from Git`
- Dockerfile path: `arabic-rag-chatbot/Dockerfile.frontend`
- Build context: repo root
- Port: `8080`
- Health check path: `/nginx-health`

Required environment variables:

```env
BACKEND_UPSTREAM=http://YOUR_BACKEND_INTERNAL_HOST:8000
```

Notes:

- `BACKEND_UPSTREAM` must be the Coolify internal URL for the backend service.
- The frontend container does not need `OPENROUTER_API_KEY`, `COHERE_API_KEY`, `QDRANT_URL`, or `DATABASE_URL`.
- The React app uses same-origin requests, and Nginx proxies them to the backend.

## 3. Suggested Coolify Names

- Backend service name: `rag-backend`
- Frontend service name: `rag-frontend`

Example internal URLs often look like:

```text
http://rag-backend:8000
http://qdrant-xxxxxxxx:6333
postgresql+asyncpg://postgres:PASSWORD@postgresql-xxxxxxxx:5432/postgres
```

Use the exact values Coolify shows in your dashboard.

## 4. Verify After Deploy

Backend checks:

- Open `https://YOUR_BACKEND_DOMAIN/health`
- Expected: JSON with `db_connected: true`

Frontend checks:

- Open `https://YOUR_FRONTEND_DOMAIN`
- Upload a `.pdf`, `.txt`, or `.docx`
- Ask a question and confirm a cited answer appears

## 5. Common Problems

### `getaddrinfo failed`

Your `QDRANT_URL` or `DATABASE_URL` host is wrong for Coolify's internal network. Copy the internal hostname directly from Coolify.

### Frontend loads but API calls fail

Check `BACKEND_UPSTREAM` on the frontend service. It should point to the backend's internal URL, not the public domain unless you intentionally want that.

### CORS error

Set the backend `ALLOWED_ORIGINS` to your final frontend domain.

### Backend starts but chat is unavailable

Check:

- `OPENROUTER_API_KEY`
- `COHERE_API_KEY`
- `LLM_MODEL`

The current default model is:

```env
LLM_MODEL=cohere/command-r-plus-08-2024
```

## 6. Local Docker Smoke Test

From `arabic-rag-chatbot/`:

```bash
docker compose up --build
```

Then open:

- Frontend: `http://localhost:8080`
- Backend health: `http://localhost:8000/health`
- Qdrant: `http://localhost:6333`
