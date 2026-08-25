"""Debug du parser."""
import sys
sys.path.insert(0, '.')
from tools.quiz import _split_into_blocks, _parse_block, RE_QUESTION_START, RE_QUESTION_NUMBER, RE_OPTION

real_response = """Question 1. En quelle annee ?
- A) 1926
- B) 1936

Question 2. Test de Turing ?
- A) Mesurer
- B) Imiter
"""

blocks = _split_into_blocks(real_response)
print(f"Blocs: {len(blocks)}")
for i, b in enumerate(blocks):
    print(f"\n--- Bloc {i} ---")
    for line in b:
        m_opt = RE_OPTION.match(line)
        m_q = RE_QUESTION_START.match(line) or RE_QUESTION_NUMBER.match(line)
        flag = ""
        if m_opt:
            flag = " [OPT]"
        elif m_q:
            flag = " [Q]"
        print(f"  {line!r}{flag}")
