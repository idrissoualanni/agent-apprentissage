"""Outil de création d'artefacts — format XML <learning_artefact> (Claude-style).

Le LLM émet un artefact XML ; on le parse en structure JSON exploitable par le
frontend (ArtifactRenderer). Repli : si le XML est absent/invalide, on renvoie
le contenu brut pour ne pas bloquer la réponse.
"""

import json
import re
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def create_artifact(artifact_type: str, title: str, description: str,
                    competency: str = "", competency_id: str = "",
                    level: str = "intermediaire") -> str:
    """Crée un artefact pédagogique structuré (schema, quiz, code, chart).

    Args:
        artifact_type: Type d'artefact : "schema" (Mermaid), "quiz" (JSON React),
                      "code" (Monaco editor), "chart" (Recharts)
        title: Titre de l'artefact
        description: Description ou consigne pour générer le contenu
        competency: Nom de la compétence concernée (facultatif)
        competency_id: Identifiant DB de la compétence (facultatif)
        level: Niveau de l'apprenant (debutant/intermediaire/avance)

    Returns:
        JSON string avec type, title, content (contenu structuré selon le type)
    """
    import uuid
    from apps.api.services.model_manager import MODEL_MANAGER
    from apps.api.agent.prompts import ARTIFACT_PROMPT
    from apps.api.agent.artifacts_xml import parse_learning_artefacts

    type_instructions = {
        "schema": "Génère un diagramme Mermaid complet décrivant la structure du sujet.",
        "quiz": "Génère un quiz interactif de 3 questions.",
        "code": "Génère un exemple de code annoté, complet et exécutable.",
        "chart": "Génère les données d'un graphique (bar/line/pie) au format JSON.",
    }
    instruction = type_instructions.get(artifact_type, type_instructions["schema"])

    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "artefact"
    identifier = f"{artifact_type}-{slug}-{uuid.uuid4().hex[:6]}"

    prompt = ARTIFACT_PROMPT.format(
        instruction=instruction,
        title=title,
        competency=competency or title,
        competency_id=competency_id or "",
        level=level or "intermediaire",
        description=description,
        identifier=identifier,
        artifact_type=artifact_type,
    )

    llm_wrapper = MODEL_MANAGER.get_llm("artifact")
    from langchain_core.messages import HumanMessage
    response = llm_wrapper.invoke([HumanMessage(content=prompt)])
    content = (response.content or "").strip()

    # 1) Priorité : parser l'artefact XML <learning_artefact>.
    try:
        _, artifacts = parse_learning_artefacts(content)
        if artifacts:
            art = artifacts[0]
            return json.dumps({
                "type": art.get("artifact_type", artifact_type),
                "title": art.get("title", title),
                "content": art.get("content", ""),
                "metadata": art.get("metadata", {}),
            }, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Artifact XML parse failed ({e}); fallback brut.")

    # 2) Repli : contenu brut.
    logger.warning(f"Artifact parse failed, raw: {content[:200]}")
    return json.dumps({
        "type": artifact_type,
        "title": title,
        "content": content[:2000] if content else "",
        "metadata": {},
    }, ensure_ascii=False)
