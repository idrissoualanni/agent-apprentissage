"""Outil de génération de quiz — port V2 → V3 avec ModelManager."""

import json
import re
import logging
from langchain.tools import tool

from apps.api.agent.prompts import QUIZ_PROMPT, format_context_block
from apps.api.agent.artifacts_xml import parse_learning_artefacts

logger = logging.getLogger(__name__)

# ─── Prompt : centralisé dans apps/api/agent/prompts.py (QUIZ_PROMPT) ─────

# ─── Parser Markdown robuste ──────────────────────────────────────────────

RE_QUESTION_START = re.compile(
    r"^\s*(?:Q|Question)\s*(\d+)\s*[.:]\s*(.+)", re.IGNORECASE
)
RE_QUESTION_NUMBER = re.compile(
    r"^\s*(\d+)[.:]\s+(.+)"
)
RE_OPTION = re.compile(
    r"^\s*[-*]?\s*[\(\[]?([A-Da-d])[\.\)\]]\s*(.+)", re.IGNORECASE
)
RE_REPONSE = re.compile(
    r"[Rr][ée]ponse\s*[:=]?\s*\(?\s*([A-Da-d])\b", re.IGNORECASE
)


def _split_into_blocks(content: str) -> list:
    lines = content.split("\n")
    blocks = []
    current = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        is_new = False
        if RE_QUESTION_START.match(line):
            is_new = True
        elif RE_QUESTION_NUMBER.match(line):
            has_letter_option = any(RE_OPTION.match(l) for l in current[-5:])
            if not has_letter_option:
                is_new = True

        if is_new and current:
            blocks.append(current)
            current = []
        current.append(line)

    if current:
        blocks.append(current)

    return blocks


def _parse_block(block: list) -> dict | None:
    if not block:
        return None

    question_text = None
    options = []
    correct_index = None

    for line in block:
        stripped = line.strip()

        if question_text is None:
            m = RE_QUESTION_START.match(line) or RE_QUESTION_NUMBER.match(line)
            if m:
                question_text = m.group(2).strip()
                continue

        m_opt = RE_OPTION.match(line)
        if m_opt and len(options) < 4:
            options.append(m_opt.group(2).strip())
            continue

        m_rep = RE_REPONSE.search(stripped)
        if m_rep:
            letter = m_rep.group(1).upper()
            idx = ord(letter) - ord("A")
            if 0 <= idx < 4:
                correct_index = idx

    if not question_text or len(options) < 2:
        return None

    if correct_index is None:
        correct_index = 0

    return {
        "question": question_text,
        "options": options[:4],
        "correct_index": correct_index,
    }


def _parse_markdown_quiz(content: str, max_questions: int = 10) -> list:
    blocks = _split_into_blocks(content)
    questions = []
    for block in blocks:
        q = _parse_block(block)
        if q and q["question"] and q["options"]:
            questions.append(q)
    return questions[:max_questions]


def _extract_json(content: str) -> dict | None:
    content = content.strip()
    m = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    m = re.search(r"```\s*(\{.*?\})\s*```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    start = content.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(content[start:i + 1])
                    except json.JSONDecodeError:
                        break

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


@tool
def generate_quiz(competency_name: str, context: str,
                  nb_questions: int = 3, difficulte: str = "moyen",
                  level: str = "intermediaire", competency_id: str = "") -> str:
    """Génère un quiz structuré sur une compétence donnée.

    Args:
        competency_name: Nom de la compétence à évaluer
        context: Contexte documentaire pour alimenter les questions
        nb_questions: Nombre de questions à générer (défaut: 3)
        difficulte: Niveau de difficulté (facile/moyen/difficile)
        level: Niveau de l'apprenant (debutant/intermediaire/avance)
        competency_id: Identifiant DB de la compétence (pour l'interactivité)

    Returns:
        JSON string contenant les questions du quiz avec options et index correct
    """
    import uuid
    from apps.api.services.model_manager import MODEL_MANAGER

    # Identifiant unique de l'artefact (pour le suivi interactif).
    slug = re.sub(r"[^a-z0-9]+", "-", competency_name.lower()).strip("-") or "quiz"
    identifier = f"quiz-{slug}-{uuid.uuid4().hex[:6]}"

    llm_wrapper = MODEL_MANAGER.get_llm("quiz_generation")
    messages = QUIZ_PROMPT.format_messages(
        nb_questions=nb_questions,
        competency_name=competency_name,
        context_block=format_context_block(context[:2000]),
        difficulte=difficulte,
        level=level or "intermediaire",
        competency_id=competency_id or "",
        identifier=identifier,
    )

    response = llm_wrapper.invoke(messages)
    content = response.content.strip()

    # 1) Priorité : artefact XML <learning_artefact type="quiz">.
    questions = []
    try:
        _, artifacts = parse_learning_artefacts(content)
        for art in artifacts:
            if art.get("artifact_type") == "quiz" and art.get("content"):
                parsed = json.loads(art["content"])
                if isinstance(parsed, list) and parsed:
                    questions = parsed
                    break
    except (json.JSONDecodeError, TypeError):
        questions = []

    # 2) Repli : Markdown structuré (ancien format).
    if not questions:
        questions = _parse_markdown_quiz(content, max_questions=nb_questions)

    # 3) Repli : JSON brut.
    if not questions:
        data = _extract_json(content)
        if data and "questions" in data:
            questions = data["questions"]

    if not questions:
        questions = [{
            "question": f"Que savez-vous sur {competency_name} ?",
            "options": ["Bien", "Moyennement", "Pas du tout"],
            "correct_index": 0,
        }]

    return json.dumps(questions, ensure_ascii=False)


@tool
def evaluate_answer(question: str, options: str, correct_index: int,
                    user_answer_index: int) -> str:
    """Évalue une réponse utilisateur à une question de quiz.

    Args:
        question: Texte de la question
        options: Options séparées par des virgules (ex: "optA, optB, optC")
        correct_index: Index de la bonne réponse (0-based)
        user_answer_index: Index de la réponse de l'utilisateur (0-based)

    Returns:
        JSON string avec is_correct, correct_option, user_option
    """
    options_list = [o.strip() for o in options.split(",")]
    is_correct = user_answer_index == correct_index
    result = {
        "is_correct": is_correct,
        "correct_option": options_list[correct_index] if correct_index < len(options_list) else "N/A",
        "user_option": options_list[user_answer_index] if user_answer_index < len(options_list) else "N/A",
    }
    return json.dumps(result, ensure_ascii=False)
