# Plan de deploiement — Agent d'Apprentissage

> Objectif : deployer l'application (backend FastAPI + frontend Next.js) sur des
> **hebergeurs gratuits**, en tenant compte des contraintes specifiques du projet.

---

## 1. Contraintes du projet

| Contrainte | Impact sur l'hebergement |
|---|---|
| **SQLite** (`db/agent.db`, `checkpoints.db`) | Necessite un **filesystem persistant** (les DB sont perdues au redemarrage sinon) |
| **ChromaDB** (`data/chroma`) | Idem : filesystem persistant requis pour les embeddings |
| **Embeddings locaux** (`qwen3-embedding:0.6b`) | Necessite **Ollama local** demarre — impossible sur la plupart des hebergeurs gratuits (pas de GPU/daemon) |
| **LLMs cloud** (Ollama Cloud) | Cle API requise, aucun impact hebergement |
| **LangGraph + checkpointer** | `checkpoints.db` SQLite, donc filesystem persistant |

### ⚠️ Point bloquant principal
Les hebergeurs gratuits **sans volume persistant** (Render free, Railway trial) **perdent
SQLite + Chroma a chaque redemarrage/deploy**. Deux solutions :
1. Choisir un hebergeur **avec volume persistant gratuit** (Fly.io).
2. **Migrer** SQLite → PostgreSQL manage + Chroma → vector store cloud (Chroma Cloud / Pinecone free).

---

## 2. Comparatif hebergeurs gratuits (2026)

### Backend FastAPI

| Hebergeur | Free tier | Volume persistant | Verdict |
|---|---|---|---|
| **[Fly.io](https://fly.io)** | 3 VMs partagées, 160 GB outbound | ✅ Volumes (1 GB free) | ✅ **Recommande** : seul free tier avec volume persistant fiable |
| **[Render](https://render.com)** | 750 h/mois, spin-down apres 15 min | ❌ Free = pas de disque persistant | ⚠️ SQLite/Chroma perdus au restart |
| **[Railway](https://railway.app)** | $5 credit/mois (trial) | ⚠️ Volumes mais credit limite | ⚠️ Credit vite epuise |
| **[Koyeb](https://koyeb.com)** | 1 service free | ❌ Pas de volume free | ⚠️ Meme probleme |
| **PythonAnywhere** | Free tier Python | ✅ Filesystem persistant | ⚠️ Pas ideal pour FastAPI async + ports |

### Frontend Next.js

| Hebergeur | Free tier | Verdict |
|---|---|---|
| **[Vercel](https://vercel.com)** | 100 GB bandwidth, 6000 build min | ✅ **Recommande** : integration Next.js native |
| **[Netlify](https://netlify.com)** | 100 GB bandwidth | ✅ Bonne alternative |
| **Cloudflare Pages** | Illimite bandwidth | ✅ Mais Next.js SSR moins bien supporte |

### Base de donnees / Vector store (si migration)

| Service | Free tier | Usage |
|---|---|---|
| **Neon** (Postgres) | 5 GB, branch illimites | Remplacer SQLite |
| **Supabase** (Postgres) | 500 MB | Remplacer SQLite |
| **Chroma Cloud** | Free tier | Remplacer ChromaDB local |
| **Pinecone** | 2 GB, 1 index | Remplacer ChromaDB local |

---

## 3. Strategie recommandee (100% gratuit)

### Option A — Rapide (volume persistant Fly.io)
Conserve SQLite + Chroma, mais **desactive les embeddings locaux** (le RAG ne
fonctionnera pas sans Ollama). Les LLMs restent cloud.

- **Backend** : Fly.io (avec volume 1 GB pour `db/` + `data/`)
- **Frontend** : Vercel
- **RAG** : desactive ou migre embeddings vers un provider cloud

### Option B — Perenne (migration DB + vector store cloud)
Plus robuste, tout est manage. Demande du code en plus.

- **Backend** : Render ou Fly.io (sans volume, car DB externe)
- **Frontend** : Vercel
- **DB** : Neon Postgres (migrer le schema SQLite)
- **Vector store** : Chroma Cloud ou Pinecone (migrer les embeddings)
- **Embeddings** : provider cloud (Ollama Cloud embeddings, ou OpenAI/Cohere)

---

## 4. Plan d'action — Option A (recommandee pour demarrer)

### Etape 1 : Preparer le code
- [ ] Rendre les **embeddings optionnels** : si Ollama local absent, le RAG est
      desactive proprement (ne bloque pas le demarrage).
- [ ] Verifier que `config.py` lit bien les paths depuis l'env (`DB_PATH`,
      `CHROMA_DIR`, `CHECKPOINT_DB`) pour pointer vers le volume Fly.io.
- [ ] Ajouter un `fly.toml` (config Fly.io) avec le volume monte sur `/app/data` et `/app/db`.

### Etape 2 : Deployer le backend sur Fly.io
```bash
fly launch --copy-config --no-deploy      # genere fly.toml
fly volumes create agent_data --size 1    # volume persistant 1 GB
fly secrets set OLLAMA_API_KEY=... OLLAMA_BASE_URL=https://ollama.com
fly deploy
```

### Etape 3 : Deployer le frontend sur Vercel
```bash
cd apps/web
npx vercel --prod
# Ou connecter le repo GitHub sur vercel.com
```
- Configurer la variable `NEXT_PUBLIC_API_URL` (ou proxy) pour pointer vers l'URL Fly.io.
- Adapter `apps/web/lib/api.ts` (`API_BASE`) pour utiliser l'URL du backend en production.

### Etape 4 : CORS + URL backend
- Dans `apps/api/main.py`, ajouter l'origine Vercel a `allow_origins`.
- Dans le frontend, remplacer `API_BASE = "/api"` par l'URL reelle du backend en prod.

### Etape 5 : Tests post-deploiement
- [ ] `GET /health` repond 200.
- [ ] Une session de chat fonctionne (LLM cloud).
- [ ] Les donnees persistent apres un redemarrage (volume Fly.io).
- [ ] La page `/revision` affiche le calendrier.

---

## 5. Variables d'environnement a fournir (production)

Voir `.env.example` pour la liste complete. Les **requises** :

| Variable | Requis | Description |
|---|---|---|
| `OLLAMA_API_KEY` | ✅ | Cle API Ollama Cloud |
| `OLLAMA_BASE_URL` | ✅ | `https://ollama.com` |
| `OLLAMA_MODEL` | ✅ | Modele de generation (cloud) |
| `AVAILABLE_MODELS` | — | Liste des modeles cloud |
| `DB_PATH` / `CHROMA_DIR` / `CHECKPOINT_DB` | ✅ (Fly.io) | Pointer vers le volume persistant |
| `RAG_*` | — | Parametres RAG (valeurs par defaut OK) |
| `WEB_SEARCH_DEFAULT_PROVIDER` | — | `ddgs` (sans cle) par defaut |

---

## 6. Limites des free tiers a surveiller

- **Fly.io** : 3 VMs, 1 GB volume. Spin-down possible apres inactivite.
- **Vercel** : fonctions serverless = timeout 10s (free). Les appels LLM longs
  peuvent depasser → preferer le streaming ou augmenter le timeout cote backend.
- **Quota Ollama Cloud** : surveiller la consommation de tokens.
- **Cold start** : le backend Fly.io peut mettre quelques secondes a demarrer.

---

## 7. Prochaines actions immediates

1. **Choisir l'option** (A ou B).
2. Creer les comptes : [Fly.io](https://fly.io), [Vercel](https://vercel.com).
3. Recuperer la **cle API Ollama Cloud**.
4. Lancer le deploiement (Etapes 2-3).
