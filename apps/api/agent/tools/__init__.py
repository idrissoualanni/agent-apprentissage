"""Agent tools V3 — tous les outils de l'agent d'apprentissage."""

from apps.api.agent.tools.quiz import generate_quiz, evaluate_answer
from apps.api.agent.tools.feynman import evaluate_feynman
from apps.api.agent.tools.artifact import create_artifact
from apps.api.agent.tools.web_search import web_search
from apps.api.agent.tools.progress import (
    update_mastery_after_quiz,
    update_mastery_after_feynman,
    get_progress_summary,
    get_revision_plan,
)
from apps.api.agent.tools.artifact_store import save_artifact, list_user_artifacts

__all__ = [
    "generate_quiz",
    "evaluate_answer",
    "evaluate_feynman",
    "create_artifact",
    "web_search",
    "update_mastery_after_quiz",
    "update_mastery_after_feynman",
    "get_progress_summary",
    "get_revision_plan",
    "save_artifact",
    "list_user_artifacts",
]
