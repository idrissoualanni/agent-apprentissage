"""Nœuds du StateGraph V3 — router, diagnostic, retrieval, method, generate, eval, tool, confirmation.

Port de graph/nodes.py V2 vers V3 avec :
- model_manager au lieu de model_name
- Imports apps.api.*
- Tool transparency tracking
- user_id sur les appels DB
"""

import json
import time
import logging
from typing import Optional

from apps.api.agent.state import AgentState
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from apps.api.agent.tools.quiz import generate_quiz, evaluate_answer
from apps.api.agent.tools.feynman import evaluate_feynman
from apps.api.agent.tools.progress import update_mastery_after_quiz, update_mastery_after_feynman
from apps.api.agent.tools.artifact import create_artifact
from apps.api.db import crud
import apps.api.config as config

logger = logging.getLogger(__name__)


# ─── Prompt templates ─────────────────────────────────────────────────────

SOCRATIC_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un tuteur socratique. L'utilisateur apprend : {competency_name}.
Contexte : {context}
Niveau estimé : {level}

Ne donne JAMAIS la réponse directement. Guide par des questions.
Si le niveau est faible, commence par des questions simples.
Si le niveau est moyen, pousse la réflexion.
Réponds en français, ton bienveillant mais exigeant."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{question}"),
])

FEYNMAN_PROMPT_NODE = ChatPromptTemplate.from_messages([
    ("system", """Demande à l'utilisateur d'expliquer la notion suivante avec ses propres mots (méthode Feynman) :
Notion : {competency_name}
Contexte : {context}

Formule une invitation claire : "Explique-moi comme si j'avais 12 ans..."
Si l'utilisateur a déjà fourni une explication, évalue-la."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{question}"),
])

SCAFFOLD_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu expliques une notion nouvelle de manière progressive.
Notion : {competency_name}
Contexte : {context}

Structure :
1. Définition simple en une phrase
2. Analogie concrète
3. Exemple détaillé
4. Point de vigilance (erreur fréquente)

Réponds en français, ton pédagogique."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{question}"),
])

DIAGNOSTIC_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un évaluateur pédagogique. Le domaine est : {domain}.
Génère 3 questions calibrées pour estimer le niveau de l'utilisateur.

Format JSON STRICT :
{{
  "questions": ["question 1", "question 2", "question 3"],
  "estimated_level": "debutant" | "intermediaire" | "avance"
}}

Les questions doivent aller du général au spécifique."""),
    ("human", "{question}"),
])

RESPONSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un assistant pédagogique. Réponds à la question en t'appuyant sur le contexte.
Contexte : {context}
Méthode en cours : {method}
Si tu ne sais pas, dis-le honnêtement."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{question}"),
])


def format_docs(documents) -> str:
    return "\n\n".join(doc.page_content for doc in documents) if documents else ""


# ─── Helpers ──────────────────────────────────────────────────────────────

def _track_tool(state: AgentState, name: str, duration_ms: float, success: bool):
    """Ajoute une entrée de transparence d'outil à l'état."""
    transparency = state.get("tool_transparency") or []
    transparency.append({"name": name, "duration_ms": round(duration_ms, 1), "success": success})
    return transparency


# ─── Nœuds ────────────────────────────────────────────────────────────────

def _is_meta_question(question: str) -> bool:
    """Détecte si la question est une salutation, question méta, ou hors-sujet pédagogique."""
    import re
    q = question.lower().strip()

    META_PATTERNS = [
        r"^(salut|bonjour|bonsoir|coucou|hello|hi|hey|yo|wesh)\s*[!.?]*$",
        r"^(bonne\s*journée|bonne\s*soirée|à\s*bientôt|au\s*revoir|bye|ciao)\s*[!.?]*$",
        r"^(qui\s*es[- ]tu|que\s*sais[- ]tu|tu\s*sais\s*faire|t['\u2019]es\s*un\s*bot)",
        r"^(quel\s*est\s*ton\s*(nom|rôle|but|objectif))",
        r"^(merci|thanks|super|bien|ok|parfait|excellent|genial|bravo|top|cool)\s*[!.?]*$",
        r"^(oui|non|peut[- ]être|jsp|bof)\s*[!.?]*$",
    ]

    for pattern in META_PATTERNS:
        if re.match(pattern, q):
            return True

    words = q.split()
    PEDAGOGICAL_HINTS = [
        "explique", "comprendre", "pourquoi", "comment", "qu'est-ce", "quel", "quelle",
        "donne", "montre", "défini", "exemple", "résumé", "révise", "apprend",
        "quiz", "test", "éval", "notion", "concept", "théorie", "cours",
    ]
    if len(words) < 4 and not any(h in q for h in PEDAGOGICAL_HINTS):
        return True

    return False


