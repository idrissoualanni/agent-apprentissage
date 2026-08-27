"""Nœuds de contexte (Phase 3+) : competency_proposer, et à terme
context_builder, method_evaluator, revision_planner.

Ces nœuds enrichissent l'état de l'agent avec le Learner Model et gèrent
les compétences dynamiques.
"""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage

from apps.api.agent.state import AgentState
from apps.api.db import crud
from apps.api.agent.memory import learner_model as lm
from apps.api.agent.prompts import (
    COMPETENCY_PROPOSAL_PROMPT, IMPLICIT_UNDERSTANDING_PROMPT,
)

logger = logging.getLogger(__name__)

# Prompts : centralisés dans apps/api/agent/prompts.py
# (COMPETENCY_PROPOSAL_PROMPT, IMPLICIT_UNDERSTANDING_PROMPT)


def competency_proposer_node(state: AgentState, model_manager, db_path=None) -> dict:
    """Propose une nouvelle compétence si aucune n'est détectée, avec validation utilisateur.

    Utilise interrupt() pour demander à l'utilisateur de valider la création.
    Si validé, crée la compétence via crud.create_competency.
    """
    from langgraph.types import interrupt

    domain = state.get("learner_profile", {}).get("domain", "")
    question = state.get("question", "")
    active = state.get("active_competency")
    user_id = state.get("user_id", "default_user")

    # Rien à proposer si une compétence est déjà active ou pas de domaine.
    if active or not domain:
        return {}

    # S'il y a déjà une proposition en attente, on la re-soumet (reprise après interrupt).
    pending = lm.get_pending_competency(user_id, db_path=db_path)

    if pending is None:
        # Première exécution : proposer un nom via le LLM.
        # On lui fournit la liste des compétences EXISTANTES du domaine pour
        # qu'il vérifie d'abord si la question s'y rattache (évite les doublons
        # et garantit le rattachement au domaine abordé).
        existing = crud.get_competencies(domain, db_path) or []
        if existing:
            existing_names = "\n".join(f"- {c['nom']}" for c in existing)
        else:
            existing_names = "(aucune compétence existante dans ce domaine)"

        llm = model_manager.get_llm("chat")
        prompt = COMPETENCY_PROPOSAL_PROMPT.format(
            domain=domain,
            question=question,
            existing_competencies=existing_names,
        )
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            proposed_name = response.content.strip().strip('"\'').split("\n")[0].strip()
        except Exception as e:
            logger.warning(f"competency_proposer: échec LLM ({e}); pas de proposition.")
            return {}

        if not proposed_name:
            return {}

        # Éviter les doublons : si une compétence similaire existe (nom proche ou
        # chevauchement de termes), on l'utilise directement.
        similar = lm.find_similar_competency(proposed_name, domain, db_path=db_path)
        if similar:
            return {"active_competency": similar["nom"]}

        pending_id = lm.propose_competency(proposed_name, domain, db_path=db_path)
        pending = {
            "id": pending_id,
            "proposed_name": proposed_name,
            "proposed_domain": domain,
        }

    # Demander validation à l'utilisateur (pause l'exécution).
    user_response = interrupt({
        "question": (
            f"Tu abordes un nouveau sujet. Veux-tu que je crée la compétence "
            f"« {pending['proposed_name']} » dans le domaine « {domain} » pour suivre ta progression ?"
        ),
        "type": "competency_creation",
        "proposed_name": pending["proposed_name"],
    })

    accepted = user_response in (True, "true", "yes", "oui", "ok", "confirm", "1", 1)
    if accepted:
        lm.resolve_pending_competency(pending["id"], "approved", db_path=db_path)
        # Vérifie à nouveau les doublons avant création.
        similar = lm.find_similar_competency(pending["proposed_name"], domain, db_path=db_path)
        if similar:
            return {"active_competency": similar["nom"]}
        crud.create_competency(domain, pending["proposed_name"], db_path=db_path)
        logger.info(f"Compétence créée : {pending['proposed_name']} ({domain})")
        return {"active_competency": pending["proposed_name"]}

    lm.resolve_pending_competency(pending["id"], "rejected", db_path=db_path)
    return {}


