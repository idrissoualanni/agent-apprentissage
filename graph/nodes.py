"""Nœuds du StateGraph — router, diagnostic, retrieval, method, generate, eval."""

import json
from typing import Optional
from graph.state import AgentState
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tools.quiz import generate_quiz, evaluate_answer
from tools.feynman import evaluate_feynman
from tools.progress import update_mastery_after_quiz, update_mastery_after_feynman
from tools.artifact import create_artifact
from db import db

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


# ─── Nœuds ────────────────────────────────────────────────────────────────

def router_profil_node(state: AgentState, retriever, model_name: str, db_path=None) -> dict:
    """Charge le profil et décide du premier routing (diagnostic vs retrieval)."""
    profile = db.get_profile(db_path)
    domain = profile.get("domain", "")

    # Si pas de domaine défini, mode diagnostic
    if not domain:
        return {
            "learner_profile": profile,
            "method": "diagnostic",
            "active_competency": None,
        }

    # Sinon, on va vers retrieval (pas de double appel ici)
    return {
        "learner_profile": profile,
        "method": "scaffold",  # par défaut, sera affiné par method_selection
        "active_competency": None,
    }


def diagnostic_node(state: AgentState, model_name: str, db_path=None) -> dict:
    """Pose des questions de diagnostic si le profil est incomplet."""
    llm = ChatOllama(model=model_name, temperature=0.3)
    domain = state["learner_profile"].get("domain", "ce domaine")

    messages = DIAGNOSTIC_PROMPT.format_messages(
        domain=domain,
        question=state["question"],
    )

    response = llm.invoke(messages)
    content = response.content.strip()

    # Parsing JSON
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

    # Écrire l'estimation initiale en mastery pour chaque compétence du domaine
    from db import db as db_module
    comps = db_module.get_competencies(domain, db_path)
    level_to_score = {"debutant": 0.2, "intermediaire": 0.5, "avance": 0.8}
    initial_score = level_to_score.get(estimated_level, 0.2)

    for comp in comps:
        existing = db_module.get_mastery(comp["id"], db_path)
        if existing is None:
            db_module.upsert_mastery(
                competency_id=comp["id"],
                score=initial_score,
                leitner_box=0,
                status="new",
                db_path=db_path,
            )

    # Mettre à jour le profil global
    db_module.update_profile(domain, estimated_level, db_path)

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
    """Détecte la compétence la plus pertinente depuis la question (matching simple).
    
    Stratégie : matching mots-clés sur nom + description des compétences du domaine.
    Pas d'appel LLM pour éviter la latence à chaque tour.
    """
    if not domain:
        return None
    from db import db as db_module
    comps = db_module.get_competencies(domain, db_path)
    if not comps:
        return None
    
    question_lower = question.lower()
    best_match = None
    best_score = 0
    
    for comp in comps:
        score = 0
        nom_lower = comp["nom"].lower()
        desc_lower = (comp.get("description") or "").lower()
        
        # Match exact sur le nom (poids fort)
        if nom_lower in question_lower:
            score += 10
        # Match mots du nom
        for word in nom_lower.split():
            if len(word) > 3 and word in question_lower:
                score += 2
        # Match description
        for word in desc_lower.split():
            if len(word) > 4 and word in question_lower:
                score += 1
        
        if score > best_score:
            best_score = score
            best_match = comp["nom"]
    
    return best_match if best_score >= 2 else None


def answer_processing_node(state: AgentState, db_path=None) -> dict:
    """Traite la réponse utilisateur si on attend une réponse quiz ou une explication Feynman.
    
    Ce nœud doit s'exécuter AVANT method_selection_node pour capturer la réponse
    et la router vers l'évaluation au lieu de générer un nouveau quiz/explication.
    """
    updates = {}
    
    # --- Cas 1 : Réponse à un quiz en attente ---
    if state.get("quiz_active") and state.get("quiz_questions"):
        # L'utilisateur répond au quiz, pas une nouvelle question
        from tools.quiz import evaluate_answer
        import json
        
        # On suppose que la réponse est l'index choisi (0-3) ou le texte de l'option
        user_input = state["question"].strip()
        
        # Essayer de parser comme index
        try:
            user_idx = int(user_input) - 1  # Utilisateur 1-based, interne 0-based
        except ValueError:
            # Sinon, matcher contre les options
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
            # Réponse non reconnue, on garde quiz_active pour réessayer
            updates["answer"] = "Je n'ai pas compris votre réponse. Veuillez indiquer le numéro (1-4) ou le texte de l'option choisie."
    
    # --- Cas 2 : Explication Feynman attendue ---
    elif state.get("awaiting_feynman_explanation") and not state.get("feynman_explanation"):
        # L'utilisateur fournit son explication
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

    # Détecter la compétence active depuis la question (si pas déjà en quiz/feynman)
    active_competency = state.get("active_competency")
    if not active_competency and not state.get("quiz_active") and not state.get("feynman_explanation"):
        active_competency = _detect_active_competency(state["question"], domain, db_path)

    if state.get("quiz_active"):
        method = "quiz"
    elif state.get("feynman_explanation"):
        method = "feynman"
    elif level in ("debutant", ""):
        method = "scaffold"
    elif level == "intermediaire":
        method = "socratic"
    else:
        method = "feynman"

    return {"method": method, "active_competency": active_competency}


