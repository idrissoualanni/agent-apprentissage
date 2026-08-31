/** Client API — Agent d'Apprentissage V3 */

import type {
  Session,
  ChatMessage,
  ChatRequest,
  ChatResponse,
  ConfirmationRequest,
  QuizSubmitRequest,
  QuizSubmitResponse,
  LearnerProfile,
  Competency,
  ProgressSummary,
  RevisionPlan,
  Document,
  IndexingStatus,
  ModelConfig,
  Artifact,
} from "./types";

// En dev : proxy Next.js vers /api. En prod : URL reelle du backend Fly.io
// (definir NEXT_PUBLIC_API_URL=https://agent-apprentissage-api.fly.dev/api).
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

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
  // Correctif 2 : soumission du score d'un quiz interactif
  submitQuiz: (data: QuizSubmitRequest) =>
    request<QuizSubmitResponse>("/chat/quiz-submit", {
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
  summary: () =>
    request<{
      total_competencies: number;
      average_score: number;
      acquired: number;
      learning: number;
      new: number;
      due_for_review: number;
      gaps: { id: number; nom: string; score: number }[];
    }>("/progress/summary"),
  // Phase 6 : calendrier de revision (repetition espacee)
  revisionCalendar: () =>
    request<{ calendar: RevisionCalendarItem[]; count: number }>("/progress/revision/calendar").then((d) => d.calendar),
  revisionDue: (limit = 20) =>
    request<{ due: RevisionCalendarItem[]; count: number }>(`/progress/revision/due?limit=${limit}`).then((d) => d.due),
};

// Type pour le calendrier de revision (Phase 6)
export interface RevisionCalendarItem {
  competency_id: number;
  nom: string;
  domain: string;
  score: number;
  leitner_box: number;
  next_review_at: string;
  last_reviewed_at?: string;
  status: string;
}

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
