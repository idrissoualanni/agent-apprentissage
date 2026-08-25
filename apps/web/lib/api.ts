/** Client API — Agent d'Apprentissage V3 */

import type {
  Session,
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ConfirmationRequest,
  LearnerProfile,
  Competency,
  ProgressSummary,
  RevisionPlan,
  Document,
  IndexingStatus,
  ModelConfig,
  Artifact,
} from "./types";

const API_BASE = "/api";

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API Error ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Sessions ─────────────────────────────────────────────────────────────

export const sessions = {
  list: () => request<{ sessions: Session[] }>("/sessions").then((d) => d.sessions),
  create: (title?: string) =>
    request<Session>("/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  get: (id: number) => request<Session>(`/sessions/${id}`),
  update: (id: number, title: string) =>
    request<void>(`/sessions/${id}`, {
      method: "PUT",
      body: JSON.stringify({ title }),
    }),
  delete: (id: number) =>
    request<void>(`/sessions/${id}`, { method: "DELETE" }),
  messages: (id: number) => request<{ messages: ChatMessage[] }>(`/sessions/${id}/messages`).then((d) => d.messages),
};

// ── Chat ─────────────────────────────────────────────────────────────────

export const chat = {
  send: (data: ChatRequest) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({ ...data, streaming: false }),
    }),
  confirm: (data: ConfirmationRequest) =>
    request<ChatResponse>("/chat/confirm", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Profile ──────────────────────────────────────────────────────────────

export const profile = {
  get: () => request<LearnerProfile>("/profile"),
  update: (data: Partial<LearnerProfile>) =>
    request<void>("/profile", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  tree: () => request<{ tree: Competency[] }>("/profile/tree").then((d) => d.tree),
  competencies: () => request<{ competencies: Competency[] }>("/profile/competencies").then((d) => d.competencies),
};

// ── Progress ─────────────────────────────────────────────────────────────

export const progress = {
  overview: () => request<{ overview: unknown[] }>("/progress/overview").then((d) => d.overview),
  due: () => request<{ due: unknown[]; count: number }>("/progress/due").then((d) => d.due),
  revisionPlan: () => request<RevisionPlan>("/progress/revision-plan"),
  summary: () => request<unknown>("/progress/summary"),
};

// ── Documents ────────────────────────────────────────────────────────────

export const documents = {
  list: () => request<{ documents: Document[] }>("/documents").then((d) => d.documents),
  status: () => request<IndexingStatus>("/documents/status"),
  delete: (filename: string) =>
    request<void>(`/documents/${filename}`, { method: "DELETE" }),
  upload: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error("Upload failed");
    return res.json();
  },
};

// ── Models ───────────────────────────────────────────────────────────────

export const models = {
  catalog: () => request<{ catalog: ModelConfig[] }>("/models/catalog").then((d) => d.catalog),
  active: () => request<{ active: Record<string, string> }>("/models/active").then((d) => d.active),
  select: (operation: string, modelName: string) =>
    request<void>("/models/select", {
      method: "POST",
      body: JSON.stringify({ operation, model_name: modelName }),
    }),
  status: () => request<unknown>("/models/status"),
};

// ── Artifacts ────────────────────────────────────────────────────────────

export const artifacts = {
  list: (sessionId?: number) => {
    const query = sessionId ? `?session_id=${sessionId}` : "";
    return request<Artifact[]>(`/documents/artifacts${query}`);
  },
};
