"""Outil d'évaluation Feynman — port V2 → V3."""

import json
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def evaluate_feynman(topic: str, explanation: str) -> str:
    """Évalue la qualité d'une explication Feynman (technique de rétroleçon).

    Args:
        topic: Le sujet ou concept expliqué par l'apprenant
        explanation: L'explication de l'apprenant dans ses propres mots

    Returns:
        JSON string avec score (0-1), evaluation, gaps, strengths, feedback
    """
    from apps.api.services.model_manager import MODEL_MANAGER
    from apps.api.agent.prompts import FEYNMAN_EVAL_PROMPT, parse_json_llm

    prompt = FEYNMAN_EVAL_PROMPT.format(topic=topic, explanation=explanation)

    llm_wrapper = MODEL_MANAGER.get_llm("feynman_eval")
    from langchain_core.messages import HumanMessage
    response = llm_wrapper.invoke([HumanMessage(content=prompt)])
    content = (response.content or "").strip()

    data = parse_json_llm(content)
    if isinstance(data, dict) and "score" in data:
        return json.dumps(data, ensure_ascii=False)

    logger.warning(f"Feynman eval parse failed, raw: {content[:200]}")
    return json.dumps({
        "score": 0.5,
        "evaluation": "Évaluation non disponible",
        "gaps": [],
        "strengths": [],
        "feedback": content[:500] if content else "Pas de réponse du modèle",
    }, ensure_ascii=False)
