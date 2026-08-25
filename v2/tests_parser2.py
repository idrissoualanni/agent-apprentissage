"""Test du parser avec la vraie reponse de minimax-m3."""
import sys
sys.path.insert(0, '.')
from tools.quiz import _parse_markdown_quiz

# Reponse reelle tronquee de minimax-m3 (les 3 premieres questions)
real_response = """# Quiz : L'Epopee de l'Intelligence Artificielle

## Partie 1

Question 1. En quelle annee Alan Turing a-t-il publie son article fondateur ?
- A) 1926
- B) 1936
- C) 1946
- D) 1956

Question 2. Quel est l'objectif du Test de Turing ?
- A) Mesurer la vitesse de calcul
- B) Determiner si une machine peut imiter la conversation humaine
- C) Verifier la fiabilite d'un algorithme
- D) Tester la memoire d'un programme

Question 3. Vrai ou Faux : La conference de Dartmouth (1956) est nee l'IA ?

## Partie 2

Question 4. Qu'est-ce qu'un systeme expert ?
- A) Un reseau de neurones profonds
- B) Un programme qui reproduit le raisonnement d'un specialiste
- C) Un robot humanoide
- D) Un modele generatif de texte

Reponse : B

Question 5. Limite des systemes experts ?
- A) Consommation electrique
- B) Incapacite d'apprendre
- C) Anglais uniquement
- D) Necessite Internet
"""

result = _parse_markdown_quiz(real_response, max_questions=10)
print(f"Parse: {len(result)} questions trouvees")
for i, q in enumerate(result, 1):
    print(f"  Q{i}: {q['question'][:60]}")
    print(f"    options: {q['options']}")
    print(f"    correct_index: {q['correct_index']}")
    print()
