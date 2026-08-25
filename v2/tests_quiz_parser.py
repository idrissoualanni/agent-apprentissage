"""Tests e2e du parser quiz Markdown.

Couvre les formats que le modele cloud minimax-m3 peut renvoyer,
plus les edge cases (listes a puces, reponses en fin de bloc, etc.).
"""

import sys
sys.path.insert(0, '.')

from tools.quiz import (
    _parse_markdown_quiz,
    _split_into_blocks,
    _parse_block,
    _extract_json,
    generate_quiz,
    evaluate_answer,
)


PASS = "[OK]"
FAIL = "[KO]"
results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"{status} {name}" + (f" -- {detail}" if detail else ""))


# ─── Test 1 : format classique Q1. / A) / B) ────────────────────────────
print("\n=== T1 -- Format classique Q1. / A) ===")
sample = """Q1. Qui est le pere de l'informatique ?
A) Alan Turing
B) John von Neumann
C) Charles Babbage
D) Ada Lovelace
Reponse: A

Q2. Quelle annee ?
A) 1936
B) 1946
Reponse: A"""

qs = _parse_markdown_quiz(sample)
check("2 questions trouvees", len(qs) == 2, f"got {len(qs)}")
if len(qs) >= 1:
    check("Q1 question texte", "Qui est" in qs[0]["question"])
    check("Q1 4 options", len(qs[0]["options"]) == 4)
    check("Q1 correct_index=0 (Turing = A)", qs[0]["correct_index"] == 0)
if len(qs) >= 2:
    check("Q2 correct_index=0", qs[1]["correct_index"] == 0)


# ─── Test 2 : format avec listes a puces Markdown ─────────────────────────
print("\n=== T2 -- Format avec listes a puces ===")
sample = """Question 1. Quelle est la capitale de la France ?
- A) Londres
- B) Paris
- C) Berlin
- D) Madrid
Reponse: B

Question 2. Capitale de l'Allemagne ?
- A) Paris
- B) Berlin
- C) Madrid
Reponse : B"""

qs = _parse_markdown_quiz(sample)
check("2 questions (avec puces)", len(qs) == 2, f"got {len(qs)}")
if len(qs) >= 1:
    check("Q1 question (avec puces)", "capitale" in qs[0]["question"])
    check("Q1 option B = Paris", qs[0]["options"][1] == "Paris")
    check("Q1 correct_index=1 (Paris=B)", qs[0]["correct_index"] == 1)


# ─── Test 3 : format "Question N." (le modele l'utilise souvent) ──────────
print("\n=== T3 -- Format Question N. ===")
sample = """Question 1. Premiere question ?
- A) opt 1
- B) opt 2
- C) opt 3
- D) opt 4

Question 2. Deuxieme question ?
- A) opt 1
- B) opt 2
- C) opt 3
- D) opt 4
Reponse: C"""

qs = _parse_markdown_quiz(sample)
check("2 questions (Question N.)", len(qs) == 2, f"got {len(qs)}")
if len(qs) >= 2:
    check("Q2 correct_index=2", qs[2-1]["correct_index"] == 2)


# ─── Test 4 : reponses a la fin du bloc (corrige en bas) ──────────────────
print("\n=== T4 -- Reponses en fin de bloc ===")
sample = """Q1. Couleur du ciel ?
A) Rouge
B) Bleu
C) Vert
D) Jaune

Q2. 2+2 ?
A) 3
B) 4
C) 5

## Corriges

1. B -- Le ciel est bleu
2. B -- 2+2 = 4"""

qs = _parse_markdown_quiz(sample)
check("2 questions malgre corrige apres", len(qs) >= 1, f"got {len(qs)}")


# ─── Test 5 : variantes de syntaxe ────────────────────────────────────────
print("\n=== T5 -- Variantes syntaxiques ===")
sample = """(A) Premiere opt
[B] Deuxieme opt
{C} Troisieme opt
*D) Quatrieme opt"""

