# Agent Memory & Learner Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire de l'agent un tuteur qui ne perd jamais le fil de la session, se souvient de ce qu'il a fait, connaît le niveau de l'apprenant par compétence, et adapte dynamiquement ses méthodes et son calendrier de révision.

**Architecture:** Hybride — on garde le graphe LangGraph principal (1 agent) et on y ajoute : (1) un nœud `context_builder` qui injecte le Learner Model + résumé de session avant chaque décision, (2) un sous-agent mémoire (`session_memory`) invoqué tous les 3 tours pour compacter la session, (3) un Learner Model enrichi en SQLite (compétences dynamiques, score par session, efficacité des méthodes), (4) un `revision_planner` + page `/revision`. La mémoire court terme utilise le checkpointer LangGraph ; la mémoire long terme utilise la DB SQLite.

**Tech Stack:** Python 3.12, FastAPI, LangGraph 1.2 (checkpointer SqliteSaver, interrupt, subgraph), SQLite, Next.js 14, Ollama (local + cloud).

---

## Scope Check

Le spec couvre 6 sous-systèmes, mais ils sont **fortement interdépendants** (tout repose sur la mémoire de session). Plutôt que 6 plans séparés, on fait **un plan en 6 phases ordonnées**, chaque phase produisant un logiciel testable indépendamment :

| Phase | Sous-système | Produit testable |
|---|---|---|
| 1 | Mémoire de session (fondation) | L'agent ne perd plus le fil |
| 2 | Learner Model enrichi (DB) | Base de connaissance utilisateur |
| 3 | Compétences dynamiques | Création validée par l'utilisateur |
| 4 | Sous-agent mémoire | Résumé de session tous les 3 tours |
| 5 | Method evaluator | Méthode s'adapte (inférence implicite) |
| 6 | Revision planner + page /revision | Calendrier par compétence |

**Dépendances :** 1 → 2 → {3, 4, 5} → 6. La Phase 1 est bloquante pour tout le reste.

---

## 🌐 Recherches web — état de l'art (sources réelles, 2026-08-26)

Recherches via le plugin DuckDuckGo (3 lots, ~25 sources). Synthèse par thème et impact sur le plan.

### A. Architectures des leaders de l'edtech

