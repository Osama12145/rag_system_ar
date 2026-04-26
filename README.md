# Development Guide — Company Intelligence RAG

This document serves as the Source of Truth for the architecture, API, and development procedures of the OS_AI Company Intelligence RAG Platform.

## Project Architecture

The project consists of two core components residing in their respective directories:

1. **Frontend (`query-prism-dash`)**
   - **Stack**: React, Vite, TailwindCSS, Shadcn, TypeScript.
   - **Package Manager**: pnpm.
   - **Role**: Provides the user interface, manages chat sessions, handles multi-lingual switching (RTL/LTR), and parses streaming Langchain traces for rendering citations and metrics.

2. **Backend (`arabic-rag-chatbot`)**
   - **Stack**: Python 3, FastAPI, Langchain, Cohere Embeddings, OpenRouter (LLM), Qdrant.
   - **Role**: Ingests document PDFs, generates embeddings, queries the Qdrant vector store, and provides an SSE endpoint that streams Langchain agent outputs.
   - **Observability**: Interfaced with LangSmith via `.env` configured `LANGCHAIN_*` environments.

## Directory Structure

```text
c:\cloadeCode\
 ├── query-prism-dash/         # Frontend React App
 │    ├── src/                 # UI components and API client 
 │    ├── tailwind.config.ts   # Style definitions (Arabic font support)
 │    └── package.json         # Managed via pnpm
 └── arabic-rag-chatbot/       # Backend FastAPI app
      ├── api_server.py        # Central API Router
      ├── rag_pipeline.py      # Langchain conversational logic
      ├── vector_store.py      # Qdrant interface for retrieval
      ├── config.py            # Global PyDantic settings and Langchain env vars
      ├── requirements.txt     # Python dependencies
      └── .env                 # Environment secrets
```

## API Endpoints Mapping

The frontend connects to the backend exclusively through Axios/Fetch.

| Frontend Action | Frontend Call | Backend Endpoint | Method | Format |
|---|---|---|---|---|
| Send Message | `streamChat()` | `/api/chat` | POST | SSE stream + `[CITATIONS]` JSON block at EOF |
| Upload PDF | `uploadDocument()`| `/api/documents/upload` | POST | Form Data |
| Get Qdrant Status | `getQdrantStatus()` | `/health` | GET | JSON |

*Note*: Ensure that the FastAPI CORS configuration covers the frontend origin (`http://localhost:5173`). 

---

## How to Run the Environment

### 1. Vector Database Setup
If using Qdrant locally via memory, `QDRANT_URL=local` in the `.env` file suffices. For a permanent local instance:
```bash
docker run -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage:z qdrant/qdrant
```

### 2. Backend (FastAPI)
1. Navigate to the backend directory:
   ```bash
   cd c:\cloadeCode\arabic-rag-chatbot
   ```
2. Set up virtual environment and install dependencies:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your keys (especially LangSmith, OpenRouter API keys).
4. Start the server (runs on port 8000 by default):
   ```bash
   uvicorn api_server:app --reload
   ```

### 3. Frontend (React/Vite)
1. Navigate to the frontend directory:
   ```bash
   cd c:\cloadeCode\query-prism-dash
   ```
2. Install dependencies (make sure `pnpm` is installed globally):
   ```bash
   pnpm install
   ```
3. Start the Vite development server (usually runs on port 5173):
   ```bash
   pnpm run dev
   ```

## LangSmith Observability
The `.env` requires the following layout to push backend RAG invocation traces directly into LangSmith:
```ini
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
LANGCHAIN_API_KEY=your-langsmith-api-key
LANGCHAIN_PROJECT=company-intelligence-rag
```
Langchain natively captures the `ChatOpenAI` and Qdrant chains and synchronizes them with your LangSmith web UI for performance debugging.

## Migration Note (v1.3)
After updating to the flattened Qdrant payload format, clear the old vector data and document metadata once before re-uploading files.

```python
import asyncio

from sqlalchemy import text

from database import AsyncSessionFactory
from vector_store import VectorStoreManager


async def clear_metadata():
    async with AsyncSessionFactory() as session:
        await session.execute(text("DELETE FROM file_metadata"))
        await session.commit()


vs = VectorStoreManager()
vs.delete_all_documents()
asyncio.run(clear_metadata())
```

Then re-upload all documents through the UI.
