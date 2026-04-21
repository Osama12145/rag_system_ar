declare global {
  interface Window {
    __APP_CONFIG__?: {
      API_BASE?: string;
    };
  }
}

export const API_BASE =
  window.__APP_CONFIG__?.API_BASE?.trim() ||
  (import.meta.env.VITE_API_BASE as string | undefined)?.trim() ||
  "";

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
  sessionId?: string;
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

type UploadResponse = {
  message: string;
  file_id: string;
  success: boolean;
  document?: DocumentRecord;
};

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
  ms = 5000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function listDocuments(): Promise<{
  docs: DocumentRecord[];
  mocked: boolean;
}> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/documents`);
    return { docs: await parseJsonOrThrow<DocumentRecord[]>(res), mocked: false };
  } catch {
    return { docs: [], mocked: true };
  }
}

export async function uploadDocument(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<{ doc: DocumentRecord; mocked: boolean }> {
  const formData = new FormData();
  formData.append("files", file);
  onProgress?.(10);

  const res = await fetchWithTimeout(
    `${API_BASE}/api/documents/upload`,
    { method: "POST", body: formData },
    30_000,
  );
  const data = await parseJsonOrThrow<UploadResponse>(res);
  onProgress?.(100);

  return {
    doc: data.document ?? {
      id: data.file_id,
      name: file.name,
      size: file.size,
      pages: 0,
      chunks: 0,
      uploadedAt: new Date().toISOString().slice(0, 10),
      status: "ready",
    },
    mocked: false,
  };
}

export async function listSessions(): Promise<{
  sessions: Session[];
  mocked: boolean;
}> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/sessions`);
    const data = await parseJsonOrThrow<{ sessions: Session[] }>(res);
    return { sessions: data.sessions ?? [], mocked: false };
  } catch {
    return { sessions: [], mocked: true };
  }
}

function parseStreamPayload(payload: string): { text: string; citations: Citation[] } {
  const marker = "[CITATIONS]";
  const markerIndex = payload.indexOf(marker);
  if (markerIndex === -1) {
    return { text: payload, citations: [] };
  }

  const text = payload.slice(0, markerIndex);
  const citationsPayload = payload.slice(markerIndex + marker.length).trim();
  if (!citationsPayload) {
    return { text, citations: [] };
  }

  try {
    return { text, citations: JSON.parse(citationsPayload) as Citation[] };
  } catch {
    return { text, citations: [] };
  }
}

export async function* streamChat(
  req: ChatRequest,
): AsyncGenerator<{
  delta?: string;
  citations?: Citation[];
  mocked?: boolean;
  done?: boolean;
}> {
  const res = await fetchWithTimeout(
    `${API_BASE}/api/chat`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    },
    15_000,
  );

  if (!res.ok || !res.body) {
    const error = await res.json().catch(() => ({ detail: "Chat failed" }));
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let payload = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      payload += decoder.decode();
      break;
    }
    payload += decoder.decode(value, { stream: true });
  }

  const { text, citations } = parseStreamPayload(payload);
  if (text) {
    yield { delta: text };
  }
  yield { citations, done: true };
}

export async function getTokenUsage(): Promise<TokenUsage> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/usage`);
    const data = await parseJsonOrThrow<{ used?: number; total?: number }>(res);
    return { used: data.used ?? 0, total: data.total ?? 1_000_000, mocked: false };
  } catch {
    return { used: 0, total: 1_000_000, mocked: true };
  }
}

export async function getQdrantStatus(): Promise<{
  active: boolean;
  mocked: boolean;
}> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/health`, undefined, 3_000);
    const data = await parseJsonOrThrow<{ status?: string }>(res);
    return { active: data.status === "healthy" || data.status === "degraded", mocked: false };
  } catch {
    return { active: false, mocked: true };
  }
}