def context_builder_node(state: AgentState, db_path=None) -> dict:
    """Construit le contexte apprenant et l'injecte dans l'état (Phase 4).

    Charge depuis le Learner Model : niveau par compétence, scores de la session,
    meilleures méthodes, sujets habituels, et résumé de session. Ce contexte sera
    utilisé par les nœuds pédagogiques pour personnaliser les réponses.
    """
    user_id = state.get("user_id", "default_user")
    session_id = state.get("session_id")
    try:
        context = lm.get_learner_context(user_id, session_id=session_id, db_path=db_path)
    except Exception as e:
        logger.warning(f"context_builder: échec chargement Learner Model ({e}).")
        context = {}
    return {"learner_context": context}


# ─── Phase 5 : method evaluator + hook ε-greedy ──────────────────────────

DEFAULT_EPSILON = 0.2  # 20% exploration, 80% exploitation


def _resolve_competency_id(competency_name, state=None, db_path=None) -> Optional[int]:
    """Résout un nom de compétence en ID via la base."""
    if not competency_name:
        return None
    from apps.api.agent.nodes import _resolve_competency_id as _resolve
    try:
        return _resolve(competency_name, state or {}, db_path=db_path)
    except Exception:
        return None


def _epsilon_greedy_method(competency_id: int, default_method: str, db_path=None,
                            epsilon: float = DEFAULT_EPSILON) -> str:
    """Hook ε-greedy : exploite la meilleure méthode connue 1-ε, explore ε."""
    import random
    if competency_id is None:
        return default_method
    eff = lm.get_method_effectiveness(competency_id, db_path=db_path)
    if not eff or random.random() >= epsilon:
        return default_method
    # Exploration : choisir une méthode au hasard parmi celles connues
    return random.choice(list(eff.keys()))


def _inferred_success_from_llm(question: str, answer: str, user_response: str,
                                model_manager) -> Optional[float]:
    """Inference implicite : le LLM devine si l'apprenant a compris (0-1)."""
    if not question or not user_response:
        return None
    from langchain_core.messages import HumanMessage
    prompt = IMPLICIT_UNDERSTANDING_PROMPT.format(
        question=question, answer=answer, user_response=user_response,
    )
    try:
        llm = model_manager.get_llm("feynman_eval")
        resp = llm.invoke([HumanMessage(content=prompt)])
        val = float(resp.content.strip().split()[0])
        return max(0.0, min(1.0, val))
    except Exception as e:
        logger.warning(f"inference implicite échouée ({e}).")
        return None


def method_evaluator_node(state: AgentState, model_manager, db_path=None) -> dict:
    """Phase 5 : met a jour method_effectiveness et applique le blend mastery.

    - Signal explicite (quiz/feynman) : score utilisé directement.
    - Pas de signal : inference implicite via le LLM depuis la conversation.
    Met a jour method_effectiveness (record_method_outcome) et mastery.score
    avec le blend (quiz : old*0.6 + new*0.4 ; feynman : old*0.3 + new*0.7).
    """
    method = state.get("method")
    active = state.get("active_competency")
    competency_id = _resolve_competency_id(active, state=state, db_path=db_path)
    if not method or not competency_id:
        return {}

    # Déterminer le score : explicite ou implicite.
    score = None
    if state.get("feynman_score") is not None:
        score = float(state["feynman_score"])
        blend_old, blend_new = 0.3, 0.7  # feynman : signal fort
    elif state.get("evaluation_score") is not None:
        score = float(state["evaluation_score"])
        blend_old, blend_new = 0.6, 0.4  # quiz : signal modéré
    else:
        # Inference implicite
        score = _inferred_success_from_llm(
            state.get("question", ""),
            state.get("answer", ""),
            state.get("user_response", "") or "",
            model_manager,
        )
        if score is None:
            return {}
        blend_old, blend_new = 0.8, 0.2  # implicite : signal faible

    success = score >= 0.6
    # 1) method_effectiveness
    lm.record_method_outcome(competency_id, method, success, db_path=db_path)

    # 2) mastery.score avec blend
    from apps.api.db import crud
    m = crud.get_mastery(competency_id, db_path=db_path)
    if m:
        new_score = m["score"] * blend_old + score * blend_new
        crud.upsert_mastery(
            competency_id, round(new_score, 4),
            leitner_box=m["leitner_box"], status=m["status"],
            db_path=db_path,
        )

    return {"last_method_success": success, "last_inferred_score": score}