def _needs_web_search(question: str) -> bool:
    """Détecte si la question nécessite une recherche web."""
    import re
    q = question.lower().strip()
    WEB_PATTERNS = [
        r"(prix|cours|taux|valeur|chiffre)\s+(du|de la|des|d')",
        r"(dernière?|nouveau|récent|actuel|aujourd'hui|ce\s+mois|cette\s+année)",
        r"(actualité|news|événement|sommert|breaking)",
        r"(combien\s+coûte|quel\s+prix|que\s+vaut)",
        r"(stock|action|crypto|bitcoin|ethereum)",
        r"(météo|weather|température)",
        r"(score|résultat|match|coupe|championnat)",
    ]
    for pattern in WEB_PATTERNS:
        if re.search(pattern, q):
            return True
    return False


def _needs_revision(question: str) -> bool:
    """Détecte si l'utilisateur demande une révision / rappel."""
    import re
    q = question.lower().strip()
    REVISION_PATTERNS = [
        r"\br[ée]vis", r"\brevision", r"\brévision", r"\brappel",
        r"\brevoir\b", r"\brattrap", r"\bexercice.*r[ée]vis",
        r"\bqu.*r[ée]viser", r"\bque.*dois.*r[ée]viser",
        r"\bplan.*r[ée]vision", r"\bcarte.*mémoire",
    ]
    for pattern in REVISION_PATTERNS:
        if re.search(pattern, q):
            return True
    return False


def router_profil_node(state: AgentState, retriever, model_manager, db_path=None) -> dict:
    """Charge le profil et décide du premier routing (diagnostic vs retrieval)."""
    profile = crud.get_profile(db_path=db_path)
    domain = profile.get("domain", "")
    question = state.get("question", "")

    is_meta = _is_meta_question(question)

    if not domain:
        return {
            "learner_profile": profile,
            "method": "diagnostic",
            "active_competency": None,
            "rag_needed": not is_meta,
        }

    return {
        "learner_profile": profile,
        "method": "scaffold",
        "active_competency": None,
        "rag_needed": not is_meta,
    }


def diagnostic_node(state: AgentState, model_manager, db_path=None) -> dict:
    """Pose des questions de diagnostic si le profil est incomplet."""
    llm = model_manager.get_llm("diagnostic")
    domain = state["learner_profile"].get("domain", "ce domaine")

    messages = DIAGNOSTIC_PROMPT.format_messages(
        domain=domain,
        question=state["question"],
    )

    response = llm.invoke(messages)
    content = response.content.strip()

    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    estimated_level = "debutant"
    try:
        data = json.loads(content.strip())
        questions = data.get("questions", [])
        estimated_level = data.get("estimated_level", "debutant")
    except json.JSONDecodeError:
        questions = [f"Que savez-vous sur {domain} ?"]

    comps = crud.get_competencies(domain, db_path)
    level_to_score = {"debutant": 0.2, "intermediaire": 0.5, "avance": 0.8}
    initial_score = level_to_score.get(estimated_level, 0.2)

    for comp in comps:
        existing = crud.get_mastery(comp["id"], db_path)
        if existing is None:
            crud.upsert_mastery(
                competency_id=comp["id"],
                score=initial_score,
                leitner_box=0,
                status="new",
                db_path=db_path,
            )

    crud.update_profile(domain=domain, niveau_global=estimated_level, db_path=db_path)

    return {
        "diagnostic_questions": questions,
        "estimated_level": estimated_level,
        "method": "diagnostic",
        "answer": response.content,
    }


def retrieval_node(state: AgentState, retriever) -> dict:
    """Récupère le contexte RAG."""
    docs = retriever.invoke(state["question"])
    return {"context": format_docs(docs)}


def _detect_active_competency(question: str, domain: str, db_path) -> Optional[str]:
    """Détecte la compétence la plus pertinente depuis la question (matching simple)."""
    if not domain:
        return None
    comps = crud.get_competencies(domain, db_path)
    if not comps:
        return None

    question_lower = question.lower()
    best_match = None
    best_score = 0

    for comp in comps:
        score = 0
        nom_lower = comp["nom"].lower()
        desc_lower = (comp.get("description") or "").lower()

        if nom_lower in question_lower:
            score += 10
        for word in nom_lower.split():
            if len(word) > 3 and word in question_lower:
                score += 2
        for word in desc_lower.split():
            if len(word) > 4 and word in question_lower:
                score += 1

        if score > best_score:
            best_score = score
            best_match = comp["nom"]

    return best_match if best_score >= 2 else None


