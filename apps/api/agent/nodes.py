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

IMPORTANT : le sujet des questions doit être EXCLUSIVEMENT le sujet d'apprentissage
mentionné par l'utilisateur dans son message ci-dessous. Si le domaine indiqué est
"ce domaine", déduis le sujet depuis le message de l'utilisateur. Ne génère JAMAIS
de questions sur un autre sujet (pas de questions sur l'IA, la technologie en
général, ou tout sujet non demandé).

Format JSON STRICT :
{{
  "questions": ["question 1", "question 2", "question 3"]
}}

Les questions doivent aller du général au spécifique (facile → difficile).
Ne donne PAS de réponse aux questions, génère seulement les questions."""),
    ("human", "{question}"),
])

# Correctif 1 : évalue le niveau réel APRÈS les réponses de l'utilisateur
DIAGNOSTIC_EVAL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un évaluateur pédagogique. Le domaine est : {domain}.
Voici les questions posées et les réponses de l'apprenant. Estime son niveau réel.

Questions :
{questions}

Réponses de l'apprenant :
{answers}

Analyse la qualité, la précision et la profondeur des réponses, puis réponds en JSON STRICT :
{{
  "estimated_level": "debutant" | "intermediaire" | "avance",
  "justification": "courte explication",
  "suggested_domain": "nom court du sujet d'apprentissage détecté (2-4 mots, français), ex: 'Fractions', 'Algèbre', 'Photosynthèse'"
}}"""),
    ("human", "Estime le niveau de l'apprenant."),
])

# Correctif 5 : validation LLM de la pertinence du contexte RAG
RELEVANCE_CHECK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un filtre de pertinence. On t'a donné une question et des extraits de documents.
Détermine si les extraits contiennent réellement une information utile pour répondre à la question.

Question : {question}

Extraits :
{context}

