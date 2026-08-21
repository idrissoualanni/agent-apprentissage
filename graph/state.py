"""État du graphe LangGraph — TypedDict avec tous les champs nécessaires."""

from typing import Sequence, Optional, TypedDict
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """État complet du graphe d'apprentissage."""

    # Entrée utilisateur
    question: str

    # Historique conversationnel (géré par le checkpointer)
    chat_history: Sequence[BaseMessage]

    # Contexte RAG
    context: str

    # Profil apprenant (chargé depuis SQLite)
    learner_profile: dict
    active_competency: Optional[str]  # compétence courante identifiée

    # Méthode pédagogique choisie
    method: str  # "socratic", "feynman", "scaffold", "quiz", "diagnostic"

    # Diagnostic
    diagnostic_questions: list[str]
    diagnostic_answers: list[str]
    estimated_level: Optional[str]

    # Quiz
    quiz_questions: list[dict]
    quiz_active: bool

    # Feynman
    feynman_topic: Optional[str]
    feynman_explanation: Optional[str]
    awaiting_feynman_explanation: bool  # True = prochaine réponse = explication Feynman
    feynman_score: Optional[float]
    feynman_gaps: Optional[str]

    # Outil déclenché
    tool_name: Optional[str]
    tool_result: Optional[str]

    # Évaluation & progression
    evaluation_score: Optional[float]
    leitner_action: Optional[str]  # "promote", "demote", "stay"

    # Réponse finale
    answer: str