| Source | Découverte clé | Impact sur le plan |
|---|---|---|
| [Khan Academy — Khanmigo](https://blog.khanacademy.org/how-khan-academy-is-building-a-better-ai-tutor-our-most-recent-learnings/) | Leur problème n°1 : injecter le contexte de performance de l'élève à chaque prompt. Amélioré via « smarter data use » | Valide `context_builder` ; on l'injecte dans **chaque prompt**, pas juste au routage |
| [Duolingo — Birdbrain](https://blog.duolingo.com/learning-how-to-help-you-learn-introducing-birdbrain/) + [ML pipelines](https://www.techaheadcorp.com/blog/how-duolingo-personalizes-learning/) | **Deep knowledge tracing** + **bandit pipelines** (multi-armed bandits) pour la personnalisation à 50M+ utilisateurs | Phase 5 : la sélection de méthode peut évoluer vers un **bandit** (ε-greedy) plutôt qu'une simple efficacité |
| [Squirrel AI](https://squirrelai.com/) | Découpage des connaissances au **nano-level** (centaines → dizaines de milliers de knowledge points) | Phase 3 : prévoir une granularité de compétence extensible (parent/enfant) sans tout créer d'avance |
| [Carnegie Learning — MATHia](https://www.carnegielearning.com/blog/mathia-ai) | ML qui étudie **comment** les élèves interagissent et pensent ; mise à jour continue du learner model | Phase 5 : mettre à jour la maîtrise **après chaque interaction**, pas seulement après les quiz |

### B. Mémoire d'agent (le cœur du sujet)

| Source | Découverte clé | Impact sur le plan |
|---|---|---|
| [LangMem (GitHub)](https://github.com/langchain-ai/langmem) | SDK officiel LangGraph : extrait l'info importante, affine les prompts, mémoire long terme. Intégration native au storage LangGraph | **Phase 4 : utiliser LangMem** (confirmé installable, v0.0.30) |
| [LangMem — episodic memories](https://langchain-ai.github.io/langmem/guides/extract_episodic_memories/) | **Semantic** = « what » (faits), **episodic** = « how » (chaîne de raisonnement qui a mené au succès) | Phase 4 : stocker les deux — faits pédagogiques (semantic) + épisodes réussis (episodic) |
| [OpenAI Cookbook — session memory](https://developers.openai.com/cookbook/examples/agents_sdk/session_memory) | « Le contexte utile est **local** : les steps récents comptent bien plus que l'historique lointain ». Résumer en summaries structurées réinjectées | Phase 1/4 : préserver le **tail** (derniers tours) intact, résumer le **head** |
| [Context compression (Medium)](https://medium.com/the-ai-forum/automatic-context-compression-in-llm-agents-why-agents-need-to-forget-and-how-to-help-them-do-it-43bff14c341d) | « Résumer le head via un 2e appel LLM, préserver le tail (~10% les plus récents), archiver les originaux » | Phase 4 : stratégie de compression head/tail précise |
| [ChatGPT memory (mem0)](https://x.com/mem0ai/article/2071990201531118063) | Deux systèmes de mémoire + mécanisme d'injection ; un moteur background consolide la mémoire | Valide l'architecture 2 couches (checkpointer + Learner Model) |

### C. Répétition espacée

| Source | Découverte clé | Impact sur le plan |
|---|---|---|
| [SM-2 vs FSRS vs Leitner](https://smartrecallai.com/blog/sm2-vs-fsrs-vs-leitner-vs-anki-2026) + [Penluma](https://penluma.com/blog/ai-learning-platform/21-spaced-repetition-algorithms-in-practice-sm-2-fsrs) | **FSRS** est plus précis que SM-2/Leitner (modélise la stabilité + difficulté par carte) | Phase 6 : Leitner déjà en place (simple) ; **FSRS = amélioration future** documentée |

### D. Multi-agent pour l'éducation

| Source | Découverte clé | Impact sur le plan |
|---|---|---|
| [AceSAT (GitHub)](https://github.com/atifanawaz/acesat-multiagent) | Stack hiérarchique **Planner→Orchestrator→Specialist** + **Bayesian Knowledge Tracing** + routage par prérequis (FastAPI) | Référence concrète si on évolue vers plus de spécialisation. Notre approche hybride (agent + sous-agent mémoire) reste le bon dosage actuel |
| [LLM Agent Classrooms](https://www.emergentmind.com/topics/classroom-of-llm-agents) | Agents spécialisés par rôle qui coordonnent l'apprentissage | Idem : évolution future, pas le point de départ |

### E. Knowledge tracing & adaptation pédagogique

| Source | Découverte clé | Impact sur le plan |
|---|---|---|
| [Deep Knowledge Tracing (arXiv)](https://arxiv.org/html/2504.20070v1) + [emergentmind](https://www.emergentmind.com/topics/deep-knowledge-tracing-dkt) | DKT = RNN qui prédit la performance future depuis l'historique d'interactions | Valide `session_competency_score` ; trop lourd pour nous, mais le **principe** (prédire depuis l'historique) guide `method_evaluator` |
| [KT + formative assessment (Springer)](https://link.springer.com/article/10.1007/s40747-025-02149-4) | Suivi dynamique de l'état de connaissance pour adapter l'expérience | Valide l'évaluation continue |
| [Scaffolding — 6 principes (ResearchGate)](https://www.researchgate.net/publication/327833000_Scaffolding_learning_Principles_for_effective_teaching_and_the_design_of_classroom_resources) | 6 principes : activation des connaissances préalables, collaboration, problème, **évaluation formative**, scaffolding, métacognition | Nos 8 méthodes couvrent déjà scaffolding + évaluation formative ; la **métacognition** est un ajout possible |
| [Adaptive learning — revue systématique (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S1041608025001578) | L'adaptation repose surtout sur les **trace data** ; micro-niveau : navigation, support, progression de difficulté | Valide l'inférence implicite (trace data) ; la progression de difficulté guide le choix de méthode |

### Synthèse des décisions

1. **LangMem confirmé** pour la Phase 4 (v0.0.30 installable) — mémoire semantic + episodic.
2. **Compression head/tail** : préserver les derniers tours intacts, résumer le head (OpenAI + Medium).
3. **Mise à jour continue** de la maîtrise après chaque interaction (Carnegie Learning).
4. **Bandit (ε-greedy)** pour la sélection de méthode = évolution de la Phase 5 (Duolingo), pas dès le départ.
5. **FSRS** documenté comme amélioration future du `revision_planner` (Leitner reste pour l'instant).
6. **Granularité de compétence extensible** parent/enfant (Squirrel AI), sans tout créer d'avance.
7. **L'architecture hybride est validée** : AceSAT montre qu'un multi-agent hiérarchique est possible, mais c'est une évolution, pas le point de départ.

### 🛠️ Modifications concrètes apportées aux phases

| Phase | Avant | Après recherches |
|---|---|---|
| **1** | Remplir `chat_history` | + **stratégie head/tail** : garder les N derniers tours intacts, le reste éligible au résumé |
| **2** | Tables mémoire | + colonne `p_success` (probabilité de réussite estimée, inspiration Birdbrain) ; granularité compétence **parent/enfant** (Squirrel AI) |
| **3** | Création validée | + vérification de similarité pour éviter les doublons + rattachement à un parent |
| **4** | Code maison | + **LangMem** (semantic + episodic) ; compression **head/tail** (préserver ~10% récents) |
| **5** | Efficacité simple | + mise à jour de la maîtrise **après chaque interaction** (Carnegie) ; hook **ε-greedy bandit** préparé (Duolingo) |
| **6** | Leitner | + **FSRS documenté** comme upgrade futur ; calendrier par compétence inchangé |

### F. Création d'agents & patterns d'architecture LangGraph (doc officielle)

Sources : [LangGraph](https://www.langchain.com/langgraph), [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers), [Multi-Agent Patterns](https://deepwiki.com/langchain-ai/langgraph-101/6-multi-agent-patterns), [create_react_agent vs custom](https://medium.com/@dharamai2024/langgraph-agents-with-multiple-tools-prebuilt-custom-approaches-b6208c5beb0f), [Agent Memory with Checkpointers](https://deepwiki.com/langchain-ai/langchain-academy/4.2-agent-memory-with-checkpointers).

| Concept LangGraph | Ce que dit la doc | Notre situation / décision |
|---|---|---|
| **Prebuilt (`create_react_agent`) vs custom `StateGraph`** | Le prebuilt est un scaffold ReAct rapide ; le custom `StateGraph` donne le contrôle total du flux | On **garde notre `StateGraph` custom** : notre flux pédagogique (router→diagnostic→method→…) n'est pas un simple ReAct. Bon choix confirmé. |
| **Checkpointer** | « Sauvegarde un snapshot de l'état à chaque super-step, organisé en threads. Active HITL, time-travel, exécution fault-tolerant et **mémoire conversationnelle** » | **Phase 1** : c'est exactement notre fondation mémoire. Déjà partiellement actif, à renforcer. |
| **Single vs multi-agent vs hiérarchique** | LangGraph supporte les trois avec les mêmes primitives | Notre **architecture hybride** (agent unique + sous-agent mémoire) = le bon niveau. Le hiérarchique/multi-agent est une évolution future (cf. AceSAT). |
| **Supervisor vs Swarm** | Supervisor = orchestration centralisée ; Swarm = coordination distribuée | Si on passe multi-agent plus tard, le **supervisor** est le plus adapté à un tuteur (contrôle central du parcours pédagogique). |
| **Communication multi-agent** | Message passing + schémas d'état partagés + intégration mémoire | Non nécessaire pour l'instant (un seul agent principal). |

**Conclusion architecture** : la doc LangGraph confirme que notre `StateGraph` custom + checkpointer + sous-agent mémoire est l'approche idiomatique. Pas besoin de `create_react_agent` ni de multi-agent pour l'instant. Le MCP `langchain-docs` (branché) permettra de vérifier les API précises (LangMem, checkpointer, store) pendant l'implémentation.

---

## File Structure

### Backend — nouveaux fichiers
| Fichier | Responsabilité |
|---|---|
| `apps/api/agent/memory/learner_model.py` | CRUD du Learner Model (compétences, scores par session, efficacité méthodes, topics) |
| `apps/api/agent/memory/session_memory.py` | Sous-agent mémoire : extrait faits pédagogiques + compacte la conversation |
| `apps/api/agent/memory/context_builder.py` | Construit le contexte injecté dans l'état (Learner Model + résumé session) |
| `apps/api/agent/nodes_context.py` | Nœuds `context_builder`, `method_evaluator`, `revision_planner` |
| `apps/api/db/schema_memory.sql` | Schéma des nouvelles tables mémoire |
| `apps/api/routes/revision.py` | Endpoints `/api/revision/calendar` |
| `tests/conftest.py` | Fixtures pytest (DB temporaire, model_manager mock) |
| `tests/test_learner_model.py` | Tests du Learner Model |
| `tests/test_context_builder.py` | Tests du context_builder |
| `tests/test_session_memory.py` | Tests du sous-agent mémoire |

### Backend — fichiers modifiés
| Fichier | Changement |
|---|---|
| `apps/api/agent/state.py` | Ajout champs : `session_summary`, `learner_context`, `turn_count`, `proposed_competency` |
| `apps/api/agent/graph.py` | Insertion `context_builder` en entrée, `method_evaluator` + `session_memory` en sortie, checkpointer activé |
| `apps/api/agent/nodes.py` | `router_profil_node` utilise le contexte injecté |
| `apps/api/db/migrations.py` | Application de `schema_memory.sql` |
| `apps/api/main.py` | Enregistrement du router `revision` |

### Frontend — nouveaux fichiers
| Fichier | Responsabilité |
|---|---|
| `apps/web/app/revision/page.tsx` | Page calendrier de révision |
| `apps/web/components/revision/RevisionCalendar.tsx` | Composant calendrier par compétence |

### Frontend — fichiers modifiés
| Fichier | Changement |
|---|---|
| `apps/web/lib/api.ts` | Ajout `revision.getCalendar()` |
| `apps/web/lib/types.ts` | Types `RevisionCalendar`, `CompetencySchedule` |

---

## PHASE 1 — Mémoire de session (fondation)

> **Objectif :** l'agent se souvient de la conversation dans la session en cours. C'est LA fondation — rien d'autre ne tient sans elle.

### Task 1.1 : Infrastructure de test

**Files:**
- Create: `tests/conftest.py`, `tests/__init__.py`
- Modify: `apps/api/requirements.txt`

- [ ] **Step 1 : Ajouter pytest aux dépendances**

Dans `apps/api/requirements.txt`, ajouter :
```
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

- [ ] **Step 2 : Installer**

Run: `.\venv\Scripts\python.exe -m pip install pytest pytest-asyncio`
Expected: `Successfully installed pytest-...`

- [ ] **Step 3 : Créer `tests/conftest.py`** (DB temporaire + mock)

```python
import sqlite3, tempfile
from pathlib import Path
import pytest
from apps.api.db import migrations

@pytest.fixture
def tmp_db():
    """DB SQLite temporaire avec schéma complet."""
    path = Path(tempfile.mkdtemp()) / "test.db"
    conn = sqlite3.connect(str(path))
    schema = Path("apps/api/db/schema_v3.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit(); conn.close()
    migrations.run_migrations(path)
    yield path

@pytest.fixture
def mock_retriever():
    class _R:
        def invoke(self, q): return []
    return _R()
```

- [ ] **Step 4 : Vérifier que pytest tourne**

Run: `.\venv\Scripts\python.exe -m pytest tests/ -v`
Expected: `no tests ran` (aucun test encore, mais pas d'erreur d'import)

- [ ] **Step 5 : Commit**
```
git add tests/ apps/api/requirements.txt
git commit -m "test: add pytest infrastructure"
```

### Task 1.2 : Activer le checkpointer + remplir chat_history

**Files:**
- Modify: `apps/api/agent/graph.py` (force checkpointer même en mode Studio)
- Modify: `apps/api/agent/nodes.py` (`router_profil_node` ajoute le message à `chat_history`)

- [ ] **Step 1 : Écrire le test qui échoue** — `tests/test_memory.py`

```python
def test_chat_history_persists_across_turns(tmp_db, mock_retriever):
    from apps.api.services.model_manager import ModelManager
    from apps.api.agent.graph import build_agent_graph
    g = build_agent_graph(mock_retriever, ModelManager(force_local=True),
                          db_path=str(tmp_db), with_checkpointer=True)
    cfg = {"configurable": {"thread_id": "t1"}}
    g.invoke({"question": "Bonjour", "chat_history": []}, config=cfg)
    state = g.get_state(cfg).values
    assert len(state.get("chat_history", [])) >= 1, "chat_history doit être rempli"
```

- [ ] **Step 2 : Lancer le test, vérifier qu'il échoue**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_memory.py -v`
Expected: FAIL (`chat_history` vide)

- [ ] **Step 3 : Implémenter** — dans `router_profil_node`, ajouter au retour :
```python
from langchain_core.messages import HumanMessage
# ... dans le return du router :
"chat_history": state.get("chat_history", []) + [HumanMessage(content=question)],
```
Et dans `generate_node`, ajouter l'`AIMessage` de réponse à `chat_history`.

- [ ] **Step 4 : Relancer le test, vérifier qu'il passe**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_memory.py -v`
Expected: PASS

- [ ] **Step 5 : Commit**
```
git commit -am "feat(memory): fill chat_history + enable checkpointer"
```

### Task 1.3 : Le graphe Studio utilise le checkpointer

**Files:**
- Modify: `apps/api/agent/studio_graph.py` (`with_checkpointer=True`)

- [ ] **Step 1 : Changer `with_checkpointer=False` → `True`** dans `studio_graph.py`
- [ ] **Step 2 : Vérifier la construction**
Run: `.\venv\Scripts\python.exe -c "import apps.api.agent.studio_graph as s; print('OK', len(s.graph.get_graph().nodes))"`
Expected: `OK 11`
- [ ] **Step 3 : Commit**
```
git commit -am "feat(memory): enable checkpointer in Studio mode"
```

---

## PHASE 2 — Learner Model enrichi (base de connaissance utilisateur)

> **Objectif :** une base de connaissance par utilisateur : niveau par compétence, score par session, sujets habituels.

### Task 2.1 : Schéma des tables mémoire

**Files:**
- Create: `apps/api/db/schema_memory.sql`
- Modify: `apps/api/db/migrations.py`

- [ ] **Step 1 : Créer `schema_memory.sql`**

```sql
-- Score par compétence ET par session (pas juste global)
CREATE TABLE IF NOT EXISTS session_competency_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    session_id INTEGER REFERENCES session(id) ON DELETE CASCADE,
    competency_id INTEGER NOT NULL REFERENCES competency(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0.0,
    updated_at DATETIME DEFAULT (datetime('now')),
    UNIQUE(session_id, competency_id)
);

-- Efficacité des méthodes par compétence (inférence implicite)
CREATE TABLE IF NOT EXISTS method_effectiveness (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    competency_id INTEGER REFERENCES competency(id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    uses INTEGER DEFAULT 1,
    successes INTEGER DEFAULT 0,
    effectiveness REAL DEFAULT 0.0,
    updated_at DATETIME DEFAULT (datetime('now')),
    UNIQUE(competency_id, method)
);

-- Sujets habituels de l'utilisateur
CREATE TABLE IF NOT EXISTS user_topic_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    topic TEXT NOT NULL,
    mentions INTEGER DEFAULT 1,
    last_mentioned DATETIME DEFAULT (datetime('now')),
    UNIQUE(user_id, topic)
);

-- Résumé compacté de session (faits pédagogiques + résumé textuel)
CREATE TABLE IF NOT EXISTS session_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES session(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    pedagogical_facts TEXT DEFAULT '{}',
    text_summary TEXT DEFAULT '',
    turn_count INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT (datetime('now')),
    UNIQUE(session_id)
);

-- Compétence proposée en attente de validation utilisateur
CREATE TABLE IF NOT EXISTS pending_competency (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default_user',
    proposed_name TEXT NOT NULL,
    proposed_domain TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_scs_session ON session_competency_score(session_id);
CREATE INDEX IF NOT EXISTS idx_scs_competency ON session_competency_score(competency_id);
CREATE INDEX IF NOT EXISTS idx_me_competency ON method_effectiveness(competency_id);
CREATE INDEX IF NOT EXISTS idx_uth_user ON user_topic_history(user_id);
CREATE INDEX IF NOT EXISTS idx_ss_session ON session_summary(session_id);
```

- [ ] **Step 2 : Intégrer dans `migrations.py`** — lire `schema_memory.sql` et l'exécuter dans `run_migrations` (idempotent via `IF NOT EXISTS`).
- [ ] **Step 3 : Tester la migration**
Run: `.\venv\Scripts\python.exe -c "from apps.api.db import migrations; print(migrations.run_migrations())"`
Expected: dict avec les tables créées, pas d'erreur
- [ ] **Step 4 : Commit**
```
git commit -am "feat(db): add learner model schema"
```

### Task 2.2 : CRUD du Learner Model

**Files:**
- Create: `apps/api/agent/memory/learner_model.py`, `apps/api/agent/memory/__init__.py`
- Test: `tests/test_learner_model.py`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
def test_update_session_score(tmp_db):
    from apps.api.agent.memory import learner_model as lm
    # crée une compétence d'abord
    import sqlite3
    c = sqlite3.connect(str(tmp_db))
    c.execute("INSERT INTO competency (id, domain, nom) VALUES (1,'Python','variables')")
    c.execute("INSERT INTO session (id, user_id) VALUES (1,'default_user')")
    c.commit(); c.close()
    lm.update_session_score(1, 1, 0.8, db_path=tmp_db)
    assert lm.get_session_score(1, 1, db_path=tmp_db) == 0.8

def test_record_method_effectiveness(tmp_db):
    from apps.api.agent.memory import learner_model as lm
    import sqlite3
    c = sqlite3.connect(str(tmp_db))
    c.execute("INSERT INTO competency (id, domain, nom) VALUES (1,'Python','variables')")
    c.commit(); c.close()
    lm.record_method_outcome(1, "scaffold", success=True, db_path=tmp_db)
    lm.record_method_outcome(1, "scaffold", success=False, db_path=tmp_db)
    eff = lm.get_method_effectiveness(1, db_path=tmp_db)
    assert eff["scaffold"]["uses"] == 2
    assert eff["scaffold"]["successes"] == 1
```

- [ ] **Step 2 : Lancer, vérifier l'échec**
Run: `.\venv\Scripts\python.exe -m pytest tests/test_learner_model.py -v`
Expected: FAIL (module introuvable)

- [ ] **Step 3 : Implémenter `learner_model.py`** — fonctions :
  - `update_session_score(session_id, competency_id, score, db_path)`
  - `get_session_score(session_id, competency_id, db_path)`
  - `record_method_outcome(competency_id, method, success, db_path)`
  - `get_method_effectiveness(competency_id, db_path)`
  - `bump_topic(user_id, topic, db_path)`
  - `get_top_topics(user_id, limit, db_path)`
  - `get_learner_context(user_id, session_id, db_path)` → dict agrégé (niveau par compétence, meilleurs méthodes, topics, résumé session)

- [ ] **Step 4 : Relancer, vérifier que ça passe**
Run: `.\venv\Scripts\python.exe -m pytest tests/test_learner_model.py -v`
Expected: PASS

- [ ] **Step 5 : Commit**
```
git commit -am "feat(memory): learner model CRUD"
```

---

## PHASE 3 — Compétences dynamiques (création validée)

> **Objectif :** quand l'utilisateur aborde un sujet inconnu, l'agent propose une nouvelle compétence et attend sa validation.

### Task 3.1 : Détection + proposition de compétence

**Files:**
- Modify: `apps/api/agent/nodes_context.py` (nouveau nœud `competency_proposer`)
- Modify: `apps/api/agent/graph.py` (branchement)
- Test: `tests/test_competency.py`

- [ ] **Step 1 : Test qui échoue** — vérifier qu'une question sur un sujet inconnu propose une compétence.
- [ ] **Step 2 : Lancer, vérifier l'échec.**
- [ ] **Step 3 : Implémenter `competency_proposer`** :
  - Si `_detect_active_competency` retourne None ET le domaine est défini → le LLM propose un nom de compétence.
  - Stocke dans `pending_competency` (table) + `proposed_competency` (état).
  - Utilise `interrupt()` pour demander validation à l'utilisateur.
  - Si validé → `crud.create_competency(...)` ; sinon → on continue sans créer.
- [ ] **Step 4 : Relancer, vérifier que ça passe.**
- [ ] **Step 5 : Commit**
```
git commit -am "feat(competency): dynamic competency creation with user validation"
```

---

## PHASE 4 — Sous-agent mémoire (session_memory)

> **Objectif :** tous les 3 tours, un sous-agent compacte la session (faits pédagogiques + résumé textuel) et met à jour le Learner Model.
>
> **LangMem confirmé** (v0.0.30 installable) : utiliser ses primitives pour les deux types de mémoire retenus —
> - **semantic** (« what ») : les faits pédagogiques (niveau, compétences abordées, erreurs, réussites).
> - **episodic** (« how ») : les épisodes réussis (la chaîne qui a mené à une bonne réponse), pour reproduire ce qui marche.
>
> **Compression head/tail** (OpenAI Cookbook + Medium) : le contexte utile est local. À chaque compaction, **préserver intacts les ~10% de tours les plus récents** (le tail), **résumer le head** via un appel LLM, et archiver le résumé dans `session_summary`. Ne jamais résumer le tail.

### Task 4.1 : Le sous-agent session_memory

**Files:**
- Create: `apps/api/agent/memory/session_memory.py`
- Test: `tests/test_session_memory.py`

- [ ] **Step 1 : Test qui échoue** — vérifier que `extract_pedagogical_facts` retourne un dict structuré.
- [ ] **Step 2 : Lancer, vérifier l'échec.**
- [ ] **Step 3 : Implémenter** :
  - `SESSION_MEMORY_PROMPT` : demande au LLM d'extraire `{competences_abordees, erreurs, reussites, niveau_estime}` + un résumé textuel court.
  - `session_memory_subgraph` : un petit graphe (ou fonction) invoqué tous les 3 tours.
  - Écrit dans `session_summary` (upsert).
- [ ] **Step 4 : Relancer, vérifier que ça passe.**
- [ ] **Step 5 : Commit**
```
git commit -am "feat(memory): session memory subagent (facts + summary)"
```

### Task 4.2 : Intégration au graphe principal (tous les 3 tours)

**Files:**
- Modify: `apps/api/agent/state.py` (ajout `turn_count`, `session_summary`, `learner_context`)
- Modify: `apps/api/agent/graph.py` (nœud `session_memory` conditionnel en fin de tour)

- [ ] **Step 1 : Ajouter les champs d'état** + défauts dans `STATE_DEFAULTS`.
- [ ] **Step 2 : Ajouter le nœud `session_memory`** au graphe, avec un routage conditionnel : `if turn_count % 3 == 0 → session_memory → END, sinon → END`.
- [ ] **Step 3 : Vérifier la construction du graphe.**
Run: `.\venv\Scripts\python.exe -c "import apps.api.agent.studio_graph as s; print(len(s.graph.get_graph().nodes))"`
Expected: nombre de nœuds augmenté
- [ ] **Step 4 : Commit**
```
git commit -am "feat(memory): wire session_memory every 3 turns"
```

### Task 4.3 : context_builder injecte le Learner Model

**Files:**
- Create: `apps/api/agent/memory/context_builder.py`
- Modify: `apps/api/agent/graph.py` (nœud `context_builder` en entrée, avant router)
- Test: `tests/test_context_builder.py`

- [ ] **Step 1 : Test qui échoue** — `build_context` retourne un dict avec niveau/compétences/résumé.
- [ ] **Step 2 : Lancer, vérifier l'échec.**
- [ ] **Step 3 : Implémenter `context_builder`** : appelle `learner_model.get_learner_context(...)` + charge `session_summary`, retourne `learner_context` dans l'état.
- [ ] **Step 4 : Câbler dans le graphe** : `START → context_builder → router`.
- [ ] **Step 5 : Relancer les tests, vérifier.**
- [ ] **Step 6 : Commit**
```
git commit -am "feat(memory): context_builder injects learner model"
```

---

## PHASE 5 — Method evaluator (inférence implicite)

> **Objectif :** après chaque quiz/Feynman, déduire si la méthode a aidé et mettre à jour `method_effectiveness`. La sélection de méthode privilégie alors les méthodes efficaces.
>
> **Améliorations issues des recherches :**
> - **Mise à jour continue** (Carnegie Learning / MATHia) : la maîtrise est mise à jour **après chaque interaction**, pas seulement après les quiz. Le `method_evaluator` exploite toutes les traces (réponses, hésitations, scores).
> - **Hook bandit ε-greedy** (Duolingo / Birdbrain) : la sélection de méthode prépare un crochet ε-greedy — avec probabilité ε on explore une méthode moins utilisée, sinon on exploite la meilleure `effectiveness`. Désactivé par défaut (ε=0), activable plus tard.

### Task 5.1 : method_evaluator

**Files:**
- Create: `apps/api/agent/nodes_context.py` (nœud `method_evaluator`)
- Modify: `apps/api/agent/graph.py` (insertion après `evaluate`)
- Modify: `apps/api/agent/nodes.py` (`method_selection_node` consulte `method_effectiveness`)

- [ ] **Step 1 : Test qui échoue** — après un quiz réussi, `method_effectiveness` est mis à jour.
- [ ] **Step 2 : Lancer, vérifier l'échec.**
- [ ] **Step 3 : Implémenter `method_evaluator`** : lit `evaluation_score`/`feynman_score` + la méthode utilisée, appelle `learner_model.record_method_outcome(...)`.
- [ ] **Step 4 : Adapter `method_selection_node`** : à maîtrise égale, choisir la méthode avec la meilleure `effectiveness` pour la compétence active.
- [ ] **Step 5 : Relancer les tests, vérifier.**
- [ ] **Step 6 : Commit**
```
git commit -am "feat(method): implicit method effectiveness evaluation"
```

---

## PHASE 6 — Revision planner + page /revision

> **Objectif :** un calendrier de révision par compétence, mis à jour à chaque progression, affiché sur une page dédiée.

### Task 6.1 : revision_planner (backend)

**Files:**
- Create: `apps/api/routes/revision.py`
- Modify: `apps/api/main.py` (enregistrement du router)
- Modify: `apps/api/agent/tools/progress.py` (`get_revision_plan` enrichi par compétence)

- [ ] **Step 1 : Test qui échoue** — `/api/revision/calendar` retourne un calendrier par compétence.
- [ ] **Step 2 : Lancer, vérifier l'échec.**
- [ ] **Step 3 : Implémenter l'endpoint** : lit `mastery.next_review_at` groupé par compétence, retourne `{competency, items:[{due, box, priority}]}`.
- [ ] **Step 4 : Enregistrer le router dans `main.py`.**
- [ ] **Step 5 : Relancer les tests, vérifier.**
- [ ] **Step 6 : Commit**
```
git commit -am "feat(revision): per-competency revision calendar endpoint"
```

### Task 6.2 : Page /revision (frontend)

**Files:**
- Create: `apps/web/app/revision/page.tsx`, `apps/web/components/revision/RevisionCalendar.tsx`
- Modify: `apps/web/lib/api.ts`, `apps/web/lib/types.ts`

- [ ] **Step 1 : Ajouter les types** `RevisionCalendar`, `CompetencySchedule` dans `types.ts`.
- [ ] **Step 2 : Ajouter `revision.getCalendar()`** dans `api.ts`.
- [ ] **Step 3 : Créer `RevisionCalendar.tsx`** : liste des compétences avec leurs révisions dues (badge priorité, date, boîte Leitner).
- [ ] **Step 4 : Créer `app/revision/page.tsx`** qui fetch et affiche le calendrier.
- [ ] **Step 5 : Vérifier le build**
Run: `cmd.exe /c "cd apps\web && npx next build"` (ou vérifier en dev)
Expected: pas d'erreur TS bloquante
- [ ] **Step 6 : Commit**
```
git commit -am "feat(revision): /revision calendar page"
```

---

## Validation finale

- [ ] Lancer toute la suite : `.\venv\Scripts\python.exe -m pytest tests/ -v` → tous les tests passent.
- [ ] Vérifier la construction du graphe : `import apps.api.agent.studio_graph`.
- [ ] Scénario bout en bout dans Studio :
  1. « Bonjour » → diagnostic (base vide).
  2. Répondre aux 3 questions → niveau estimé, Learner Model rempli.
  3. Poser 3-4 questions → vérifier que `chat_history` grossit et que l'agent se souvient.
  4. Au 3e tour → `session_memory` compacte la session.
  5. Demander un quiz → `method_evaluator` met à jour l'efficacité.
  6. Ouvrir `/revision` → calendrier affiché.

---

## Risques & hypothèses

- **Disque C: presque plein** : libérer de l'espace avant les tests (le checkpointer SQLite écrit).
- **Quota cloud** : les tests utilisent `force_local=True`. Le mode Studio cloud consomme du quota.
- **Latence** : le sous-agent mémoire ajoute 1 appel LLM tous les 3 tours. Acceptable car pas à chaque tour.
- **Compétences dynamiques** : la validation utilisateur évite les doublons, mais il faut une vérification de similarité (nom proche) pour ne pas recréer une compétence existante.
- **Pas de migration destructive** : toutes les nouvelles tables sont en `IF NOT EXISTS`, aucune donnée existante n'est touchée.