def answer_processing_node(state: AgentState, db_path=None) -> dict:
    """Traite la réponse utilisateur si on attend une réponse quiz ou une explication Feynman."""
    updates = {}

    if state.get("quiz_active") and state.get("quiz_questions"):
        user_input = state["question"].strip()

        try:
            user_idx = int(user_input) - 1
        except ValueError:
            q = state["quiz_questions"][0]
            options = q.get("options", [])
            user_idx = -1
            for i, opt in enumerate(options):
                if opt.lower() in user_input.lower() or user_input.lower() in opt.lower():
                    user_idx = i
                    break

        if user_idx >= 0:
            q = state["quiz_questions"][0]
            result_str = evaluate_answer.invoke({
                "question": q["question"],
                "options": ",".join(q.get("options", [])),
                "correct_index": q.get("correct_index", 0),
                "user_answer_index": user_idx,
            })
            result = json.loads(result_str)

            updates.update({
                "evaluation_score": 1.0 if result["is_correct"] else 0.0,
                "quiz_active": False,
                "quiz_questions": [],
                "answer": f"{'✅ Correct !' if result['is_correct'] else '❌ Incorrect.'} La bonne réponse était : {result['correct_option']}",
            })
        else:
            updates["answer"] = "Je n'ai pas compris votre réponse. Veuillez indiquer le numéro (1-4) ou le texte de l'option choisie."

    elif state.get("awaiting_feynman_explanation") and not state.get("feynman_explanation"):
        updates.update({
            "feynman_explanation": state["question"],
            "awaiting_feynman_explanation": False,
        })

    return updates


def method_selection_node(state: AgentState, db_path=None) -> dict:
    """Choisit la méthode pédagogique selon le niveau, l'historique et la compétence active."""
    profile = state.get("learner_profile", {})
    level = profile.get("niveau_global", "")
    domain = profile.get("domain", "")

    active_competency = state.get("active_competency")
    if not active_competency and not state.get("quiz_active") and not state.get("feynman_explanation"):
        active_competency = _detect_active_competency(state["question"], domain, db_path)

    if state.get("quiz_active"):
        method = "quiz"
    elif state.get("feynman_explanation"):
        method = "feynman"
    elif _needs_revision(state.get("question", "")):
        method = "revision"
    elif _needs_web_search(state.get("question", "")):
        method = "web_search"
    elif level in ("debutant", ""):
        method = "scaffold"
    elif level == "intermediaire":
        method = "socratic"
    else:
        method = "feynman"

    return {"method": method, "active_competency": active_competency}


def generate_node(state: AgentState, model_manager) -> dict:
    """Génère la réponse selon la méthode choisie."""
    if state.get("answer") and state.get("method") in ("quiz", "feynman", "artifact", "web_search", "revision"):
        return {}

    llm = model_manager.get_llm("answer")
    method = state.get("method", "scaffold")
    context = state.get("context", "")
    competency = state.get("active_competency", "ce sujet")
    level = state.get("estimated_level", state.get("learner_profile", {}).get("niveau_global", ""))

    if method == "socratic":
        prompt = SOCRATIC_PROMPT
    elif method == "feynman":
        prompt = FEYNMAN_PROMPT_NODE
    elif method == "scaffold":
        prompt = SCAFFOLD_PROMPT
    elif method == "diagnostic":
        prompt = DIAGNOSTIC_PROMPT
    else:
        prompt = RESPONSE_PROMPT

    profile = state.get("learner_profile", {})
    domain = profile.get("domain", "ce domaine")

    format_kwargs = {
        "context": context,
        "competency_name": competency,
        "level": level,
        "method": method,
        "chat_history": state.get("chat_history", []),
        "question": state["question"],
    }

    if method == "diagnostic":
        format_kwargs = {"domain": domain, "question": state["question"]}

    messages = prompt.format_messages(**format_kwargs)
    response = llm.invoke(messages)
    return {"answer": response.content}


