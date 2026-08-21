"""Outil de generation de quiz interactifs."""

import json
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate

import config
from llm import get_llm

QUIZ_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un expert pedagogique. Genere un quiz de {nb_questions} questions sur la competence suivante :

Competence : {competency_name}
Contexte du document : {context}

Format de sortie JSON STRICT (uniquement le JSON, rien d'autre) :
{{
  "questions": [
    {{
      "question": "texte de la question",
      "options": ["option A", "option B", "option C", "option D"],
      "correct_index": 0
    }}
  ]
}}

Niveau de difficulte : {difficulte}
Les questions doivent tester la comprehension, pas la memorisation brute."""),
])


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
    llm = get_llm(model=config.OLLAMA_MODEL, temperature=0.5)

    messages = QUIZ_PROMPT.format_messages(
        nb_questions=nb_questions,
        competency_name=competency_name,
        context=context[:2000],
        difficulte=difficulte,
    )

    response = llm.invoke(messages)
    content = response.content.strip()

    # Nettoyage : extraire le JSON si entoure de markdown
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        data = json.loads(content.strip())
        return json.dumps(data.get("questions", []), ensure_ascii=False)
    except json.JSONDecodeError:
        fallback = [{
            "question": f"Que savez-vous sur {competency_name} ?",
            "options": ["Je connais bien", "J'ai des notions", "Je ne sais pas"],
            "correct_index": 0,
        }]
        return json.dumps(fallback, ensure_ascii=False)


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
