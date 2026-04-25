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

export type HistoryMessage = {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
};

export type StoredIdentity = {
  id: string;
  type: "guest" | "local";
  name: string;
  email?: string;
  createdAt: string;
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

type ChatHistoryResponse = {
  history: HistoryMessage[];
  message_count: number;
  session_id: string | null;
};

const LEGACY_USER_ID_STORAGE_KEY = "os-ai-user-id";
const IDENTITIES_STORAGE_KEY = "os-ai-identities";
const CURRENT_IDENTITY_STORAGE_KEY = "os-ai-current-identity-id";
const ACTIVE_SESSION_STORAGE_KEY = "os-ai-active-session-id";

function generateId(prefix: string) {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `${prefix}-${globalThis.crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function readStoredIdentities(): StoredIdentity[] {
  try {
    const raw = window.localStorage.getItem(IDENTITIES_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as StoredIdentity[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeStoredIdentities(identities: StoredIdentity[]) {
  window.localStorage.setItem(IDENTITIES_STORAGE_KEY, JSON.stringify(identities));
}

function ensureIdentityBootstrap(): StoredIdentity[] {
  const existing = readStoredIdentities();
  if (existing.length > 0) {
    return existing;
  }

  const legacyUserId = window.localStorage.getItem(LEGACY_USER_ID_STORAGE_KEY);
  const guestIdentity: StoredIdentity = {
    id: legacyUserId || generateId("guest"),
    type: "guest",
    name: "Guest",
    createdAt: new Date().toISOString(),
  };

  writeStoredIdentities([guestIdentity]);
  window.localStorage.setItem(CURRENT_IDENTITY_STORAGE_KEY, guestIdentity.id);
  if (legacyUserId) {
    window.localStorage.removeItem(LEGACY_USER_ID_STORAGE_KEY);
  }
  return [guestIdentity];
}

export function listStoredIdentities(): StoredIdentity[] {
  return ensureIdentityBootstrap();
}

export function getCurrentIdentity(): StoredIdentity {
  const identities = ensureIdentityBootstrap();
  const currentId = window.localStorage.getItem(CURRENT_IDENTITY_STORAGE_KEY);
  const current = identities.find((identity) => identity.id === currentId);
  if (current) {
    return current;
  }

  const fallback = identities[0];
  window.localStorage.setItem(CURRENT_IDENTITY_STORAGE_KEY, fallback.id);
  return fallback;
}

export function switchIdentity(identityId: string) {
  const identities = ensureIdentityBootstrap();
  const target = identities.find((identity) => identity.id === identityId);
  if (!target) {
    throw new Error("Identity not found");
  }
  window.localStorage.setItem(CURRENT_IDENTITY_STORAGE_KEY, target.id);
}

export function upsertLocalIdentity(name: string, email: string): StoredIdentity {
  const normalizedEmail = email.trim().toLowerCase();
  if (!normalizedEmail) {
    throw new Error("Email is required");
  }

  const identities = ensureIdentityBootstrap();
  const existing = identities.find(
    (identity) => identity.type === "local" && identity.email?.toLowerCase() === normalizedEmail,
  );

  const nextIdentity: StoredIdentity = existing
    ? { ...existing, name: name.trim() || existing.name }
    : {
        id: `acct-${normalizedEmail.replace(/[^a-z0-9]+/g, "-") || generateId("acct")}`,
        type: "local",
        name: name.trim() || normalizedEmail.split("@")[0],
        email: normalizedEmail,
        createdAt: new Date().toISOString(),
      };

  const updated = existing
    ? identities.map((identity) => (identity.id === existing.id ? nextIdentity : identity))
    : [nextIdentity, ...identities];

  writeStoredIdentities(updated);
  window.localStorage.setItem(CURRENT_IDENTITY_STORAGE_KEY, nextIdentity.id);
  return nextIdentity;
}

export function continueAsGuest() {
  const identities = ensureIdentityBootstrap();
  const guest = identities.find((identity) => identity.type === "guest");
  if (!guest) {
    throw new Error("Guest identity missing");
  }
  window.localStorage.setItem(CURRENT_IDENTITY_STORAGE_KEY, guest.id);
}

export function getCurrentUserId() {
  return getCurrentIdentity().id;
}

export function createSessionId() {
  return generateId("session");
}

export function getActiveSessionId() {
  return window.localStorage.getItem(`${ACTIVE_SESSION_STORAGE_KEY}:${getCurrentUserId()}`);
}

export function setActiveSessionId(sessionId: string) {
  window.localStorage.setItem(`${ACTIVE_SESSION_STORAGE_KEY}:${getCurrentUserId()}`, sessionId);
}

function withUserHeaders(init?: RequestInit): RequestInit {
  const headers = new Headers(init?.headers);
  headers.set("X-User-Id", getCurrentUserId());
  return { ...init, headers };
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
  ms = 5000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(input, { ...withUserHeaders(init), signal: controller.signal });
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

export async function getChatHistory(
  sessionId?: string,
): Promise<{
  history: HistoryMessage[];
  sessionId: string | null;
  mocked: boolean;
}> {
  try {
    const url = new URL(`${API_BASE}/api/chat/history`, window.location.origin);
    if (sessionId) {
      url.searchParams.set("session_id", sessionId);
    }
    const res = await fetchWithTimeout(url.toString());
    const data = await parseJsonOrThrow<ChatHistoryResponse>(res);
    return {
      history: data.history ?? [],
      sessionId: data.session_id,
      mocked: false,
    };
  } catch {
    return { history: [], sessionId: sessionId ?? null, mocked: true };
  }
}

export async function clearChatHistory(sessionId?: string): Promise<void> {
  const url = new URL(`${API_BASE}/api/chat/clear`, window.location.origin);
  if (sessionId) {
    url.searchParams.set("session_id", sessionId);
  }
  await fetchWithTimeout(
    url.toString(),
    {
      method: "POST",
    },
    10_000,
  );
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
  const marker = "[CITATIONS]";
  let textBuffer = "";
  let citationsPayload = "";
  let inCitations = false;

  while (true) {
    const { value, done } = await reader.read();
    const chunkText = done ? decoder.decode() : decoder.decode(value, { stream: true });

    if (inCitations) {
      citationsPayload += chunkText;
    } else {
      textBuffer += chunkText;
      const markerIndex = textBuffer.indexOf(marker);

      if (markerIndex !== -1) {
        const delta = textBuffer.slice(0, markerIndex);
        if (delta) {
          yield { delta };
        }
        citationsPayload += textBuffer.slice(markerIndex + marker.length);
        textBuffer = "";
        inCitations = true;
      } else if (textBuffer.length > marker.length) {
        const safeLength = textBuffer.length - marker.length;
        const delta = textBuffer.slice(0, safeLength);
        textBuffer = textBuffer.slice(safeLength);
        if (delta) {
          yield { delta };
        }
      }
    }

    if (done) {
      break;
    }
  }

  if (!inCitations && textBuffer) {
    yield { delta: textBuffer };
  }

  let citations: Citation[] = [];
  if (citationsPayload.trim()) {
    try {
      citations = JSON.parse(citationsPayload) as Citation[];
    } catch {
      citations = [];
    }
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