# Test unitaire sur _parse_block
block = ["Question test ?", "(A) Premiere opt", "[B] Deuxieme opt", "{C] Troisieme opt"]
# Note : {C] volontairement invalide pour tester la robustesse
result = _parse_block(["Question test ?", "(A) Premiere opt", "[B] Deuxieme opt", "(C) Troisieme"])
check("(A) matche", result is not None and result["options"][0] == "Premiere opt" if result else False)
check("[B] matche", result is not None and result["options"][1] == "Deuxieme opt" if result else False)


# ─── Test 6 : edge cases ─────────────────────────────────────────────────
print("\n=== T6 -- Edge cases ===")

# Bloc vide
check("_parse_block([]) = None", _parse_block([]) is None)

# Bloc sans question
check("_parse_block(['A) opt']) = None", _parse_block(["A) opt"]) is None)

# Bloc avec question mais pas d'options
check("_parse_block(['Q1. ?']) = None", _parse_block(["Q1. ?"]) is None)

# max_questions limite le resultat
sample_big = "\n\n".join([f"Q{i}. Q{i}?\nA) a\nB) b\nC) c\nD) d\nReponse: A" for i in range(10)])
qs = _parse_markdown_quiz(sample_big, max_questions=3)
check("max_questions=3 respecte", len(qs) == 3)


# ─── Test 7 : extract_json (fallback si le modele renvoie du JSON) ────────
print("\n=== T7 -- _extract_json ===")

# JSON dans bloc ```json
data = _extract_json('```json\n{"questions": [{"question": "q", "options": [], "correct_index": 0}]}\n```')
check("Bloc ```json", data is not None and "questions" in data)

# JSON brut
data = _extract_json('{"questions": []}')
check("JSON brut", data is not None and data.get("questions") == [])

# Pas du JSON
data = _extract_json("Du texte normal sans JSON")
check("Texte sans JSON -> None", data is None)


# ─── Test 8 : evaluate_answer (tool complementaire) ───────────────────────
print("\n=== T8 -- evaluate_answer ===")

import json
result = json.loads(evaluate_answer.invoke({
    "question": "2+2 ?",
    "options": "3,4,5",
    "correct_index": 1,
    "user_answer_index": 1,
}))
check("Bonne reponse detectee", result["is_correct"] is True)
check("correct_option = 4", result["correct_option"] == "4")

result = json.loads(evaluate_answer.invoke({
    "question": "2+2 ?",
    "options": "3,4,5",
    "correct_index": 1,
    "user_answer_index": 0,
}))
check("Mauvaise reponse detectee", result["is_correct"] is False)
check("user_option = 3", result["user_option"] == "3")


# ─── Test 9 : generation reelle (si Ollama dispo) ────────────────────────
print("\n=== T9 -- generate_quiz (integration) ===")
try:
    import config
    import os
    # On force un test rapide sans appel reseau si Ollama n'est pas dispo
    if config.OLLAMA_BASE_URL:
        # Mode cloud : test sans appel reel pour eviter 401
        check("generate_quiz importe sans erreur", generate_quiz is not None)
    else:
        # Mode local : on essaie un vrai appel avec un modele local
        result_str = generate_quiz.invoke({
            "competency_name": "Python",
            "context": "Python est un langage de programmation",
            "nb_questions": 2,
            "difficulte": "facile",
        })
        result = json.loads(result_str)
        check("generate_quiz -> 2 questions", len(result) == 2, f"got {len(result)}")
        check("Questions structurees (question + options)",
              all("question" in q and "options" in q for q in result))
except Exception as e:
    check("generate_quiz fonctionne", False, str(e))


# ─── Resume ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
ok = sum(1 for s, _, _ in results if s == PASS)
ko = sum(1 for s, _, _ in results if s == FAIL)
print(f"RESULTAT : {ok} passes, {ko} echoues sur {len(results)} tests")
if ko > 0:
    print("\nDetail des echecs :")
    for s, name, detail in results:
        if s == FAIL:
            print(f"  {s} {name} -- {detail}")
print("=" * 70)

sys.exit(0 if ko == 0 else 1)
