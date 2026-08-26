# Guide de deploiement — Agent d'Apprentissage

Ce document decrit comment deployer l'application (backend FastAPI + frontend Next.js)
en local ou via Docker.

## Architecture

| Service | Port | Description |
|---|---|---|
| **Backend FastAPI** | 8000 | API REST + graphe LangGraph |
| **Frontend Next.js** | 3000 | Interface utilisateur |
| **SQLite** | — | `db/agent.db` (agent) + `checkpoints.db` (LangGraph) |
| **ChromaDB** | — | `data/chroma` (embeddings RAG) |

> **Modeles** : tous les LLMs sont **cloud** (Ollama Cloud). Seuls les embeddings RAG
> restent locaux (`qwen3-embedding:0.6b`). Une cle API Ollama est requise dans `.env`.

---

## 1. Deploiement local (developpement)

### Backend
```bash
# Depuis la racine du projet
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

pip install -r apps/api/requirements.txt
python -m uvicorn apps.api.main:app --reload --port 8000
```
Les migrations SQLite s'executent automatiquement au demarrage.

### Frontend
```bash
cd apps/web
npm install
npm run dev          # http://localhost:3000
```

### LangGraph Studio (debugging de l'agent)
```bash
langgraph dev        # utilise langgraph.json + .env.studio, port 2024
```

---

## 2. Deploiement Docker (production)

### Build + demarrage
```bash
docker compose up --build
```
- Backend : http://localhost:8000 (docs Swagger sur `/docs`)
- Frontend : http://localhost:3000

### Volumes persistants
Les donnees (DB SQLite + Chroma + documents) sont persistees dans des volumes Docker :
- `agent_db` → `/app/db`
- `agent_data` → `/app/data`

### Arret
```bash
docker compose down            # arrete les conteneurs
docker compose down -v         # arrete + supprime les volumes (donnees)
```

---

## 3. Variables d'environnement

Copier `.env.example` en `.env` et remplir :

| Variable | Description |
|---|---|
| `OLLAMA_BASE_URL` | URL Ollama Cloud (`https://ollama.com`) |
| `OLLAMA_API_KEY` | **Cle API Ollama Cloud (requis)** |
| `OLLAMA_MODEL` | Modele de generation par defaut (cloud) |
| `OLLAMA_EMBEDDING_MODEL` | Modele d'embedding RAG (local) |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` / `TOP_K` | Parametres RAG |

> ⚠️ Ne **jamais** committer une vraie cle API. `.env` doit rester hors Git.

---

## 4. Tests

```bash
python -m pytest tests/ -v
```
29 tests couvrent : memoire de session, Learner Model, competences dynamiques,
method evaluator (ε-greedy), revision planner, sous-agent memoire.

---

## 5. Points d'attention

- **Disque** : le projet utilise SQLite + Chroma en local. Prevoir un volume persistant.
- **Quota cloud** : les LLMs cloud consomment du quota Ollama. Surveiller l'usage.
- **Embeddings locaux** : necessitent un serveur Ollama local demarre (`ollama serve`)
  pour le RAG. Si absent, l'indexation des documents echouera.
- **CORS** : en production, adapter `allow_origins` dans `apps/api/main.py`.
