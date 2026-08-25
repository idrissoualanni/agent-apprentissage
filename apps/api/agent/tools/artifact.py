"""Outil de création d'artefacts — port V2 → V3 avec 4 types."""

import json
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def create_artifact(artifact_type: str, title: str, description: str) -> str:
    """Crée un artefact pédagogique structuré (schema, quiz, code, chart).

    Args:
        artifact_type: Type d'artefact : "schema" (Mermaid), "quiz" (JSON React),
                      "code" (Monaco editor), "chart" (Recharts)
        title: Titre de l'artefact
        description: Description ou consigne pour générer le contenu

    Returns:
        JSON string avec type, title, content (contenu structuré selon le type)
    """
    from apps.api.services.model_manager import MODEL_MANAGER

    type_instructions = {
        "schema": "Génère un diagramme Mermaid décrivant la structure du sujet.",
        "quiz": "Génère un quiz interactif au format JSON React.",
        "code": "Génère un exemple de code annoté et complet.",
        "chart": "Génère les données pour un graphique Recharts.",
    }

    instruction = type_instructions.get(artifact_type, type_instructions["schema"])

    prompt = f"""Tu es un expert pédagogique. {instruction}

Sujet : {title}
Description : {description}

Réponds UNIQUEMENT avec un JSON valide (pas de texte avant/après) :
{{
    "type": "{artifact_type}",
    "title": "{title}",
    "content": {{
        // Contenu selon le type :
        // schema: {{"mermaid": "graph TD\\nA-->B"}}
        // quiz: {{"questions": [{{"question": "...", "options": ["A","B","C","D"], "correct_index": 0}}]}}
        // code: {{"language": "python", "code": "...", "explanation": "..."}}
        // chart: {{"chartType": "bar", "data": [{{"name": "...", "value": 0}}], "title": "..."}}
    }}
}}"""

    llm_wrapper = MODEL_MANAGER.get_llm("artifact")
    from langchain_core.messages import HumanMessage
    response = llm_wrapper.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()

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
        logger.warning(f"Artifact parse failed: {content[:200]}")
        return json.dumps({
            "type": artifact_type,
            "title": title,
            "content": {"raw": content[:2000] if content else ""},
        }, ensure_ascii=False)