def tool_execution_node(state: AgentState, model_manager) -> dict:
    """Exécute l'outil demandé (quiz, feynman, web_search, revision, artifact) via @tool.invoke()."""
    t0 = time.time()
    tool = state.get("method")
    context = state.get("context", "")
    competency = state.get("active_competency", "ce sujet")
    user_id = state.get("user_id", "default_user")

    if tool == "quiz":
        result_str = generate_quiz.invoke({
            "competency_name": competency,
            "context": context,
            "nb_questions": 3,
            "difficulte": "moyen",
        })
        questions = json.loads(result_str)
        elapsed = (time.time() - t0) * 1000
        return {
            "quiz_questions": questions,
            "quiz_active": True,
            "answer": _format_quiz_for_display(questions),
            "tool_transparency": _track_tool(state, "generate_quiz", elapsed, True),
        }

    elif tool == "feynman":
        if state.get("feynman_explanation"):
            result_str = evaluate_feynman.invoke({
                "topic": competency,
                "context": context,
                "explanation": state["feynman_explanation"],
            })
            result = json.loads(result_str)
            elapsed = (time.time() - t0) * 1000
            return {
                "feynman_score": result.get("score", 0.5),
                "feynman_gaps": str(result.get("gaps", [])),
                "answer": result.get("feedback", "Bien essayé !"),
                "tool_transparency": _track_tool(state, "evaluate_feynman", elapsed, True),
            }
        else:
            return {
                "answer": f"Explique-moi '{competency}' comme si j'avais 12 ans. Utilise tes propres mots.",
                "awaiting_feynman_explanation": True,
            }

    elif tool == "web_search":
        from apps.api.agent.tools.web_search import web_search
        result_str = web_search.invoke({"query": state["question"], "num_results": 3})
        results = json.loads(result_str)
        elapsed = (time.time() - t0) * 1000
        if isinstance(results, dict) and "error" in results:
            return {
                "answer": f"Erreur de recherche web : {results['error']}",
                "tool_transparency": _track_tool(state, "web_search", elapsed, False),
            }
        lines = ["### Résultats web\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"**{i}. [{r['title']}]({r['url']})**")
            lines.append(f"{r['snippet']}\n")
        return {
            "answer": "\n".join(lines),
            "web_search_results": results,
            "tool_transparency": _track_tool(state, "web_search", elapsed, True),
        }

    elif tool == "revision":
        from apps.api.agent.tools.progress import get_revision_plan
        domain = state.get("learner_profile", {}).get("domain", "")
        result_str = get_revision_plan.invoke({"domain": domain})
        result = json.loads(result_str)
        plan = result.get("plan", [])
        elapsed = (time.time() - t0) * 1000
        if not plan:
            return {
                "answer": result.get("message", "Aucune révision nécessaire. ✅"),
                "tool_transparency": _track_tool(state, "get_revision_plan", elapsed, True),
            }
        lines = [f"### 📅 Plan de révision — {result.get('message','')}\n"]
        for i, item in enumerate(plan, 1):
            lines.append(f"**{i}. {item['nom']}** — box {item['leitner_box']}, score {item['score']:.0%}")
            lines.append(f"   Prochaine révision : {item['next_review']}\n")
        if result.get("total_due", 0) > len(plan):
            lines.append(f"_…et {result['total_due'] - len(plan)} autre(s) en attente._")
        return {
            "answer": "\n".join(lines),
            "tool_transparency": _track_tool(state, "get_revision_plan", elapsed, True),
        }

    elif tool == "artifact":
        artifact_type = state.get("tool_result", "schema")
        level = state.get("estimated_level",
                           state.get("learner_profile", {}).get("niveau_global", "intermediaire"))
        result_str = create_artifact.invoke({
            "topic": competency,
            "context": context,
            "artifact_type": artifact_type,
            "level": level,
        })
        result = json.loads(result_str)
        elapsed = (time.time() - t0) * 1000
        title = result.get("title", "Artefact")
        content_md = result.get("content", "")
        answer_md = f"### :material/draw: {title}\n\n{content_md}"

        artifact_record = {"type": artifact_type, "title": title, "content": content_md}
        artifacts = state.get("artifacts") or []
        artifacts.append(artifact_record)

        return {
            "answer": answer_md,
            "artifacts": artifacts,
            "tool_transparency": _track_tool(state, "create_artifact", elapsed, True),
        }

    return {"answer": ""}


def confirmation_node(state: AgentState) -> dict:
    """Human-in-the-loop : demande confirmation avant d'exécuter un outil lourd."""
    method = state.get("method", "")
    user_confirmed = state.get("user_confirmed")

    CONFIRMATION_METHODS = {
        "quiz": "Je vais te préparer un quiz. Tu es prêt(e) ?",
        "feynman": "On va tester ta compréhension avec la méthode Feynman. C'est parti ?",
        "artifact": "Je vais créer un artefact pédagogique pour t'aider. On y va ?",
    }

    if user_confirmed is None and method in CONFIRMATION_METHODS:
        return {
            "pending_confirmation": True,
            "confirmation_type": method,
            "confirmation_prompt": CONFIRMATION_METHODS[method],
        }

    if user_confirmed is True:
        return {
            "pending_confirmation": False,
            "user_confirmed": None,
        }

    if user_confirmed is False:
        return {
            "pending_confirmation": False,
            "user_confirmed": None,
            "method": "scaffold",
            "answer": "Pas de souci, on fait autre chose ! Pose-moi une question.",
        }

    return {}


def evaluation_memory_node(state: AgentState, db_path=None) -> dict:
    """Traite le résultat et met à jour la progression en base."""
    updates = {}
    user_id = state.get("user_id", "default_user")

    if state.get("feynman_score") is not None:
        competency_name = state.get("active_competency")
        score = state["feynman_score"]

        competency_id = _resolve_competency_id(competency_name, state, db_path)

        if competency_id is not None:
            result_str = update_mastery_after_feynman.invoke({
                "competency_id": competency_id,
                "score": score,
            })
            result = json.loads(result_str)
            updates["leitner_action"] = "promote" if score >= 0.7 else "demote" if score < 0.4 else "stay"

            session_id = _resolve_session_id(state, db_path)
            if session_id is not None:
                crud.record_feynman_restitution(
                    competency_id=competency_id,
                    user_explanation=state.get("feynman_explanation", ""),
                    agent_evaluation=state.get("answer", ""),
                    score=score,
                    gaps_identified=state.get("feynman_gaps", "[]"),
                    session_id=session_id,
                    db_path=db_path,
                )

    elif state.get("evaluation_score") is not None:
        competency_name = state.get("active_competency")
        is_correct = state["evaluation_score"] >= 0.6

        competency_id = _resolve_competency_id(competency_name, state, db_path)

        if competency_id is not None:
            result_str = update_mastery_after_quiz.invoke({
                "competency_id": competency_id,
                "is_correct": is_correct,
            })
            result = json.loads(result_str)
            updates["leitner_action"] = "promote" if is_correct else "demote"

            session_id = _resolve_session_id(state, db_path)
            quiz_questions = state.get("quiz_questions", [])
            if session_id is not None and quiz_questions:
                q = quiz_questions[0]
                crud.record_quiz_attempt(
                    competency_id=competency_id,
                    question=q.get("question", ""),
                    options=",".join(q.get("options", [])),
                    user_answer=str(state.get("answer", "")),
                    is_correct=is_correct,
                    session_id=session_id,
                    db_path=db_path,
                )

    return updates


def _resolve_competency_id(competency_name: Optional[str], state: AgentState, db_path=None) -> Optional[int]:
    """Résout le nom de compétence en ID via la base."""
    if not competency_name:
        return None
    profile = state.get("learner_profile", {})
    domain = profile.get("domain", "")
    if not domain:
        return None
    comps = crud.get_competencies(domain, db_path)
    for c in comps:
        if c["nom"] == competency_name:
            return c["id"]
    return None


def _resolve_session_id(state: AgentState = None, db_path=None) -> Optional[int]:
    """Récupère l'ID de la session correspondant au thread_id actif."""
    path = db_path or config.DB_PATH

    if not Path(path).exists():
        return None

    thread_id = (state or {}).get("thread_id") if state else None

    with crud.get_connection(path) as conn:
        if thread_id:
            row = conn.execute(
                "SELECT id FROM session WHERE langgraph_thread_id = ?",
                (thread_id,),
            ).fetchone()
            if row:
                return row["id"]
        row = conn.execute(
            "SELECT id FROM session ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None


def _format_quiz_for_display(questions: list) -> str:
    """Texte court d'introduction pour le quiz."""
    n = len(questions)
    return f":material/quiz: **Quiz** — {n} question{'s' if n != 1 else ''} prête{'s' if n != 1 else ''}. Réponds ci-dessous."


# ─── Import manquant ──────────────────────────────────────────────────────
from pathlib import Path
