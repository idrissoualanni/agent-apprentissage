"""État du graphe LangGraph V3 — TypedDict avec tous les champs nécessaires."""

from typing import Sequence, Optional, TypedDict
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """État complet du graphe d'apprentissage V3."""

    # ─── Entrée utilisateur ───────────────────────────────────────────────
    question: str
    user_id: str  # V3: multi-user

    # ─── Historique conversationnel ───────────────────────────────────────
    chat_history: Sequence[BaseMessage]

    # ─── Contexte RAG ────────────────────────────────────────────────────
    rag_needed: bool
    context: str
    rag_confidence: Optional[float]  # V3: score de confiance RAG

    # ─── Profil apprenant ────────────────────────────────────────────────
    learner_profile: dict
    active_competency: Optional[str]

    # ─── Méthode pédagogique ─────────────────────────────────────────────
    method: str

    # ─── Diagnostic ──────────────────────────────────────────────────────
    diagnostic_questions: list[str]
    diagnostic_answers: list[str]
    estimated_level: Optional[str]

    # ─── Quiz ────────────────────────────────────────────────────────────
    quiz_questions: list[dict]
    quiz_active: bool

    # ─── Feynman ─────────────────────────────────────────────────────────
    feynman_topic: Optional[str]
    feynman_explanation: Optional[str]
    awaiting_feynman_explanation: bool
    feynman_score: Optional[float]
    feynman_gaps: Optional[str]

    # ─── Outil déclenché ─────────────────────────────────────────────────
    tool_name: Optional[str]
    tool_result: Optional[str]

    # ─── Évaluation & progression ────────────────────────────────────────
    evaluation_score: Optional[float]
    leitner_action: Optional[str]

    # ─── Human-in-the-loop ───────────────────────────────────────────────
    pending_confirmation: bool
    confirmation_type: Optional[str]
    confirmation_prompt: Optional[str]
    user_confirmed: Optional[bool]

    # ─── Session ─────────────────────────────────────────────────────────
    thread_id: Optional[str]
    session_id: Optional[int]  # V3: DB session ID

    # ─── V3: Transparence outils ─────────────────────────────────────────
    tool_transparency: list[dict]  # [{name, duration_ms, success}]

    # ─── V3: Artefacts ───────────────────────────────────────────────────
    artifacts: list[dict]

    # ─── V3: Streaming ───────────────────────────────────────────────────
    streaming: bool
    model_override: Optional[str]

    # ─── V3: Web search ──────────────────────────────────────────────────
    web_search_results: Optional[list]

    # ─── Réponse finale ──────────────────────────────────────────────────
    answer: str


# Valeurs par défaut pour les champs V3
STATE_DEFAULTS = {
    "user_id": "default_user",
    "rag_confidence": None,
    "tool_transparency": [],
    "artifacts": [],
    "streaming": True,
    "model_override": None,
    "web_search_results": None,
    "session_id": None,
}
