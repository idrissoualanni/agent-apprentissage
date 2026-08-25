# Agent d'Apprentissage V3

Agent pédagogique basé sur **LangGraph + Ollama + ChromaDB**. Architecture Client-Serveur : frontend **Next.js 14** + backend **FastAPI**, sessions multi-utilisateurs, streaming, recherche web multi-provider, human-in-the-loop, répétition espacée (Leitner).

---

## Architecture V3

```
┌──────────────────────────────┐     ┌───────────────────────────────────────────┐
│   Frontend Next.js 14        │────▶│   Backend FastAPI                         │
│   http://localhost:3000      │     │   http://localhost:8000                    │
│                              │     │                                           │
│   app/ (App Router)          │     │   main.py → FastAPI + lifespan            │
│     page.tsx                 │     │   ├── routes/                             │
│     chat/page.tsx            │     │   │   chat.py        /api/chat            │
│     import/page.tsx          │     │   │   sessions.py    /api/sessions        │
│     dashboard/page.tsx       │     │   │   documents.py   /api/documents       │
│     profil/page.tsx          │     │   │   profile.py     /api/profile         │
│   components/                │     │   │   progress.py    /api/progress        │
│     ChatWindow.tsx           │     │   │   models.py      /api/models          │
│     MessageBubble.tsx        │     │   ├── agent/                              │
│     SessionList.tsx          │     │   │   graph.py       StateGraph V3        │
│     StreamingText.tsx        │     │   │   nodes.py       9 nœuds LangGraph     │
│     ConfirmationButtons.tsx  │     │   │   state.py       AgentState           │
│     ToolBadge.tsx            │     │   ├── tools/                              │
│     ProgressCard.tsx         │     │   │   quiz.py, feynman.py, artifact.py   │
│     ModelSwitcher.tsx        │     │   │   web_search.py, progress.py          │
│   lib/                       │     │   ├── llm/                               │
│     api.ts                   │     │   │   cloud_providers.py  get_llm()       │
│     sessions.ts              │     │   ├── rag/                               │
│     utils.ts                 │     │   │   retriever.py, ingestion.py         │
│   tailwind.config.ts         │     │   ├── db/                                │
│                              │     │   │   schema_v3.sql, crud.py, migrations  │
│   Port: 3000                 │     │   └── services/                          │
│                              │     │       rag_service.py                     │
│                              │     │   Port: 8000                             │
└──────────────────────────────┘     └───────────────────────────────────────────┘
                    │                              │
                    │         HTTP/REST            │
                    └──────────────────────────────┘

                        ┌───────────────────┐
                        │    SQLite V3       │
                        │    12 tables       │
                        │    db/agent.db     │
                        └───────────────────┘
                                │
                        ┌───────┴────────┐
                        │  ChromaDB       │
                        │  data/chroma/   │
                        └────────────────┘
                                │
                        ┌───────┴────────┐
                        │  Ollama         │
                        │  (local/cloud)  │
                        └────────────────┘
```

---

## StateGraph LangGraph V3

```
START → router_profil ──→ answer_processing? ──→ retrieve? ──→ method_selection
                              │                       │            │
                              │                       │            ├─→ confirmation ──→ tool_execution
                              │                       │            │   (quiz/feynman/    │
                              │                       │            │    artifact)        │
                              │                       │            │                     │
                              │                       │            ├─→ web_search ──→ generate
                              │                       │            │                     │
                              │                       │            └─→ generate ────────→ END
                              │                       │                     ↑
                              └─→ diagnostic ─────────┼─────────────────────┘
                                                      │
                                                      └─→ evaluation_memory ──→ generate → END
```

**Nœuds V3 :**

| Nœud | Rôle |
|---|---|
| `router_profil` | Charge profil, injecte ModelManager, détecte méta/salutations |
| `answer_processing` | Parse réponses quiz/Feynman en attente, extrait `user_id` |
| `diagnostic` | Questions initiales si pas de domaine défini |
| `retrieve` | RAG conditionnel via ChromaDB (skip si salutation/méta) |
| `method_selection` | Choix pédagogique + détection web_search/revision |
| `confirmation` | Human-in-the-loop avant quiz/Feynman/artefact |
| `tool_execution` | Exécution quiz, Feynman, artifact, web_search |
| `evaluation_memory` | Score Leitner + log `tool_usage` en base |
| `generate` | Génération via `ModelManager.get_llm()` + ToolBadge |

---

## Fonctionnalités V3