def generate_node(state: AgentState, model_name: str) -> dict:
    """Génère la réponse selon la méthode choisie.
    
    Si une réponse a déjà été fournie par tool_execution_node (quiz, feynman, artifact),
    on la garde telle quelle — pas de re-génération.
    """
    # Si le tool a déjà produit une réponse, la conserver
    if state.get("answer") and state.get("method") in ("quiz", "feynman", "artifact"):
        return {}

    llm = ChatOllama(model=model_name, temperature=0.3)
    method = state.get("method", "scaffold")
    context = state.get("context", "")
    competency = state.get("active_competency", "ce sujet")
    level = state.get("estimated_level", state.get("learner_profile", {}).get("niveau_global", ""))

    # Sélection du prompt selon la méthode
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

    # DIAGNOSTIC_PROMPT attend {domain} au lieu des autres variables
    if method == "diagnostic":
        format_kwargs = {
            "domain": domain,
            "question": state["question"],
        }

    messages = prompt.format_messages(**format_kwargs)

    response = llm.invoke(messages)
    return {"answer": response.content}


def tool_execution_node(state: AgentState, model_name: str) -> dict:
    """Exécute l'outil demandé (quiz ou feynman) via @tool.invoke()."""
    tool = state.get("method")  # method_selection_node définit le type d'outil
    context = state.get("context", "")
    competency = state.get("active_competency", "ce sujet")

    if tool == "quiz":
        # Appel via @tool.invoke()
        result_str = generate_quiz.invoke({
            "competency_name": competency,
            "context": context,
            "nb_questions": 3,
            "difficulte": "moyen",
        })
        questions = json.loads(result_str)
        return {
            "quiz_questions": questions,
            "quiz_active": True,
            "answer": _format_quiz_for_display(questions),
        }

    elif tool == "feynman":
        if state.get("feynman_explanation"):
            # Évaluation via @tool.invoke()
            result_str = evaluate_feynman.invoke({
                "topic": competency,
                "context": context,
                "explanation": state["feynman_explanation"],
            })
            result = json.loads(result_str)
            return {
                "feynman_score": result.get("score", 0.5),
                "feynman_gaps": str(result.get("gaps", [])),
                "answer": result.get("feedback", "Bien essayé !"),
            }
        else:
            # On demande l'explication, marquer qu'on l'attend au tour suivant
            return {
                "answer": f"Explique-moi '{competency}' comme si j'avais 12 ans. Utilise tes propres mots.",
                "awaiting_feynman_explanation": True,
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
        # Formatter pour affichage Markdown
        title = result.get("title", "Artefact")
        content = result.get("content", "")
        answer_md = f"### :material/draw: {title}\n\n{content}"
        return {"answer": answer_md}

    return {"answer": ""}


def evaluation_memory_node(state: AgentState, db_path=None) -> dict:
    """Traite le résultat et met à jour la progression en base."""
    from tools.progress import update_mastery_after_quiz, update_mastery_after_feynman
    updates = {}

    # --- Évaluation Feynman ---
    if state.get("feynman_score") is not None:
        competency_name = state.get("active_competency")
        score = state["feynman_score"]

        # Résoudre l'ID de la compétence
        competency_id = _resolve_competency_id(competency_name, state, db_path)

        if competency_id is not None:
            # Mettre à jour la mastery
            result_str = update_mastery_after_feynman.invoke({
                "competency_id": competency_id,
                "score": score,
            })
            result = json.loads(result_str)
            updates["leitner_action"] = "promote" if score >= 0.7 else "demote" if score < 0.4 else "stay"

            # Enregistrer la restitution Feynman
            session_id = _resolve_session_id(db_path)
            if session_id is not None:
                from db import db as db_module
                db_module.record_feynman_restitution(
                    competency_id=competency_id,
                    user_explanation=state.get("feynman_explanation", ""),
                    agent_evaluation=state.get("answer", ""),
                    score=score,
                    gaps_identified=state.get("feynman_gaps", "[]"),
                    session_id=session_id,
                    db_path=db_path,
                )

    # --- Évaluation Quiz ---
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

            # Enregistrer la tentative de quiz
            session_id = _resolve_session_id(db_path)
            if session_id is not None:
                from db import db as db_module
                quiz_questions = state.get("quiz_questions", [])
                if quiz_questions:
                    q = quiz_questions[0]
                    db_module.record_quiz_attempt(
                        competency_id=competency_id,
                        question=q.get("question", ""),
                        options=",".join(q.get("options", [])),
                        user_answer=str(state.get("answer", "")),
                        is_correct=is_correct,
                        session_id=session_id,
                        db_path=db_path,
                    )

            # Enregistrer la tentative de quiz
            session_id = _resolve_session_id(db_path)
            if session_id is not None:
                from db import db as db_module
                quiz_questions = state.get("quiz_questions", [])
                if quiz_questions:
                    q = quiz_questions[0]  # dernière question posée
                    db_module.record_quiz_attempt(
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
    from db import db as db_module
    profile = state.get("learner_profile", {})
    domain = profile.get("domain", "")
    if not domain:
        return None
    comps = db_module.get_competencies(domain, db_path)
    for c in comps:
        if c["nom"] == competency_name:
            return c["id"]
    return None


def _resolve_session_id(db_path=None) -> Optional[int]:
    """Récupère l'ID de la session active."""
    from db import db as db_module
    sessions = db_module.get_connection(db_path) if db_path else None
    # Chercher la dernière session ouverte
    import config as cfg
    path = db_path or cfg.DB_PATH
    with db_module.get_connection(path) as conn:
        row = conn.execute(
            "SELECT id FROM session ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None


def _format_quiz_for_display(questions: list) -> str:
    lines = [":material/quiz: **Quiz** — Testons tes connaissances !\n"]
    for i, q in enumerate(questions, 1):
        lines.append(f"**{i}. {q['question']}**")
        for j, opt in enumerate(q.get("options", []), 1):
            lines.append(f"   {j}. {opt}")
        lines.append("")
    return "\n".join(lines)
