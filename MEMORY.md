# MEMORY.md — Agent d'Apprentissage

## Historique des modifications

### V1 — Architecture initiale (2026-08-18/19)
- [Structure initiale RAG] → erreurs: `langchain-huggingface` manquant → fix: ajouté à requirements.txt
- [Streamlit chat UI] → erreurs: `use_container_width` déprécié → fix: remplacé par `width="stretch"`
- [Session persistence JSON] → fix: créé `src/session_store.py` avec `sessions.json`
- [MemorySaver → SqliteSaver] → fix: remplacé par `langgraph_checkpoint_sqlite.SqliteSaver`
- [Architecture CDC V1] → fix: créé structure complète `db/`, `graph/`, `tools/`, `rag/`

### Audit CDC vs code (2026-08-20)
- [db/db.py DB_PATH] → fix: supprimé DB_PATH local, importé `config`
- [evaluation_memory_node vide] → fix: écrit quiz_attempts + feynman_restitutions + mastery
- [diagnostic_node sans écriture] → fix: upsert_mastery + update_profile au diagnostic
- [tools/artifact.py manquant] → fix: créé avec @tool + prompt LLM
- [rag/ingestion.py chunking] → fix: ajout détection heuristique de sections
- [.env modèles cloud] → fix: retirés, seulement qwen2.5:1.5b et qwen2.5-coder:3b
- [tools/@tool imports] → fix: migré vers `from langchain.tools import tool`
- [graph/graph.py emoji] → fix: emojis remplacés par texte ASCII (Windows)

### V2 — Refactoring majeur (2026-08-20)

**Raison :** Le chat ne se lançait pas — PyPDFLoader prenait 45s juste en import + embedding Ollama bloquait le UI. Pas de séparation ingestion/retrieval. Pas de gestion de sessions.

**Modifications :**

1. **rag/retriever.py** — Persistance ChromaDB incrémentale
   - `get_or_create_retriever()` — charge existant ou crée un vide
   - `add_documents_to_retriever()` — ajoute au vectorstore existant sans recréer
   - Plus besoin de recréer ChromaDB à chaque lancement

2. **app.py** — Refactoring complet (V2)
   - Séparation ingestion/rétrieval : `_index_pending_pdfs()` indexe les PDFs non indexés au démarrage
   - `_get_retriever()` cache le retriever ChromaDB persistant
   - `_get_agent_graph()` cache le StateGraph compilé
   - Gestion sessions sidebar : créer, switcher, supprimer
   - Messages chargés depuis la DB, pas en session_state only
   - Page DB Explorer ajoutée (tables + checkpoints LangGraph)
   - Indexation bg dans sidebar avec st.status
   - Suggestions pills avant premier message
   - Upload PDF → ingestion + ajout incrémental ChromaDB

3. **graph/nodes.py** — Corrections
   - `router_profil_node` ne fait plus le retrieval (c'était un double appel)
   - `tool_execution_node` utilise `state.get("method")` au lieu de `state.get("tool_name")`
   - `generate_node` ne re-génère pas si le tool a déjà produit une réponse

## État actuel

- **Point d'entrée** : `streamlit run app.py`
- **Base de données** : `db/agent.db` (SQLite, auto-créé)
- **Checkpoints** : `checkpoints.db` (SQLite, auto-créé)
- **ChromaDB** : `data/chroma/` (persistant, incrémental)
- **PDFs** : `data/documents/`
- **Modèle par défaut** : `qwen2.5:1.5b` (via `.env`)
- **Embedding** : `qwen3-embedding:0.6b` (via Ollama)

## Prochaines étapes

1. **Tester le pipeline complet** avec un PDF réel (upload → ingestion → question → réponse)
2. **Quiz interactif** — flow quiz: générer → réponse utilisateur → évaluer → update mastery
3. **Notifications révision espacée** — checker next_review_at dans dashboard
4. **Streaming responses** — afficher la réponse token par token
5. **Mettre à jour AGENT.md** avec l'architecture V2
