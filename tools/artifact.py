"""Outil de création d'artefacts pédagogiques (schémas, exercices, cartes mentales)."""

import json
from langchain.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

import config

ARTIFACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un créateur de supports pédagogiques. Génère un artefact de type {artifact_type} sur la notion suivante.

Notion : {topic}
Contexte : {context}
Niveau : {level}

Types d'artefacts possibles :
- schema : schéma ou diagramme expliquant le concept
- exercice : exercice pratique avec consigne et solution
- carte_mentale : représentation hiérarchique du concept

Format de sortie JSON STRICT :
{{
  "type": "schema|exercice|carte_mentale",
  "title": "Titre de l'artefact",
  "content": "Contenu en Markdown structuré",
  "format": "markdown"
}}

Le contenu doit être directement affichable dans Streamlit en Markdown.
Sois pédagogique, utilise des exemples concrets."""),
])


@tool
def create_artifact(topic: str, context: str, artifact_type: str = "schema",
                    level: str = "intermediaire") -> str:
    """Crée un artefact pédagogique (schéma, exercice ou carte mentale).

    Args:
        topic: Notion à illustrer
        context: Contexte documentaire de référence
        artifact_type: Type d'artefact (schema, exercice, carte_mentale)
        level: Niveau de l'apprenant (debutant, intermediaire, avance)

    Returns:
        JSON string avec type, title, content (Markdown), format
    """
    llm = ChatOllama(model=config.OLLAMA_MODEL, temperature=0.5)

    messages = ARTIFACT_PROMPT.format_messages(
        artifact_type=artifact_type,
        topic=topic,
        context=context[:2000],
        level=level,
    )

    response = llm.invoke(messages)
    content = response.content.strip()

    # Nettoyage JSON
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        data = json.loads(content.strip())
        return json.dumps(data, ensure_ascii=False)
    except json.JSONDecodeError:
        # Fallback : retourner le texte brut comme Markdown
        fallback = {
            "type": artifact_type,
            "title": f"Artefact : {topic}",
            "content": response.content[:2000],
            "format": "markdown",
        }
        return json.dumps(fallback, ensure_ascii=False)
