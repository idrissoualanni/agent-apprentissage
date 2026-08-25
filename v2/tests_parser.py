"""Test du parser Markdown -> quiz."""
import sys
sys.path.insert(0, '.')
from tools.quiz import _parse_markdown_quiz

sample = """# Quiz IA

Question 1. En quelle annee ?
- A) 1926
- B) 1936
- C) 1946
- D) 1956

Question 2. Qui ?
A) Turing
B) Von Neumann
- C) Shannon
(D) Minsky

Reponse: B pour la 1, A pour la 2

3. Question 3 ?
1. opt 1
2. opt 2
3. opt 3
4. opt 4
Reponse : 2

Q4: Question 4 ?
(A) opt1
(B) opt2
(C) opt3
(D) opt4
**Reponse:** C
"""

result = _parse_markdown_quiz(sample, max_questions=10)
print(f"Parse: {len(result)} questions trouvees")
for i, q in enumerate(result, 1):
    print(f"  Q{i}: {q['question'][:40]}")
    print(f"    options: {q['options']}")
    print(f"    correct_index: {q['correct_index']}")