Réponds en JSON STRICT :
{{
  "is_relevant": true | false,
  "confidence": 0.0 à 1.0,
  "reason": "courte explication"
}}"""),
    ("human", "Les extraits sont-ils pertinents pour la question ?"),
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
    user_id = state.get("user_id", "default_user")
    profile = crud.get_profile(user_id=user_id, db_path=db_path)
    domain = profile.get("domain", "")
    question = state.get("question", "")

    # Compat LangGraph Studio : si `question` est vide, extraire depuis `messages`
    if not question and state.get("messages"):
        last = state["messages"][-1]
        content = getattr(last, "content", "")
        # Le contenu peut être une liste de parts [{'type':'text','text':...}]
        if isinstance(content, list):
            question = " ".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            ).strip()
        else:
            question = str(content).strip()

    is_meta = _is_meta_question(question)

    # Phase 1 — mémoire de session : ajouter la question de l'utilisateur à l'historique
    new_history = list(state.get("chat_history", [])) + [HumanMessage(content=question)]

    # Diagnostic uniquement si aucun domaine ET aucun diagnostic passé
    # (niveau_global est rempli par la fin du diagnostic).
    if not domain and not profile.get("niveau_global"):
        return {
            "learner_profile": profile,
            "method": "diagnostic",
            "active_competency": None,
            "rag_needed": not is_meta,
            "question": question,
            "chat_history": new_history,
        }

    return {
        "learner_profile": profile,
        "method": "scaffold",
        "active_competency": None,
        "rag_needed": not is_meta,
        "question": question,
        "chat_history": new_history,
    }


def diagnostic_node(state: AgentState, model_manager, db_path=None) -> dict:
    """Correctif 1 : génère les questions de diagnostic et pose la PREMIÈRE.

    Ne devine plus le niveau : il sera estimé après les réponses de l'utilisateur
    (voir answer_processing_node). N'écrit plus dans la DB à ce stade.
    """
    question = state.get("question", "")

    # Message meta (salutation) ou trop vague : pas de diagnostic, on accueille
    # et on demande ce que l'utilisateur veut apprendre.
    if _is_meta_question(question) or len(question.strip()) < 10:
        return {
            "method": "scaffold",
            "diagnostic_active": False,
            "answer": (
                "Salut ! 👋 Je suis ton agent d'apprentissage personnel.\n\n"
                "Dis-moi ce que tu veux apprendre — par exemple : "
                "« Je veux apprendre les fractions » ou « Apprends-moi les bases de Python » — "
                "et je commencerai par estimer ton niveau avec 3 petites questions."
            ),
        }

    llm = model_manager.get_llm("diagnostic")
    domain = state["learner_profile"].get("domain") or "ce domaine"

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

    try:
        data = json.loads(content.strip())
        questions = data.get("questions", [])
    except json.JSONDecodeError:
        questions = []

    if not questions:
        questions = [
            f"Que savez-vous sur {domain} ?",
            f"Quels concepts de {domain} vous semblent familiers ?",
            f"Qu'aimeriez-vous apprendre en {domain} ?",
        ]

    # Pose la première question, active la boucle de diagnostic
    first_question = questions[0]
    return {
        "diagnostic_questions": questions,
        "diagnostic_answers": [],
        "diagnostic_active": True,
        "diagnostic_current_index": 0,
        "method": "diagnostic",
        "answer": (
            f"Avant de commencer, j'aimerais estimer ton niveau en {domain}. "
            f"Réponds à ces {len(questions)} questions, une par une.\n\n"
            f"**Question 1/{len(questions)}** : {first_question}"
        ),
    }


def retrieval_node(state: AgentState, retriever, model_manager=None) -> dict:
    """Correctif 5 : récupère le contexte RAG avec double-check de pertinence.

    1. Recherche sémantique avec score (seuil RAG_SEMANTIC_THRESHOLD).
    2. Si des chunks passent le seuil et que RAG_DOUBLE_CHECK_ENABLED,
       validation LLM via RELEVANCE_CHECK_PROMPT.
    3. Retourne context + rag_relevant + rag_confidence + rag_reason.
    """
    from apps.api.rag.retriever import retrieve_semantic
    import apps.api.config as config

    question = state["question"]
    threshold = getattr(config, "RAG_SEMANTIC_THRESHOLD", 0.3)
    top_k = getattr(config, "TOP_K", 3)

    docs, best_score, has_relevant = retrieve_semantic(
        retriever, question, top_k=top_k, threshold=threshold
    )

    # Aucun chunk pertinent → pas de contexte
    if not has_relevant or not docs:
        return {
            "context": "",
            "rag_relevant": False,
            "rag_confidence": best_score,
            "rag_reason": f"Aucun chunk au-dessus du seuil {threshold} (best={best_score:.2f})",
        }

    context_text = format_docs(docs)

    # Double-check LLM (désactivable)
    if getattr(config, "RAG_DOUBLE_CHECK_ENABLED", True) and model_manager is not None:
        try:
            llm = model_manager.get_llm("relevance_check")
            msgs = RELEVANCE_CHECK_PROMPT.format_messages(
                question=question, context=context_text
            )
            content = llm.invoke(msgs).content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content.strip())
            is_relevant = data.get("is_relevant", True)
            confidence = float(data.get("confidence", best_score))
            reason = data.get("reason", "")
            if not is_relevant:
                return {
                    "context": "",
                    "rag_relevant": False,
                    "rag_confidence": confidence,
                    "rag_reason": f"Rejeté par LLM : {reason}",
                }
            return {
                "context": context_text,
                "rag_relevant": True,
                "rag_confidence": confidence,
                "rag_reason": reason,
            }
        except Exception as e:
            logger.warning(f"Double-check RAG échoué ({e}); on garde le contexte.")

    # Pas de double-check → on garde le contexte si le seuil est passé
    return {
        "context": context_text,
        "rag_relevant": True,
        "rag_confidence": best_score,
        "rag_reason": "Seuil de similarité atteint (double-check désactivé)",
    }


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


def _process_diagnostic_answer(state: AgentState, model_manager, db_path=None) -> dict:
    """Correctif 1 : traite une réponse de diagnostic, pose la question suivante
    ou estime le niveau final quand toutes les questions ont reçu une réponse."""
    questions = state.get("diagnostic_questions", [])
    answers = list(state.get("diagnostic_answers", []))
    index = state.get("diagnostic_current_index", 0)
    user_id = state.get("user_id", "default_user")
    # Domaine reel du profil (peut etre vide) ; version texte pour les prompts
    profile_domain = (state.get("learner_profile") or {}).get("domain") or ""
    domain = profile_domain or "ce domaine"

    # Enregistrer la réponse à la question courante
    if index < len(questions):
        answers.append(state.get("question", "").strip())
    next_index = index + 1

    # S'il reste des questions → poser la suivante
    if next_index < len(questions):
        return {
            "diagnostic_answers": answers,
            "diagnostic_current_index": next_index,
            "diagnostic_active": True,
            "method": "diagnostic",
            "answer": (
                f"**Question {next_index + 1}/{len(questions)}** : "
                f"{questions[next_index]}"
            ),
        }

    # Toutes les réponses collectées → estimer le niveau réel via le LLM
    estimated_level = "debutant"
    justification = ""
    if model_manager is not None:
        try:
            llm = model_manager.get_llm("diagnostic")
            questions_txt = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
            answers_txt = "\n".join(f"{i+1}. {a}" for i, a in enumerate(answers))
            msgs = DIAGNOSTIC_EVAL_PROMPT.format_messages(
                domain=domain, questions=questions_txt, answers=answers_txt,
            )
            content = llm.invoke(msgs).content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content.strip())
            estimated_level = data.get("estimated_level", "debutant")
            justification = data.get("justification", "")
            # Inférence du domaine si le profil n'en a pas encore
            suggested = (data.get("suggested_domain") or "").strip()
            if not profile_domain and suggested:
                profile_domain = suggested
                domain = suggested
        except Exception as e:
            logger.warning(f"Évaluation diagnostic échouée ({e}); niveau par défaut.")

    # Initialiser la maîtrise des compétences du domaine avec le niveau estimé
    level_to_score = {"debutant": 0.2, "intermediaire": 0.5, "avance": 0.8}
    initial_score = level_to_score.get(estimated_level, 0.2)
    comps = crud.get_competencies(profile_domain, db_path) if profile_domain else []
    for comp in comps:
        if crud.get_mastery(comp["id"], db_path) is None:
            crud.upsert_mastery(
                competency_id=comp["id"],
                score=initial_score,
                leitner_box=0,
                status="new",
                db_path=db_path,
            )
    crud.update_profile(
        domain=profile_domain,
        niveau_global=estimated_level,
        user_id=user_id,
        db_path=db_path,
    )

    level_label = {"debutant": "débutant", "intermediaire": "intermédiaire", "avance": "avancé"}
    return {
        "diagnostic_answers": answers,
        "diagnostic_current_index": next_index,
        "diagnostic_active": False,
        "estimated_level": estimated_level,
        "method": "diagnostic",
        "answer": (
            f"Merci ! D'après tes réponses, j'estime ton niveau en {domain} : "
            f"**{level_label.get(estimated_level, estimated_level)}**.\n\n"
            f"{justification}\n\n"
            f"Je vais adapter mes explications. Pose-moi ta première question !"
        ),
    }


def answer_processing_node(state: AgentState, model_manager=None, db_path=None) -> dict:
    """Traite la réponse utilisateur (diagnostic en boucle, quiz, ou explication Feynman)."""
    updates = {}

    # ── Correctif 1 : boucle de diagnostic ────────────────────────────────
    if state.get("diagnostic_active") and state.get("diagnostic_questions"):
        return _process_diagnostic_answer(state, model_manager, db_path)

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

    # ── Correctif 3 : récupérer le score de maîtrise de la compétence active ──
    mastery_score = None
    if active_competency:
        cid = _resolve_competency_id(active_competency, state, db_path)
        if cid is not None:
            m = crud.get_mastery(cid, db_path)
            if m:
                mastery_score = m.get("score")

    if state.get("quiz_active"):
        method = "quiz"
    elif state.get("feynman_explanation"):
        method = "feynman"
    elif state.get("force_web_search"):
        # V3 : toggle UI "recherche web" activé → on force la méthode web_search
        method = "web_search"
    elif _needs_revision(state.get("question", "")):
        method = "revision"
    elif _needs_web_search(state.get("question", "")):
        method = "web_search"
    elif mastery_score is not None:
        # Méthode basée sur la maîtrise de la compétence active (pas le niveau global)
        if mastery_score < 0.4:
            method = "scaffold"
        elif mastery_score < 0.7:
            method = "socratic"
        else:
            method = "feynman"
    elif level in ("debutant", ""):
        method = "scaffold"
    elif level == "intermediaire":
        method = "socratic"
    else:
        method = "feynman"

    # ── Phase 5 : hook ε-greedy bandit ──
    # Si on a des donnees d'efficacite pour cette competence, on exploite la
    # meilleure methode connue (1-ε) ou on explore une autre methode (ε).
    if active_competency and method in ("scaffold", "socratic", "feynman"):
        try:
            from apps.api.agent.nodes_context import _epsilon_greedy_method, _resolve_competency_id as _rcid
            cid = _rcid(active_competency, db_path=db_path)
            if cid is not None:
                method = _epsilon_greedy_method(cid, method, db_path=db_path)
        except Exception:
            pass  # pas de donnees d'efficacite → methode par defaut

    return {"method": method, "active_competency": active_competency}


def generate_node(state: AgentState, model_manager) -> dict:
    """Génère la réponse selon la méthode choisie."""
    # Ne pas écraser une réponse déjà produite (diagnostic, quiz, feynman, etc.)
    if state.get("answer") and state.get("method") in ("quiz", "feynman", "artifact", "web_search", "revision", "diagnostic"):
        return {}

    # Correctif 5 : si le RAG était requis mais non pertinent, répondre honnêtement
    if state.get("rag_needed") and state.get("rag_relevant") is False:
        reason = state.get("rag_reason", "")
        _answer = (
            "Je n'ai pas trouvé cette information dans tes documents. "
            "Je préfère ne pas inventer de réponse.\n\n"
            "Tu peux :\n"
            "- Uploader un document qui couvre ce sujet (bouton + ), ou\n"
            "- Activer la recherche web (icône globe) pour que je cherche en ligne."
        )
        return {
            "answer": _answer,
            "rag_reason": reason,
            # Phase 1 — mémoire de session : ajouter la réponse à l'historique
            "chat_history": list(state.get("chat_history", [])) + [AIMessage(content=_answer)],
        }

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
    answer = response.content

    # Correctif 4 : suffixer d'une invitation adaptée selon next_step
    next_step = state.get("next_step")
    if next_step == "expliquer":
        answer += "\n\nVeux-tu que je t'explique cette notion plus simplement ?"
    elif next_step == "approfondir":
        answer += "\n\nBien joué ! On approfondit, ou on passe à un quiz plus difficile ?"
    elif next_step == "continuer":
        answer += "\n\nOn continue sur cette lancée ?"

    return {
        "answer": answer,
        # Phase 1 — mémoire de session : ajouter la réponse à l'historique
        "chat_history": list(state.get("chat_history", [])) + [AIMessage(content=answer)],
    }


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

        # Correctif 2 : résoudre le competency_id pour la soumission du score
        competency_id = _resolve_competency_id(competency, state, db_path=None)

        n = len(questions)
        return {
            "quiz_questions": questions,
            "quiz_active": True,
            "answer": f"Voici un quiz de {n} question{'s' if n > 1 else ''} sur « {competency} ». Réponds puis valide !",
            # Correctif 2 : le quiz est livré en artefact interactif
            "artifacts": [{
                "artifact_type": "quiz",
                "title": f"Quiz — {competency}",
                "content": json.dumps(questions, ensure_ascii=False),
                "metadata": {
                    "competency_id": competency_id,
                    "competency_name": competency,
                },
            }],
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
    """Human-in-the-loop via interrupt() : pause l'exécution et attend la confirmation.

    Dans LangGraph Studio, interrupt() affiche un champ pour saisir la réponse
    (true/false ou oui/non). L'exécution reprend avec la valeur fournie via
    Command(resume=...).
    """
    from langgraph.types import interrupt

    method = state.get("method", "")

    CONFIRMATION_METHODS = {
        "quiz": "Je vais te préparer un quiz. Tu es prêt(e) ?",
        "feynman": "On va tester ta compréhension avec la méthode Feynman. C'est parti ?",
        "artifact": "Je vais créer un artefact pédagogique pour t'aider. On y va ?",
    }

    if method in CONFIRMATION_METHODS:
        # Pause l'exécution et attend la réponse de l'utilisateur
        user_response = interrupt({
            "question": CONFIRMATION_METHODS[method],
            "type": method,
        })
        # L'exécution reprend ici avec la valeur de Command(resume=...)
        accepted = user_response in (True, "true", "yes", "oui", "ok", "confirm", "1", 1)
        if accepted:
            return {
                "pending_confirmation": False,
                "user_confirmed": True,
                "confirmation_type": method,
            }
        return {
            "pending_confirmation": False,
            "user_confirmed": False,
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
            # Correctif 4 : feedback adaptatif selon le score Feynman
            if score < 0.4:
                updates["next_step"] = "expliquer"
            elif score >= 0.7:
                updates["next_step"] = "approfondir"
            else:
                updates["next_step"] = "continuer"

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
            # Correctif 4 : feedback adaptatif selon le résultat du quiz
            updates["next_step"] = "approfondir" if is_correct else "expliquer"

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
