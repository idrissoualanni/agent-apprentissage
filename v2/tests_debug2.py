"""Debug parse_block."""
import sys
sys.path.insert(0, '.')
from tools.quiz import _parse_block, RE_OPTION, RE_REPONSE, RE_QUESTION_START, RE_QUESTION_NUMBER

block = [
    'Question 1. En quelle annee ?',
    '- A) 1926',
    '- B) 1936',
]

print("Block:", block)
print()

for line in block:
    m_q = RE_QUESTION_START.match(line) or RE_QUESTION_NUMBER.match(line)
    m_opt = RE_OPTION.match(line)
    m_rep = RE_REPONSE.search(line)
    print(f"line: {line!r}")
    print(f"  question match: {m_q.groups() if m_q else None}")
    print(f"  option match: {m_opt.groups() if m_opt else None}")
    print(f"  reponse match: {m_rep.groups() if m_rep else None}")
    print()

result = _parse_block(block)
print(f"Result: {result}")
