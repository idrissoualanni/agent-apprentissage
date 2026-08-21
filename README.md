# Agent d'Apprentissage

Agent pédagogique basé sur LangGraph + Ollama + ChromaDB. Interface Streamlit avec sessions, quiz interactif HTML, méthode Feynman, répétition espacée (Leitner), recherche web, planificateur de révision, et human-in-the-loop.

## Architecture

```
app.py                    → Interface Streamlit (5 pages + renderers HTML)
config.py                 → Configuration centralisée (.env)
├── db/
│   ├── schema.sql        → Schéma SQLite (9 tables)
│   └── db.py             → Couche d'accès SQLite
├── graph/
│   ├── state.py          → TypedDict AgentState (LangGraph)
│   ├── nodes.py          → 9 nœuds (router, answer_processing, diagnostic,
│   │                       retrieve, method, confirmation, generate, tool, evaluate)
│   └── graph.py          → Construction StateGraph + SqliteSaver
├── llm/
│   └── cloud_providers.py → Factory get_llm() — Ollama local ou distant
├── rag/
│   ├── ingestion.py      → Chargement PDF + chunking hiérarchique
│   └── retriever.py      → ChromaDB persistant (create/load/add)
├── tools/
│   ├── quiz.py           → Génération quiz JSON via Ollama
│   ├── feynman.py        → Évaluation restitution Feynman
│   ├── progress.py       → Système Leitner + plan de révision
│   ├── artifact.py       → Génération artefacts pédagogiques
│   └── web_search.py     → Recherche web DuckDuckGo
├── ui/
│   └── renderers.py      → Templates HTML interactifs (quiz, feynman, artefacts)
└── data/
    ├── documents/        → PDFs uploadés
    └── chroma/           → ChromaDB persistant
```

## Fonctionnement

### Pipeline RAG conditionnel

1. **Upload PDF** → `rag/ingestion.py` chunk le document en segments
2. **Indexation** → Segments ajoutés à ChromaDB via `rag/retriever.py`
3. **Question** → Router charge le profil, détecte questions méta vs pédagogiques
4. **RAG conditionnel** → Skip retrieval pour salutations/ack, retrieval pour questions pédagogiques
5. **Méthode** → Choix pédagogique selon le niveau + type de question
6. **Human-in-the-loop** → Confirmation avant quiz/Feynman/artefact
7. **Génération** → Ollama génère la réponse avec le prompt adapté
8. **Évaluation** → Score Leitner mis à jour en base

### StateGraph LangGraph

```
START → router → answer_processing? → retrieve? → method → confirmation? → tool? → evaluate → generate → END
         └→ diagnostic ──────────────────────────────────────────────────────────────→ generate → END
         └→ method (skip RAG si méta) ─→ confirmation? → tool? → evaluate → generate → END
```

**Nœuds :**
- **router** — Charge le profil, détecte questions méta, définit `rag_needed`
- **answer_processing** — Capture réponses quiz/Feynman en attente
- **diagnostic** — Questions de diagnostic si pas de domaine défini
- **retrieve** — RAG retrieval via ChromaDB (skip si `rag_needed=False`)
- **method** — Choix de la méthode pédagogique + détection web_search/revision
- **confirmation** — Human-in-the-loop avant actions lourdes (quiz/Feynman/artefact)
- **generate** — Génération Ollama avec le prompt adapté
- **tool** — Exécution quiz/feynman/artifact/web_search/revision
- **evaluate** — Mise à jour de la progression en base

### Fonctionnalités V2

| Fonctionnalité | Description |
|---|---|
| **RAG conditionnel** | Détecte salutations/méta → skip retrieval, gain de latence |
| **Human-in-the-loop** | Confirmation UI avant quiz/Feynman/artefact (boutons Oui/Non) |
| **Recherche web** | DuckDuckGo intégré pour questions d'actualité/prix/stats |
| **Planificateur révision** | Vérifie les cartes Leitner en retard, propose un plan |
| **Quiz interactif HTML** | CSS/JS intégré, sélection d'options, score instantané |
| **Cloud models** | Factory `get_llm()` — Ollama local ou distant via `OLLAMA_BASE_URL` |

### Base de données SQLite

| Table | Description |
|---|---|
| `learner_profile` | Profil mono-utilisateur (domaine, niveau) |
| `competency` | Compétences hiérarchiques (auto-référencées) |
| `mastery` | Score + boîte Leitner + date prochaine révision |
| `document` | PDFs uploadés |
| `chunk` | Segments indexés |
| `session` | Sessions de conversation (UUID thread_id) |
| `message` | Messages utilisateur/assistant |
| `quiz_attempt` | Tentatives de quiz |
| `feynman_restitution` | Évaluations Feynman |

### Répétition espacée (Leitner)

6 boîtes (0-5) avec intervalles non-linéaires :
- Box 0 : immédiat
- Box 1 : 1 jour
- Box 2 : 2 jours
- Box 3 : 5 jours
- Box 4 : 10 jours
- Box 5 : 21 jours

Score ≥ 0.7 → promotion | Score < 0.4 → rétrogradation

## Installation

```bash
# Cloner
git clone https://github.com/idrissoualanni/agent-apprentissage.git
cd agent-apprentissage

# Virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Dépendances
pip install -r requirements.txt

# Configuration
cp .env.example .env  # ou éditer .env directement

# Lancer Ollama
ollama serve

# Lancer l'app
streamlit run app.py
```

## Configuration (.env)

```env
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
OLLAMA_NUM_GPU=0
AVAILABLE_MODELS=qwen2.5:1.5b,qwen2.5-coder:3b

# Ollama distant (optionnel)
OLLAMA_BASE_URL=
OLLAMA_API_KEY=

CHUNK_SIZE=1000
CHUNK_OVERLAP=200
TOP_K=3
```

## Modèles Ollama requis

```bash
ollama pull qwen2.5:1.5b           # LLM principal
ollama pull qwen2.5-coder:3b       # Alternative
ollama pull qwen3-embedding:0.6b   # Embeddings
```

## Pages Streamlit

| Page | Description |
|---|---|
| **Chat** | Interface conversationnelle avec tuteur IA + renderers HTML interactifs |
| **Dashboard** | KPIs progression + graphique barres (Plotly) |
| **Import PDF** | Upload + indexation de documents |
| **Profil** | Domaine, niveau, compétences |
| **DB** | Explorateur de tables + checkpoints LangGraph |
