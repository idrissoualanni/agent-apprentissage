# Agent d'Apprentissage

Agent pédagogique basé sur LangGraph + Ollama + ChromaDB. Interface Streamlit avec sessions, quiz, méthode Feynman, répétition espacée (Leitner).

## Architecture

```
app.py                    → Interface Streamlit (5 pages)
config.py                 → Configuration centralisée (.env)
├── db/
│   ├── schema.sql        → Schéma SQLite (9 tables)
│   └── db.py             → Couche d'accès SQLite
├── graph/
│   ├── state.py          → TypedDict AgentState (LangGraph)
│   ├── nodes.py          → 7 nœuds (router, diagnostic, retrieve, method, generate, tool, evaluate)
│   └── graph.py          → Construction StateGraph + SqliteSaver
├── rag/
│   ├── ingestion.py      → Chargement PDF + chunking hiérarchique
│   └── retriever.py      → ChromaDB persistant (create/load/add)
├── tools/
│   ├── quiz.py           → Génération quiz JSON via Ollama
│   ├── feynman.py        → Évaluation restitution Feynman
│   ├── progress.py       → Système Leitner + update mastery
│   └── artifact.py       → Génération artefacts pédagogiques
└── data/
    ├── documents/        → PDFs uploadés
    └── chroma/           → ChromaDB persistant
```

## Fonctionnement

### Pipeline RAG

1. **Upload PDF** → `rag/ingestion.py` chunk le document en segments
2. **Indexation** → Segments ajoutés à ChromaDB via `rag/retriever.py`
3. **Question** → Router charge le profil, décide diagnostic ou retrieval
4. **Retrieval** → ChromaDB récupère les k segments les plus pertinents
5. **Méthode** → Choix pédagogique selon le niveau (scaffold/socratic/quiz/feynman)
6. **Génération** → Ollama génère la réponse avec le prompt adapté
7. **Évaluation** → Score Leitner mis à jour en base

### StateGraph LangGraph

```
START → router → (diagnostic? | retrieve) → method → (tool → evaluate → generate | generate) → END
```

- **router** : charge le profil, décide du premier routing
- **diagnostic** : questions de diagnostic si pas de domaine défini
- **retrieve** : RAG retrieval via ChromaDB
- **method** : choix de la méthode pédagogique
- **generate** : génération Ollama avec le prompt adapté
- **tool** : exécution quiz/feynman/artifact
- **evaluate** : mise à jour de la progression en base

### Base de données SQLite

| Table | Description |
|---|---|
| `learner_profile` | Profil mono-utilisateur (domaine, niveau) |
| `competency` | Compétences hiérarchiques (auto-référencées) |
| `mastery` | Score + boîte Leitner + date prochaine révision |
| `document` | PDFs uploadés |
| `chunk` | Segments indexés |
| `session` | Sessions de conversation |
| `message` | Messages utilisateur/assistant |
| `quiz_attempt` | Tentatives de quiz |
| `feynman_restitution` | Évaluations Feynman |

### Répétition espacée (Leitner)

6 boîtes (0-5) avec intervalles croissants :
- Box 0 : immédiat
- Box 1 : 1 jour
- Box 2 : 3 jours
- Box 3 : 7 jours
- Box 4 : 15 jours
- Box 5 : 45 jours

Score ≥ 0.7 → promotion | Score < 0.4 → rétrogradation

## Installation

```bash
# Cloner
git clone <repo-url>
cd agent-apprentissage

# Virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Dépendances
pip install -r requirements.txt

# Configuration
cp .env.example .env  # ou editer .env directement

# Lancer Ollama
ollama serve

# Lancer l'app
streamlit run app.py
```

## Configuration (.env)

```env
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
AVAILABLE_MODELS=qwen2.5:1.5b,qwen2.5-coder:3b
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
| **Chat** | Interface conversationnelle avec le tuteur IA |
| **Dashboard** | KPIs progression + graphique barres |
| **Import PDF** | Upload + indexation de documents |
| **Profil** | Domaine, niveau, compétences |
| **DB** | Explorateur de tables + checkpoints LangGraph |
