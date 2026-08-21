# Mémoire du Projet — Agent d'Apprentissage

## Bugs corrigés (2026-08-20)

- [Bug #1: active_competency jamais défini] → fix: ajouté `_detect_active_competency()` dans `graph/nodes.py` (keyword matching score-based, pas de LLM)
- [Bug #2: boucles quiz/Feynman jamais fermées] → fix: ajouté `answer_processing_node()` avant `method_selection_node`, parsing des réponses quiz, capture explication Feynman
- [Bug #2b: graph.py sans answer_processing] → fix: ajouté le nœud `answer_processing` entre `router` et `retrieve`/`method`, nouveau routing conditionnel
- [Bug #3: sessions partagent le même thread_id] → fix: `_create_new_session()` avec `uuid.uuid4().hex[:8]`, récupération du thread_id depuis la DB dans le chat input
- [Bug #4: Leitner calendar incohérent] → fix: unifié `LEITNER_INTERVALS` comme source unique, passé `next_review_at` depuis `progress.py` vers `db.upsert_mastery()`

## Fichiers modifiés

- `graph/state.py` — ajouté `awaiting_feynman_explanation`, `rag_needed`, `pending_confirmation`, `user_confirmed`
- `graph/nodes.py` — ajouté `_detect_active_competency()`, `answer_processing_node()`, mis à jour `method_selection_node()`
- `graph/graph.py` — ajouté nœud `answer_processing`, nouveau routing conditionnel
- `app.py` — ajouté `uuid` import, `_create_new_session()`, fix session creation en 3 endroits
- `db/db.py` — ajouté paramètre `next_review_at` à `upsert_mastery()`
- `tools/progress.py` — passé `next_review_at` aux appels `upsert_mastery()`

## Plan de refactor V2

Sauvegardé dans `docs/superpowers/plans/2026-08-20-refactor-v2.md`

6 sous-projets :
1. RAG conditionnel + Node activation
2. Human-in-the-loop
3. Web Search Tool (DuckDuckGo)
4. Revision Planner
5. Interface Interactive HTML/CSS/JS
6. Cloud Models (OpenAI, Anthropic)
