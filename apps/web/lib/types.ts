/** Types TypeScript partagés — Agent d'Apprentissage V3 */

// ── Session ──────────────────────────────────────────────────────────────
export interface Session {
  id: number;
  title: string;
  started_at: string;
  message_count: number;
  user_id: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  method?: string;
  tools_used?: ToolUsage[];
  created_at: string;
}

// ── Profile ──────────────────────────────────────────────────────────────
export interface LearnerProfile {
  domain: string;
  niveau_global: string;
  learning_context: string;
  goals: string;
  mastered_competencies: CompetencyMastery[];
  learning_competencies: CompetencyMastery[];
  gaps: CompetencyMastery[];
  average_score: number;
}

export interface Competency {
  id: number;
  nom: string;
  description: string;
  parent_id: number | null;
}

export interface CompetencyMastery {
  competency_id: number;
  nom: string;
  score: number;
  status: string;
  box: number;
}

// ── Progress ─────────────────────────────────────────────────────────────
export interface ProgressSummary {
  total: number;
  average_score: number;
  mastered: CompetencyMastery[];
  gaps: CompetencyMastery[];
  due_for_review: DueItem[];
}

export interface DueItem {
  competency_id: number;
  nom: string;
  box: number;
  next_review: string;
  score: number;
}

export interface RevisionPlan {
  plan: RevisionItem[];
}

export interface RevisionItem {
  competency: string;
  priority: "high" | "medium" | "low";
  box: number;
  reason: string;
}

// ── Documents ────────────────────────────────────────────────────────────
export interface Document {
  id: number;
  filename: string;
  num_chunks: number;
  created_at: string;
}

export interface IndexingStatus {
  total: number;
  indexed: number;
  pending: string[];
}

// ── Tools ────────────────────────────────────────────────────────────────
export interface ToolUsage {
  tool: string;
  duration_ms: number;
  details: Record<string, unknown>;
}

// ── Artifacts ────────────────────────────────────────────────────────────
export type ArtifactType = "schema" | "quiz" | "code" | "chart";

export interface Artifact {
  id: number;
  session_id: number;
  artifact_type: ArtifactType;
  title: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

// ── Models ───────────────────────────────────────────────────────────────
export interface ModelConfig {
  model_name: string;
  display_name: string;
  provider: "ollama_local" | "ollama_cloud";
  default_temperature: number;
  format_mode: string;
  max_tokens: number;
  is_active: boolean;
}

// ── Chat ─────────────────────────────────────────────────────────────────
export interface ChatRequest {
  question: string;
  session_id: number;
  user_id?: string;
  model_override?: string;
}

export interface ChatResponse {
  message_id: number;
  answer: string;
  method?: string;
  pending_confirmation?: boolean;
  confirmation_type?: string;
  confirmation_prompt?: string;
  artifacts?: Artifact[];
  tool_transparency?: ToolUsage[];
}

export interface ConfirmationRequest {
  session_id: number;
  accepted: boolean;
  message_id?: number;
}

// ── SSE Events ───────────────────────────────────────────────────────────
export type StreamEvent =
  | { event: "token"; data: { text: string; method?: string } }
  | { event: "tool_used"; data: ToolUsage }
  | { event: "pending_confirmation"; data: { prompt: string; type: string; message_id: number } }
  | { event: "artifact"; data: { type: ArtifactType; title: string; content: unknown } }
  | { event: "done"; data: { session_id: number; message_id: number; tools_used: ToolUsage[] } }
  | { event: "error"; data: { message: string } };

// ── Quiz (interactive) ───────────────────────────────────────────────────
export interface QuizQuestion {
  question: string;
  options: string[];
  correct_index: number;
}

export interface QuizState {
  questions: QuizQuestion[];
  answers: (number | null)[];
  score: number | null;
  submitted: boolean;
}
