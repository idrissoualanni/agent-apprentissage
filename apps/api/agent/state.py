"""État du graphe LangGraph V3 — TypedDict avec tous les champs nécessaires."""

from typing import Sequence, Optional, TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """État complet du graphe d'apprentissage V3."""

    # ─── Entrée utilisateur ───────────────────────────────────────────────
    question: str
    user_id: str  # V3: multi-user

    # ─── Format standard LangGraph Studio ─────────────────────────────────
    # Studio envoie les messages au format `messages` (liste de BaseMessage).
    # Le réducteur add_messages concatène l'historique automatiquement.
    messages: Annotated[list[BaseMessage], add_messages]

    # ─── Historique conversationnel ───────────────────────────────────────
    chat_history: Sequence[BaseMessage]

    # ─── Contexte RAG ────────────────────────────────────────────────────
    rag_needed: bool
    needs_diagnostic: bool            # V3: flag de routage du router (bootstrap niveau)
    context: str
    rag_confidence: Optional[float]  # V3: score de confiance RAG
    rag_relevant: bool               # Correctif 5 : le contexte est-il pertinent ?
    rag_reason: str                  # Correctif 5 : raison du rejet/acceptation RAG

    # ─── Profil apprenant ────────────────────────────────────────────────
    learner_profile: dict
    active_competency: Optional[str]

    # ─── Méthode pédagogique ─────────────────────────────────────────────
    method: str

    # ─── Diagnostic ──────────────────────────────────────────────────────
    diagnostic_questions: list[str]
    diagnostic_answers: list[str]
    estimated_level: Optional[str]
    diagnostic_active: bool          # Correctif 1 : True pendant la boucle de diagnostic
    diagnostic_current_index: int    # Correctif 1 : index de la question en cours
    diagnostic_just_completed: bool  # V3 : flag PAR TOUR, diagnostic terminé ce tour-ci
    next_step: Optional[str]         # Correctif 4 : "expliquer" | "approfondir" | "continuer"

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

    # ─── Phase 4 : mémoire de session (sous-agent) ──────────────────────
    turn_count: int                      # nombre de tours dans la session
    session_summary: Optional[dict]      # résumé compacté (faits + texte)
    learner_context: Optional[dict]      # contexte apprenant injecté (Phase 4)

    # ─── Phase 5 : method evaluator ─────────────────────────────────────
    last_method_success: Optional[bool]   # derniere methode a-t-elle reussi ?
    last_inferred_score: Optional[float]  # score infere (explicite ou implicite)

    # ─── V3: Transparence outils ─────────────────────────────────────────
    tool_transparency: list[dict]  # [{name, duration_ms, success}]

    # ─── V3: Artefacts ───────────────────────────────────────────────────
    artifacts: list[dict]

    # ─── V3: Streaming ───────────────────────────────────────────────────
    streaming: bool
    model_override: Optional[str]

    # ─── V3: Web search ──────────────────────────────────────────────────
    web_search_results: Optional[list]
    force_web_search: bool  # V3: toggle UI pour forcer la recherche web

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
    "force_web_search": False,
    "session_id": None,
    # Correctif 1 — diagnostic en boucle
    "diagnostic_active": False,
    "diagnostic_current_index": 0,
    "diagnostic_questions": [],
    "diagnostic_answers": [],
    # V3 — flag de routage du router (remplace method="diagnostic" codé en dur)
    "needs_diagnostic": False,
    # V3 — flag PAR TOUR : diagnostic terminé ce tour-ci (remplace method=="diagnostic")
    "diagnostic_just_completed": False,
    # Correctif 4 — feedback adaptatif
    "next_step": None,
    # Correctif 5 — double-check RAG
    "rag_relevant": False,
    "rag_reason": "",
    # Phase 1 — mémoire de session
    "chat_history": [],
    # Phase 4 — sous-agent mémoire
    "turn_count": 0,
    "session_summary": None,
    "learner_context": None,
    # Phase 5 — method evaluator
    "last_method_success": None,
    "last_inferred_score": None,
}
