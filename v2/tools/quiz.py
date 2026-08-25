"""Outil de generation de quiz interactifs.

Le modele cloud minimax-m3 renvoie naturellement du Markdown (questions
numerotees, options A/B/C/D, corrige detaille). Plutot que de forcer un
JSON strict que le modele ignore, on parse la reponse Markdown pour
extraire les questions structurées.
"""

import json
import re
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate

import config
from llm import get_llm


# ─── Prompt : on accepte le format Markdown ───────────────────────────────

QUIZ_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un expert pedagogique. Genere un quiz de {nb_questions} questions a choix multiples sur la competence suivante :

Competence : {competency_name}
Contexte du document : {context}

FORMAT ATTENDU (Markdown structure) :

Pour chaque question, utilise EXACTEMENT ce gabarit :

Q1. [Texte de la question]
A) [option 1]
B) [option 2]
C) [option 3]
D) [option 4]
Reponse: B

Q2. [Texte de la question]
A) [option 1]
B) [option 2]
C) [option 3]
D) [option 4]
Reponse: A

...

Regles :
- Chaque question DOIT avoir 4 options A, B, C, D (toujours dans cet ordre).
- La ligne "Reponse:" DOIT etre placee juste apres les 4 options.
- Une seule lettre par "Reponse:".
- Tu peux ajouter un corrige detaille apres toutes les questions (ignore).
- Commence directement par Q1. sans preamble.

Difficulte : {difficulte}."""),
])


# ─── Parser Markdown robuste ──────────────────────────────────────────────

# Patterns compiles
RE_QUESTION_START = re.compile(
    r"^\s*(?:Q|Question)\s*(\d+)\s*[\.\:\)]\s*(.+)", re.IGNORECASE
)
RE_QUESTION_NUMBER = re.compile(
    r"^\s*(\d+)[\.\:\)]\s+(.+)"
)
# Accepte : "A) opt", "A. opt", "(A) opt", "- A) opt", "* A) opt"
RE_OPTION = re.compile(
    r"^\s*[-*]?\s*[\(\[]?([A-Da-d])[\.\)\]]\s*(.+)", re.IGNORECASE
)
RE_REPONSE = re.compile(
    r"[Rr][ée]ponse\s*[\:\=]?\s*\(?\s*([A-Da-d])\b", re.IGNORECASE
)


def _split_into_blocks(content: str) -> list:
    """Decoupe le contenu en blocs (un bloc = une question + ses options).

    Heuristique : on split sur les lignes qui commencent par Q1. / Q2. / etc.
    ou Question N. ou N. (suivi d'un texte).
    """
    lines = content.split("\n")

    blocks = []
    current = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Detecte debut d'une nouvelle question
        is_new = False
        if RE_QUESTION_START.match(line):
            is_new = True
        elif RE_QUESTION_NUMBER.match(line):
            # "1. Question ..." mais pas une option numerique
            # On verifie qu'on n'a pas deja une option A/B/C/D dans le bloc
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
    """Parse un bloc en question / options / correct_index."""
    if not block:
        return None

    question_text = None
    options = []
    correct_index = None

    for line in block:
        stripped = line.strip()

        # Ligne de question (premiere ligne ou ligne "Q1. texte")
        if question_text is None:
            m = RE_QUESTION_START.match(line) or RE_QUESTION_NUMBER.match(line)
            if m:
                question_text = m.group(2).strip()
                continue

        # Ligne d'option
        m_opt = RE_OPTION.match(line)
        if m_opt and len(options) < 4:
            text = m_opt.group(2).strip()
            options.append(text)
            continue

        # Ligne de réponse
        m_rep = RE_REPONSE.search(stripped)
        if m_rep:
            letter = m_rep.group(1).upper()
            idx = ord(letter) - ord("A")
            if 0 <= idx < 4:
                correct_index = idx

    # Validation
    if not question_text or len(options) < 2:
        return None

    # Si pas de reponse detectee, on prend la 1ere option comme "correcte"
    if correct_index is None:
        correct_index = 0

    return {
        "question": question_text,
        "options": options[:4],
        "correct_index": correct_index,
    }


def _parse_markdown_quiz(content: str, max_questions: int = 10) -> list:
    """Parse une réponse Markdown du LLM en liste de questions structurées."""
    blocks = _split_into_blocks(content)

    questions = []
    for block in blocks:
        q = _parse_block(block)
        if q and q["question"] and q["options"]:
            questions.append(q)

    return questions[:max_questions]


def _extract_json(content: str) -> dict | None:
    """Fallback : tente d'extraire un objet JSON si le modèle en renvoie."""
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
                        return json.loads(content[start:i+1])
                    except json.JSONDecodeError:
                        break

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


# ─── Outil principal ──────────────────────────────────────────────────────

@tool
def generate_quiz(competency_name: str, context: str,
                  nb_questions: int = 3, difficulte: str = "moyen") -> str:
    """Genere un quiz structure sur une competence donnee.

    Args:
        competency_name: Nom de la competence a evaluer
        context: Contexte documentaire pour alimenter les questions
        nb_questions: Nombre de questions a generer (defaut: 3)
        difficulte: Niveau de difficulte (facile/moyen/difficile)

    Returns:
        JSON string contenant les questions du quiz avec options et index correct
    """
    llm = get_llm(model_name=config.OLLAMA_MODEL, temperature=0.5)

    messages = QUIZ_PROMPT.format_messages(
        nb_questions=nb_questions,
        competency_name=competency_name,
        context=context[:2000],
        difficulte=difficulte,
    )

    response = llm.invoke(messages)
    content = response.content.strip()

    # Strategie 1 : parser le Markdown (format naturel du modele)
    questions = _parse_markdown_quiz(content, max_questions=nb_questions)

    # Strategie 2 : fallback JSON si jamais le modele repond en JSON
    if not questions:
        data = _extract_json(content)
        if data and "questions" in data:
            questions = data["questions"]

    # Strategie 3 : quiz minimal
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
    """Evalue une reponse utilisateur a une question de quiz.

    Args:
        question: Texte de la question
        options: Options separees par des virgules (ex: "optA, optB, optC")
        correct_index: Index de la bonne reponse (0-based)
        user_answer_index: Index de la reponse de l'utilisateur (0-based)

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
