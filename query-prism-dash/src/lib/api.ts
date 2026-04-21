/**
 * api.ts — Company Intelligence RAG Client
 * Connects to FastAPI backend at API_BASE.
 * Returns empty data (no mocks) when the backend is unavailable,
 * so the UI always reflects real state.
 *
 * Default backend URL: http://localhost:8000
 */

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string) || "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────────

export type Citation = {
  id: string;
  document: string;
  page: number;
  snippet: string;
  score?: number;
};

export type ChatRequest = {
  message: string;
  sourceCheck: boolean;
  deepResearch: boolean;
  reasoning: boolean;
  language: "en" | "ar";
  history?: { role: "user" | "assistant"; content: string }[];
};

export type DocumentRecord = {
  id: string;
  name: string;
  size: number;
  pages: number;
  chunks: number;
  uploadedAt: string;
  status: "indexing" | "ready" | "error";
};

export type Session = {
  id: string;
  title: string;
  preview: string;
  updatedAt: string;
  messageCount: number;
};

export type TokenUsage = {
  used: number;
  total: number;
  mocked: boolean;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Race a fetch against a timeout. Throws on timeout or network error. */
async function fetchWithTimeout(
  input: RequestInfo,
  init?: RequestInit,
  ms = 5000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    const res = await fetch(input, { ...init, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Documents ────────────────────────────────────────────────────────────────

/**
 * List indexed documents from the backend.
 * Returns an empty array (not mock data) when the backend is unreachable.
 */
export async function listDocuments(): Promise<{
  docs: DocumentRecord[];
  mocked: boolean;
}> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/documents`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const docs = (await res.json()) as DocumentRecord[];
    return { docs, mocked: false };
  } catch {
    // Return empty list — no fake data
    return { docs: [], mocked: true };
  }
}

/**
 * Upload one or more PDF files to the backend.
 * Uses multipart/form-data with field name "files" (what FastAPI expects).
 */
export async function uploadDocument(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<{ doc: DocumentRecord; mocked: boolean }> {
  const fd = new FormData();
  // Backend expects List[UploadFile] via field name "files"
  fd.append("files", file);

  onProgress?.(10);

  const res = await fetchWithTimeout(
    `${API_BASE}/api/documents/upload`,
    { method: "POST", body: fd },
    30_000, // 30s for large PDFs
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  onProgress?.(100);

  const data = await res.json();
  // Backend returns DocumentUploadResponse, adapt it to DocumentRecord shape
  const doc: DocumentRecord = {
    id: `upload-${Date.now()}`,
    name: file.name,
    size: file.size,
    pages: Math.max(1, Math.round(file.size / 28_000)),
    chunks: data.documents_processed ?? 0,
    uploadedAt: new Date().toISOString().slice(0, 10),
    status: "ready",
  };
  return { doc, mocked: false };
}

// ─── Sessions ─────────────────────────────────────────────────────────────────

/**
 * List chat sessions from the backend.
 * Returns an empty array when the backend is unreachable.
 */
export async function listSessions(): Promise<{
  sessions: Session[];
  mocked: boolean;
}> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/sessions`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const sessions = (data.sessions ?? data) as Session[];
    return { sessions, mocked: false };
  } catch {
    return { sessions: [], mocked: true };
  }
}

// ─── Chat Streaming ───────────────────────────────────────────────────────────

/**
 * Streaming chat. Yields text chunks chunk by chunk.
 * Parses the optional [CITATIONS]{...} suffix at end of stream.
 * Falls back to a mock typewriter reply when the backend is unreachable.
 */
export async function* streamChat(
  req: ChatRequest,
): AsyncGenerator<{
  delta?: string;
  citations?: Citation[];
  mocked?: boolean;
  done?: boolean;
}> {
  try {
    const res = await fetchWithTimeout(
      `${API_BASE}/api/chat`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      },
      8_000,
    );

    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: "Chat failed" }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let citations: Citation[] = [];

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Check for [CITATIONS] marker anywhere in the buffer
      const citIdx = buffer.indexOf("[CITATIONS]");
      if (citIdx !== -1) {
        const textPart = buffer.slice(0, citIdx);
        const citPart = buffer.slice(citIdx + "[CITATIONS]".length);
        try {
          citations = JSON.parse(citPart);
        } catch {
          /* malformed JSON — ignore citations */
        }
        if (textPart) yield { delta: textPart };
        buffer = "";
        break;
      }

      if (buffer) {
        yield { delta: buffer };
        buffer = "";
      }
    }

    yield { citations, done: true };
    return;
  } catch {
    // ── Mock fallback (dev / offline mode) ──────────────────────────────────
    const reply = mockReplyFor(req);
    for (const ch of reply) {
      await new Promise((r) => setTimeout(r, 14));
      yield { delta: ch };
    }
    yield {
      citations: req.sourceCheck ? MOCK_CITATIONS : [],
      done: true,
      mocked: true,
    };
  }
}

// ─── Usage ────────────────────────────────────────────────────────────────────

export async function getTokenUsage(): Promise<TokenUsage> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/usage`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { used: data.used ?? 0, total: data.total ?? 1_000_000, mocked: false };
  } catch {
    return { used: 0, total: 1_000_000, mocked: true };
  }
}

// ─── Qdrant Health ────────────────────────────────────────────────────────────

export async function getQdrantStatus(): Promise<{
  active: boolean;
  mocked: boolean;
}> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/health`, undefined, 3_000);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { active: data.status === "healthy", mocked: false };
  } catch {
    return { active: false, mocked: true };
  }
}

// ─── Mock helpers (chat fallback only — no mock docs/sessions) ────────────────

const MOCK_CITATIONS: Citation[] = [
  {
    id: "c1",
    document: "Employee_Handbook_2025.pdf",
    page: 42,
    snippet:
      "Employees accrue 1.75 days of paid time off per month, with a maximum carry-over of 5 days into the following calendar year.",
    score: 0.91,
  },
  {
    id: "c2",
    document: "Data_Privacy_Policy_AR.pdf",
    page: 11,
    snippet:
      "All personally identifiable information must be encrypted at rest using AES-256 and in transit via TLS 1.3 or higher.",
    score: 0.88,
  },
];

function mockReplyFor(req: ChatRequest): string {
  const ar = req.language === "ar";
  if (ar) {
    return [
      "⚠️ _الخادم غير متاح حالياً — هذا رد تجريبي._\n\n",
      "بناءً على فهرس المستندات الداخلي، إليك ملخصًا موجزًا:\n\n",
      "• تنص سياسة الإجازات على استحقاق ١٫٧٥ يومًا شهريًا، مع حد أقصى للترحيل قدره ٥ أيام.\n",
      "• يجب تشفير جميع البيانات الشخصية باستخدام AES-256 وفقًا لسياسة الخصوصية.\n",
    ].join("");
  }
  return [
    "⚠️ _Backend unavailable — this is a demo response._\n\n",
    "Based on the indexed corpus, here's a concise synthesis:\n\n",
    "• PTO policy: employees accrue **1.75 days/month** with a max **5-day carry-over**.\n",
    "• All PII must be encrypted at rest using **AES-256** and in transit via **TLS 1.3+**.\n",
  ].join("");
}
