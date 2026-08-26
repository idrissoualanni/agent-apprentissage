"""Sous-agent mémoire de session (Phase 4).

Implémentation maison inspirée de LangMem (semantic + episodic memory), mais
adossée à notre Learner Model SQLite plutôt qu'au LangGraph store.

Tous les N tours, ce sous-agent :
1. extrait les "faits pédagogiques" (semantic : niveau, compétences, erreurs, réussites),
2. produit un résumé textuel compacté de la conversation,
3. upsert le tout dans session_summary.

Stratégie head/tail (OpenAI Cookbook) : le chat_history reste intact dans le
checkpointer ; seul un résumé structuré est archivé ici pour être réinjecté
comme contexte, sans alourdir le prompt.
"""

import json
import logging
from typing import Optional

from langchain_core.messages import HumanMessage

from apps.api.agent.state import AgentState
from apps.api.agent.memory import learner_model as lm

logger = logging.getLogger(__name__)

# Fréquence de compaction : tous les 3 tours.
MEMORY_EVERY_N_TURNS = 3


SESSION_MEMORY_PROMPT = (
    "Tu es le sous-agent mémoire d'un tuteur pédagogique. Analyse la conversation "
    "ci-dessous et extrais les informations utiles pour suivre la progression de l'apprenant.\n\n"
    "Conversation :\n{conversation}\n\n"
    "Réponds UNIQUEMENT avec un JSON valide de cette forme :\n"
    "{{\n"
    '  "competences_abordees": ["..."],\n'
    '  "niveau_estime": "debutant | intermediaire | avance",\n'
    '  "reussites": ["..."],\n'
    '  "erreurs_ou_lacunes": ["..."],\n'
    '  "resume_textuel": "résumé court (2-3 phrases) de ce qui s\'est passé dans la session"\n'
    "}}"
)


def _format_conversation(chat_history, max_messages: int = 30) -> str:
    """Formate l'historique en texte pour le prompt (limite les derniers messages)."""
    msgs = list(chat_history)[-max_messages:]
    lines = []
    for m in msgs:
        role = getattr(m, "type", "message")
        content = getattr(m, "content", "")
        if isinstance(content, list):
            content = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        prefix = "Apprenant" if role == "human" else "Tuteur"
        lines.append(f"{prefix}: {content}")
    return "\n".join(lines)


def _parse_memory_response(content: str) -> dict:
    """Parse la réponse JSON du LLM, tolérant les blocs ```json."""
    content = content.strip()
    if "```json" in content:
        start = content.index("```json") + len("```json")
        end = content.index("```", start)
        content = content[start:end].strip()
    elif content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("session_memory: réponse LLM non parsable, faits vides.")
        return {}


def session_memory_node(state: AgentState, model_manager, db_path=None) -> dict:
    """Compacte la session : extrait faits pédagogiques + résumé textuel.

    Appelé tous les MEMORY_EVERY_N_TURNS tours. Met à jour session_summary et
    retourne turn_count incrémenté + session_summary.
    """
    turn_count = state.get("turn_count", 0) + 1
    chat_history = state.get("chat_history", [])
    session_id = state.get("session_id")
    user_id = state.get("user_id", "default_user")

    # Ne compacter que s'il y a de la matière et au bon rythme.
    if not chat_history or turn_count % MEMORY_EVERY_N_TURNS != 0:
        return {"turn_count": turn_count}

    conversation = _format_conversation(chat_history)
    if not conversation.strip():
        return {"turn_count": turn_count}

    llm = model_manager.get_llm("summarize")
    prompt = SESSION_MEMORY_PROMPT.format(conversation=conversation)
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        facts = _parse_memory_response(response.content)
    except Exception as e:
        logger.warning(f"session_memory: échec LLM ({e}); compaction ignorée.")
        return {"turn_count": turn_count}

    text_summary = facts.pop("resume_textuel", "")
    pedagogical_facts = facts

    # Persister dans le Learner Model si on a un session_id.
    if session_id is not None:
        try:
            lm.upsert_session_summary(
                session_id, pedagogical_facts, text_summary, turn_count,
                user_id=user_id, db_path=db_path,
            )
        except Exception as e:
            logger.warning(f"session_memory: échec upsert ({e}).")

    summary = {
        "pedagogical_facts": pedagogical_facts,
        "text_summary": text_summary,
        "turn_count": turn_count,
    }
    logger.info(f"session_memory: session {session_id} compactée au tour {turn_count}.")
    return {"turn_count": turn_count, "session_summary": summary}
