# LangGraph Studio — Debugging de l'Agent V3

LangGraph Studio est l'outil visuel officiel de LangChain pour **visualiser, inspecter et déboguer** le graphe de l'agent d'apprentissage.

---

## 🎯 Ce que Studio permet

| Fonctionnalité | Description |
|---|---|
| **Visualisation du graphe** | Voir tous les nœuds (router, diagnostic, retrieve, method, generate, tool, evaluate, confirmation) et leurs transitions |
| **Inspection de l'état** | Voir l'`AgentState` complet à chaque étape (question, method, rag_needed, etc.) |
| **Time-travel debugging** | Rejouer la conversation nœud par nœud, revenir en arrière, modifier l'état et reprendre |
| **Inspection des prompts** | Voir exactement quel prompt est envoyé à chaque LLM |
| **Test interactif** | Envoyer des questions directement depuis Studio et observer le flux |
| **Breakpoints** | Mettre en pause l'exécution avant/après un nœud spécifique |

---

## 📋 Prérequis

### 1. Ollama local doit tourner avec les modèles nécessaires

```powershell
# Vérifier qu'Ollama tourne
curl http://localhost:11434/api/tags

# Modèles requis (déjà installés) :
#   - qwen2.5-coder:3b       (LLM local pour le chat)
#   - qwen3-embedding:0.6b   (embeddings pour le RAG)
```

Si Ollama n'est pas lancé :
```powershell
# Démarrer Ollama en arrière-plan
Start-Process "C:\Users\hp\AppData\Local\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
```

### 2. Dépendances installées

`langgraph-cli[inmem]` est déjà dans `apps/api/requirements.txt`. Si besoin :
```powershell
cd C:\Users\hp\Desktop\test_python
.\venv\Scripts\Activate.ps1
pip install "langgraph-cli[inmem]"
```

---

## 🚀 Lancer LangGraph Studio

### Option A — Via le CLI (recommandé)

```powershell
cd C:\Users\hp\Desktop\test_python
.\venv\Scripts\Activate.ps1
langgraph dev
```

Cela va :
1. Lire `langgraph.json` à la racine
2. Charger le graphe depuis `apps/api/agent/studio_graph.py:graph`
3. Démarrer un serveur local (port 2024 par défaut)
4. Ouvrir automatiquement l'interface Studio dans le navigateur

> ⚠️ **Premier lancement lent** : le CLI charge tout l'environnement LangGraph. Attendez 30-60s.

### Option B — Via le script de lancement

```powershell
cd C:\Users\hp\Desktop\test_python
.\start_studio.ps1
```

---

## ⚙️ Configuration

### `langgraph.json` (racine du projet)

```json
{
  "dependencies": ["./apps/api"],
  "graphs": {
    "agent-apprentissage": "./apps/api/agent/studio_graph.py:graph"
  },
  "env": ".env.studio",
  "python_version": "3.12"
}
```

- **`dependencies`** : installe les deps depuis `apps/api/requirements.txt`
- **`graphs`** : pointe vers la variable `graph` de `studio_graph.py`
- **`env`** : utilise `.env.studio` (mode **cloud** — consomme du quota Ollama Cloud)

### `.env.studio` — Mode cloud

Ce fichier configure Ollama en mode **cloud** (`OLLAMA_BASE_URL=https://ollama.com` + `OLLAMA_API_KEY`). Les LLMs cloud (minimax-m3, kimi-k2.7-code…) sont utilisés. ⚠️ Le debugging consomme du quota. Les **embeddings restent locaux** (qwen3-embedding:0.6b).

> Pour revenir au 100 % local (sans quota), remets `ModelManager(force_local=True)` dans `studio_graph.py` et vide `OLLAMA_BASE_URL` dans `.env.studio`.

### `studio_graph.py` — Points clés

```python
# ModelManager en mode cloud : utilise minimax-m3, kimi-k2.7-code… selon les presets
model_manager = ModelManager(force_local=False)

# Retriever ChromaDB réel, avec fallback mock si indisponible
retriever = _build_retriever()

# PAS de checkpointer SQLite : Studio gère le sien pour le time-travel
graph = build_agent_graph(
    retriever=retriever,
    model_manager=model_manager,
    db_path=str(config.DB_PATH),
    with_checkpointer=False,
)
```

---

## 🔍 Déboguer l'agent dans Studio

### 1. Envoyer une question

Dans l'interface Studio :
- Cliquez sur le graphe `agent-apprentissage`
- Dans le panneau de droite, entrez une question (ex: `"Explique-moi les listes Python"`)
- Cliquez sur **Submit**

### 2. Observer le flux

Studio affiche :
- Le **chemin emprunté** à travers les nœuds (en surbrillance)
- L'**état complet** après chaque nœud
- Les **prompts LLM** envoyés (cliquez sur un nœud `generate` ou `tool`)

### 3. Time-travel debugging

- Chaque exécution crée un **thread** avec des checkpoints
- Cliquez sur un checkpoint pour **revenir à cet état**
- Modifiez l'état (ex: forcez `method: "quiz"`) et **reprenez** l'exécution
- Idéal pour tester "que se passe-t-il si le router choisit X ?"

### 4. Breakpoints

- Clic droit sur un nœud → **Add breakpoint**
- L'exécution s'arrête avant ce nœud
- Inspectez/modifiez l'état, puis continuez

---

## 🧪 Scénarios de test recommandés

| Scénario | Question | Ce qu'on observe |
|---|---|---|
| **Scaffold** | `"C'est quoi une liste ?"` | router → retrieve → method(scaffold) → generate |
| **Quiz** | `"Donne-moi un quiz sur l'IA"` | router → method(quiz) → confirmation → tool → evaluate |
| **RAG** | `"Résume le document"` | router → retrieve (chunks) → generate avec contexte |
| **Web search** | `"Prix du Bitcoin ?"` | router → method(web_search) → tool → generate |
| **Feynman** | `"Explique comme à un enfant"` | router → method(feynman) → generate |
| **Diagnostic** | (premier message, pas de profil) | router → diagnostic → generate |

---

## 🐛 Dépannage

### "No module named 'langchain_chroma'"
Le retriever ChromaDB n'est pas disponible. Studio utilise automatiquement un **mock vide** (le nœud `retrieve` ne retournera pas de contexte). Pour activer le vrai RAG :
```powershell
pip install langchain-chroma
```

### Le graphe ne se charge pas
Vérifiez que le graphe compile manuellement :
```powershell
.\venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from apps.api.agent import studio_graph; print(list(studio_graph.graph.get_graph().nodes.keys()))"
```

### Erreur 429 (quota cloud)
Studio utilise désormais les **modèles cloud** (`force_local=False`). Si tu hits une limite de quota (429), deux options :
1. **Attendre** que le quota se réinitialise.
2. **Repasser en local** : mets `ModelManager(force_local=True)` dans `studio_graph.py` et vide `OLLAMA_BASE_URL` dans `.env.studio`.

### Ollama ne répond pas
```powershell
# Redémarrer Ollama
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
Start-Process "C:\Users\hp\AppData\Local\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
```

---

## 📚 Ressources

- [LangGraph Studio Docs](https://langchain-ai.github.io/langgraph/concepts/langgraph_studio/)
- [LangGraph CLI Reference](https://langchain-ai.github.io/langgraph/cloud/reference/cli/)
- [Time-travel debugging](https://langchain-ai.github.io/langgraph/concepts/time_travel/)
