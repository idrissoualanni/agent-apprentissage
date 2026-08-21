"""Outil d'evaluation de restitution Feynman."""

import json
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate

import config
from llm import get_llm

FEYNMAN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu evalues une restitution Feynman -- l'utilisateur explique une notion avec ses propres mots.

Notion a evaluer : {topic}
Contexte de reference : {context}
Explication de l'utilisateur : {explanation}

Criteres d'evaluation :
1. **Exactitude** : l'explication est-elle fidele au concept ?
2. **Simplicite** : utilise-t-il des mots simples, sans jargon inutile ?
3. **Completude** : couvre-t-il les aspects essentiels ?
4. **Exemples** : donne-t-il des exemples concrets ?

Format de sortie JSON STRICT (uniquement le JSON, rien d'autre) :
{{
  "score": 0.75,
  "evaluation": "texte d'evaluation global",
  "gaps": ["lacune 1", "lacune 2"],
  "strengths": ["point fort 1"],
  "feedback": "retour constructif pour l'utilisateur"
}}

Le score est entre 0.0 et 1.0. Sois bienveillant mais rigoureux."""),
])


@tool
def evaluate_feynman(topic: str, context: str, explanation: str) -> str:
    """Evalue une restitution Feynman -- l'utilisateur explique une notion avec ses propres mots.

    Args:
        topic: Notion a evaluer
        context: Contexte de reference du document
        explanation: Explication de l'utilisateur avec ses propres mots

    Returns:
        JSON string avec score (0-1), evaluation, gaps, strengths, feedback
    """
    llm = get_llm(model=config.OLLAMA_MODEL, temperature=0.2)

    messages = FEYNMAN_PROMPT.format_messages(
        topic=topic,
        context=context[:1500],
        explanation=explanation,
    )

    response = llm.invoke(messages)
    content = response.content.strip()

    # Nettoyage JSON
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        return json.dumps(json.loads(content.strip()), ensure_ascii=False)
    except json.JSONDecodeError:
        fallback = {
            "score": 0.5,
            "evaluation": "Evaluation non structuree",
            "gaps": ["Format de reponse non reconnu"],
            "strengths": [],
            "feedback": response.content[:200],
        }
        return json.dumps(fallback, ensure_ascii=False)
