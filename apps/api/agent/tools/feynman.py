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

    prompt = f"""Tu es un expert pédagogique. Évalue cette explication Feynman.

Sujet : {topic}
Explication de l'apprenant :
{explanation}

Évalue selon ces critères :
1. Clarté : l'explication est-elle facile à comprendre ?
2. Compréhension : l'apprenant a-t-il compris le concept ?
3. Exactitude : l'explication est-elle factuellement correcte ?
4. Simplification : a-t-il utilisé des analogies ou exemples simples ?

Réponds UNIQUEMENT avec un JSON (pas de texte avant/après) :
{{
    "score": 0.0 à 1.0,
    "evaluation": "évaluation courte du niveau",
    "gaps": ["concept manquant 1", "concept manquant 2"],
    "strengths": ["point fort 1", "point fort 2"],
    "feedback": "feedback constructif pour s'améliorer"
}}"""

    llm_wrapper = MODEL_MANAGER.get_llm("feynman_eval")
    from langchain_core.messages import HumanMessage
    response = llm_wrapper.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()

    # Parser le JSON
    try:
        if "```json" in content:
            start = content.index("```json") + len("```json")
            end = content.index("```", start)
            content = content[start:end].strip()
        elif content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        data = json.loads(content)
        return json.dumps(data, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        logger.warning(f"Feynman eval parse failed, raw: {content[:200]}")
        return json.dumps({
            "score": 0.5,
            "evaluation": "Évaluation non disponible",
            "gaps": [],
            "strengths": [],
            "feedback": content[:500] if content else "Pas de réponse du modèle",
        }, ensure_ascii=False)
