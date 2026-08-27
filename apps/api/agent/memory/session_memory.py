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

from langchain_core.messages import HumanMessage

from apps.api.agent.state import AgentState
from apps.api.agent.memory import learner_model as lm
from apps.api.agent.prompts import SESSION_MEMORY_PROMPT, parse_json_llm

logger = logging.getLogger(__name__)

# Fréquence de compaction : tous les 3 tours.
MEMORY_EVERY_N_TURNS = 3

# Prompt : centralisé dans apps/api/agent/prompts.py (SESSION_MEMORY_PROMPT)


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


def _build_state_snapshot(state: AgentState, turn_count: int) -> str:
    """Construit un instantané lisible de l'état du graphe / checkpoint.

    Sert de référence de vérité au sous-agent mémoire : il doit croiser les
    faits extraits de la conversation avec ces valeurs (voir SESSION_MEMORY_PROMPT).
    """
    profile = state.get("learner_profile") or {}
    lines = [
        f"- Tour actuel : {turn_count}",
        f"- Domaine : {profile.get('domain') or 'non défini'}",
        f"- Niveau global (checkpoint) : {profile.get('niveau_global') or 'non estimé'}",
        f"- Niveau estimé cette session : {state.get('estimated_level') or 'non estimé'}",
        f"- Compétence active : {state.get('active_competency') or 'aucune'}",
        f"- Méthode en cours : {state.get('method') or 'aucune'}",
        f"- Diagnostic actif : {bool(state.get('diagnostic_active'))}",
        f"- Quiz actif : {bool(state.get('quiz_active'))}",
        f"- Dernier score d'évaluation : {state.get('evaluation_score')}",
        f"- Dernier score Feynman : {state.get('feynman_score')}",
        f"- Prochaine étape suggérée : {state.get('next_step') or 'aucune'}",
    ]
    return "\n".join(lines)


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

    # Instantané de l'ÉTAT du graphe / checkpoint : référence de vérité que le
    # sous-agent mémoire doit respecter (voir SESSION_MEMORY_PROMPT).
    state_snapshot = _build_state_snapshot(state, turn_count)

    # Résumé précédemment compacté (depuis le Learner Model / checkpoint) pour
    # assurer la continuité et éviter de repartir de zéro.
    previous_summary = "Aucun résumé précédent."
    if session_id is not None:
        try:
            prev = lm.get_session_summary(session_id, db_path=db_path)
            if prev:
                previous_summary = (
                    f"Résumé précédent (tour {prev.get('turn_count')}) :\n"
                    f"{prev.get('text_summary', '')}\n"
                    f"Faits : {json.dumps(prev.get('pedagogical_facts', {}), ensure_ascii=False)}"
                )
        except Exception as e:
            logger.warning(f"session_memory: échec lecture résumé précédent ({e}).")

    llm = model_manager.get_llm("summarize")
    prompt = SESSION_MEMORY_PROMPT.format(
        conversation=conversation,
        state_snapshot=state_snapshot,
        previous_summary=previous_summary,
    )
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        facts = parse_json_llm(response.content, default={})
    except Exception as e:
        logger.warning(f"session_memory: échec LLM ({e}); compaction ignorée.")
        return {"turn_count": turn_count}

    if not isinstance(facts, dict):
        logger.warning("session_memory: réponse LLM non parsable, faits vides.")
        facts = {}

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