| Fonctionnalité | Description |
|---|---|
| **Multi-utilisateurs** | `user_id` sur toutes les tables, sessions isolées |
| **ModelManager** | Catalogue 15+ modèles cloud, presets par opération, cache SQLite |
| **Recherche web** | DuckDuckGo (DDGS), Tavily, Brave Search — sélection auto ou manuelle |
| **Streaming** | `StreamingText` avec animation typewriter, bulles animées |
| **Human-in-the-loop** | Confirmation avant quiz/Feynman/artefact (boutons colorés) |
| **ToolBadge** | Indicateur visuel des outils utilisés (zap, colors par type) |
| **Sessions persistantes** | Historique complet, relecture, navigation inter-sessions |
| **RAG conditionnel** | Skip retrieval pour salutations/méta → gain de latence |
| **Artefacts pédagogiques** | Génération de contenus interactifs (flashcards, mind maps...) |
| **Cache web search** | TTL configurable, évite les requêtes répétées |
| **Animations UI** | bubble-in, glow-pulse, typing-dot (tailwind.config.ts) |

---

## Base de données SQLite V3 (12 tables)

| Table | Description |
|---|---|
| `learner_profile` | Profil utilisateur (domaine, niveau, préférences) |
| `competency` | Compétences hiérarchiques (auto-référencées) |
| `mastery` | Score + boîte Leitner + date prochaine révision |
| `document` | PDFs uploadés |
| `chunk` | Segments indexés |
| `session` | Sessions de conversation (UUID thread_id) |
| `message` | Messages utilisateur/assistant |
| `quiz_attempt` | Tentatives de quiz |
| `feynman_restitution` | Évaluations Feynman |
| `artifact` | Artefacts pédagogiques générés |
| `model_config` | Configuration des modèles LLM |
| `web_search_cache` | Cache des recherches web |
| `tool_usage` | Logs d'utilisation des outils |

---

## Installation

```bash
# Cloner
git clone https://github.com/idrissoualanni/agent-apprentissage.git
cd agent-apprentissage

# Virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Dépendances
pip install -r apps/api/requirements.txt

# Configuration
cp .env.example .env           # ou éditer .env directement

# Frontend
cd apps/web
npm install
cd ../..
```

## Configuration (.env)

```env
# ─── Modèles ────────────────────────────────────────
AVAILABLE_MODELS=qwen2.5:1.5b,qwen2.5-coder:3b,minimax-m3
OLLAMA_MODEL=qwen2.5:1.5b

# ─── Embedding ──────────────────────────────────────
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b

# ─── Ollama Cloud (optionnel) ──────────────────────
OLLAMA_BASE_URL=              # vide = local, https://ollama.com = cloud
OLLAMA_API_KEY=

# ─── RAG ────────────────────────────────────────────
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
TOP_K=3

# ─── Web Search ─────────────────────────────────────
# WEB_SEARCH_DEFAULT_PROVIDER=ddgs    # ddgs | tavily | brave
# TAVILY_API_KEY=
# BRAVE_API_KEY=
```

## Modèles Ollama requis (mode local)

```bash
ollama pull qwen2.5:1.5b           # LLM principal
ollama pull qwen2.5-coder:3b       # Alternative
ollama pull qwen3-embedding:0.6b   # Embeddings
```

---

## Lancement

### ⚡ Commande rapide (2 terminals)

**Terminal 1 — Backend FastAPI :**
```bash
cd apps/api
uvicorn apps.api.main:app --reload --port 8000
```

**Terminal 2 — Frontend Next.js :**
```bash
cd apps/web
npm run dev
```

### 🌐 URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API Backend | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Health | http://localhost:8000/health |

### Pré-requis

1. **Ollama** doit être lancé : `ollama serve` (ou URL cloud dans `.env`)
2. **Python 3.11+** avec venv activé
3. **Node.js 18+** avec `npm install` fait dans `apps/web/`

---

## Routes API V3

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/api/chat` | Envoyer un message + recevoir la réponse de l'agent |
| `GET` | `/api/sessions` | Lister les sessions |
| `GET` | `/api/sessions/{id}/messages` | Historique d'une session |
| `DELETE` | `/api/sessions/{id}` | Supprimer une session |
| `POST` | `/api/documents/upload` | Upload PDF |
| `GET` | `/api/documents` | Lister les documents |
| `GET` | `/api/profile` | Profil utilisateur |
| `PUT` | `/api/profile` | Mettre à jour le profil |
| `GET` | `/api/progress` | Progression Leitner |
| `GET` | `/api/models` | Modèles disponibles |

---

## Diagrampes

Les diagrammes d'architecture sont dans `diagrams/` (format `.drawio`, ouvrables avec draw.io / VS Code) :

| Fichier | Contenu |
|---|---|
| `diagramme_architecture_technique.drawio` | Architecture complète V3 (Frontend + Backend + RAG + Agent + Tools + DB) |
| `diagramme_erd_modele_donnees.drawio` | ERD des 12 tables V3 |
| `diagramme_stategraph_agent.drawio` | StateGraph LangGraph V3 (couleurs par nœud) |
| `diagramme_stategraph.drawio` | StateGraph alternatif (layout orthogonal) |
| `agent_apprentissage_diagrammes.drawio` | 5 pages : Use Case, Architecture, StateGraph, ERD, Séquence |
