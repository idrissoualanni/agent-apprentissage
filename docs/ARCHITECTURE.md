# Architecture V3 — Agent d'Apprentissage

**Date** : 22 août 2026
**Statut** : Validé pour implémentation
**Auteur** : MiniMax-M3

---

## 1. Vision & objectifs

Refactor majeur du projet V2 (Streamlit) vers une architecture moderne :

| Objectif | Comment |
|---|---|
| **UI type Claude.ai** | Sidebar sessions + chat central + panneau artefacts droite |
| **Artefacts interactifs** | 4 types : schéma (Mermaid), quiz (React state), code (Monaco), chart (Recharts) |
| **Streaming token par token** | SSE (Server-Sent Events) depuis FastAPI vers le frontend |
| **RAG sémantique avec double-check** | 3 vérifications avant d'utiliser le contexte : doc existe + score pertinent + LLM valide |
| **Human-in-the-loop intelligent** | 3 niveaux d'action (auto / confirm / bloquant), confirmation UI pour actions coûteuses |
| **Gestion centralisée des modèles** | Catalogue unifié Ollama local + cloud, fallback intelligent, format de sortie contrôlé |
| **Web search améliorée** | Routage contextuel + cache + sources citées + multi-provider |
| **Transparence des outils** | User voit quelle tool a produit chaque réponse (badges visibles) |
| **Profil enrichi** | Compétences maîtrisées, lacunes, niveau adaptatif |
| **Méthodes auto-activées** | Déclenchement contextuel sans intervention explicite |
| **Multi-utilisateur-ready** | Schéma DB ajoute `user_id` (mono-user V3 mais préparé V4) |
| **DB V2 préservée** | SQLite, mêmes tables + ajout table `artifact` |

---

## 2. Architecture cible

```
┌──────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js 14)                         │
│                                                                  │
│  /chat                /dashboard         /documents              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ Sidebar      │    │ KPIs +       │    │ Upload PDF   │       │
│  │ - Sessions   │    │ Recharts     │    │ Drag & Drop  │       │
│  │ - Profil     │    │              │    │              │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│  ┌─────────────────────────────────────────────────────┐        │
│  │ Chat panel (streaming + HITL + tool badges visibles)│        │
│  └─────────────────────────────────────────────────────┘        │
│  ┌─────────────────────────────────────────────────────┐        │
│  │ Artifact panel (Quiz/Schema/Code/Chart) rétractable │        │
│  └─────────────────────────────────────────────────────┘        │
│                                                                  │
│            ▲ REST              ▲ SSE streaming                   │
└────────────┼────────────────────┼─────────────────────────────────┘
             │                    │
┌────────────┼────────────────────┼─────────────────────────────────┐
│            ▼      BACKEND (FastAPI + LangGraph)                   │
│                                                                  │
│  /routes/                                                        │
│    chat.py         POST /api/chat + GET /api/chat/stream        │
│    sessions.py     CRUD sessions                                 │
│    documents.py    Upload PDF, list, delete                     │
│    profile.py      Get/update profil + compétences               │
│    progress.py     Mastery summary + revision plan               │
│    models.py       Catalogue modèles, presets, fallback          │
│                                                                  │
│  /services/                                                      │
│    agent_service.py    Wrap LangGraph invoke()                   │
│    streaming.py        SSE token-by-token                       │
│    rag_service.py      ChromaDB + double-check                  │
│    checkpoint_service.py SqliteSaver                              │
│    web_search_service.py DDGS + cache + sources                 │
│                                                                  │
│  /agent/                                                         │
│    graph.py            StateGraph (LangGraph)                    │
│    nodes/                                                        │
│      router.py         Profil + domaine + tools dispatch         │
│      diagnostic.py     Estimation niveau                         │
│      retrieval.py      RAG sémantique double-check               │
│      method.py         Sélection méthode auto-activée            │
│      generate.py       Génération avec prompt conditionnel       │
│      tool.py           Quiz/Feynman/Artifact/Web/Revision        │
│      evaluate.py       Mise à jour Leitner                       │
│      confirmation.py   HITL (3 niveaux)                          │
│    state.py            AgentState (profil enrichi)               │
│    tools/                                                        │
│      quiz.py           Parser Markdown + fallback JSON           │
│      feynman.py        Évaluation restitution                    │
│      progress.py       Leitner + plans                           │
│      artifact.py       4 types d'artefacts                       │
│      web_search.py     DDGS + cache                              │
│                                                                  │
│         ▲                          ▲                             │
│         │ sqlite3                  │ HTTP                        │
│         ▼                          ▼                             │
│    ┌──────────┐              ┌──────────┐                        │
│    │ SQLite   │              │ ChromaDB │                        │
│    │ (db/)    │              │ (data/   │                        │
│    └──────────┘              │  chroma) │                        │
│                              └──────────┘                        │
│                                       ▲                          │
│                                       │ HTTP                     │
│                                  ┌────┴────────────┐             │
│                                  │ Model Manager  │             │
│                                  │ - Catalogue    │             │
│                                  │ - Format ctrl  │             │
│                                  │ - Fallback     │             │
│                                  └────┬────────────┘             │
│                                       │                          │
│                                  ┌────┴─────┐                     │
│                                  │ Ollama  │                     │
│                                  │ + Cloud │                     │
│                                  └─────────┘                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Structure de répertoires

```
agent_apprentissage/
├── apps/
│   ├── web/                          # Frontend Next.js
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx              # Redirection /chat
│   │   │   ├── chat/page.tsx
│   │   │   ├── dashboard/page.tsx
│   │   │   ├── documents/page.tsx
│   │   │   ├── profile/page.tsx
│   │   │   ├── models/page.tsx       # Gestion modèles
│   │   │   └── api/
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatWindow.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   ├── StreamingText.tsx
│   │   │   │   ├── ConfirmationButtons.tsx
│   │   │   │   └── ToolBadge.tsx
│   │   │   ├── artifacts/
│   │   │   │   ├── ArtifactRenderer.tsx
│   │   │   │   ├── SchemaArtifact.tsx
│   │   │   │   ├── QuizArtifact.tsx
│   │   │   │   ├── CodeArtifact.tsx
│   │   │   │   └── ChartArtifact.tsx
│   │   │   ├── sidebar/
│   │   │   │   ├── SessionList.tsx
│   │   │   │   └── SessionItem.tsx
│   │   │   ├── upload/PdfDropzone.tsx
│   │   │   ├── profile/
│   │   │   │   ├── CompetencyTree.tsx
│   │   │   │   ├── MasteryBadge.tsx
│   │   │   │   └── GapsList.tsx
│   │   │   ├── models/
│   │   │   │   ├── ModelSelector.tsx
│   │   │   │   └── FormatConfigPanel.tsx
│   │   │   └── ui/
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   ├── sse.ts
│   │   │   └── types.ts
│   │   ├── package.json
│   │   ├── tailwind.config.ts
│   │   └── tsconfig.json
│   │
│   └── api/                          # Backend FastAPI
│       ├── main.py
│       ├── routes/
│       │   ├── chat.py
│       │   ├── sessions.py
│       │   ├── documents.py
│       │   ├── profile.py
│       │   ├── progress.py
│       │   └── models.py
│       ├── services/
│       │   ├── agent_service.py
│       │   ├── streaming.py
│       │   ├── rag_service.py
│       │   ├── checkpoint_service.py
│       │   ├── web_search_service.py
│       │   └── model_manager.py       # Gestion modèles
│       ├── agent/
│       │   ├── graph.py
│       │   ├── nodes/
│       │   │   ├── __init__.py
│       │   │   ├── router.py
│       │   │   ├── diagnostic.py
│       │   │   ├── retrieval.py
│       │   │   ├── method.py
│       │   │   ├── generate.py
│       │   │   ├── tool.py
│       │   │   ├── evaluate.py
│       │   │   └── confirmation.py
│       │   ├── state.py
│       │   └── tools/
│       │       ├── quiz.py
│       │       ├── feynman.py
│       │       ├── progress.py
│       │       ├── artifact.py
│       │       └── web_search.py
│       ├── db/
│       │   ├── schema.sql
│       │   ├── schema_v3.sql
│       │   └── db.py
│       ├── rag/
│       │   ├── ingestion.py
│       │   └── retriever.py
│       ├── config.py
│       ├── requirements.txt
│       └── pyproject.toml
│
├── data/
│   ├── documents/
│   ├── chroma/
│   └── model_cache/                  # Cache réponses LLM
├── db/
│   ├── agent.db
│   └── checkpoints.db
├── tests/
│   ├── test_e2e.py
│   ├── test_quiz_parser.py
│   ├── test_streaming.py
│   ├── test_rag_double_check.py
│   ├── test_model_manager.py
│   └── test_web_search.py
├── docs/
│   ├── ARCHITECTURE.md               # Ce document
│   ├── API.md
│   └── FRONTEND.md
└── README.md
```

---

## 4. Schéma DB V3

```sql
-- Nouvelle table : artefacts générés par l'agent
CREATE TABLE IF NOT EXISTS artifact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES session(id) ON DELETE CASCADE,
    competency_id INTEGER REFERENCES competency(id) ON DELETE SET NULL,
    artifact_type TEXT NOT NULL CHECK (artifact_type IN ('schema', 'quiz', 'code', 'chart')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Index
CREATE INDEX IF NOT EXISTS idx_artifact_session ON artifact(session_id);
CREATE INDEX IF NOT EXISTS idx_artifact_competency ON artifact(competency_id);

-- Profil enrichi : ajout champs contexte d'apprentissage
ALTER TABLE learner_profile ADD COLUMN learning_context TEXT DEFAULT '';
ALTER TABLE learner_profile ADD COLUMN goals TEXT DEFAULT '';

-- Compétences : ajout niveau adaptatif
ALTER TABLE competency ADD COLUMN min_level TEXT DEFAULT 'debutant';
ALTER TABLE competency ADD COLUMN max_level TEXT DEFAULT 'avance';

-- Maîtrise : ajout timestamp "last practiced at" + "stable_since"
ALTER TABLE mastery ADD COLUMN stable_since DATETIME;
ALTER TABLE mastery ADD COLUMN practice_count INTEGER DEFAULT 0;

-- Nouvelles tables : modèle catalog
CREATE TABLE IF NOT EXISTS model_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('ollama_local', 'ollama_cloud')),
    default_temperature REAL DEFAULT 0.3,
    format_mode TEXT NOT NULL DEFAULT 'json_or_markdown' 
        CHECK (format_mode IN ('strict_json', 'json_or_markdown', 'markdown', 'free_text')),
    max_tokens INTEGER DEFAULT 2048,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Web search : cache
CREATE TABLE IF NOT EXISTS web_search_cache (
    query_hash TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    results_json TEXT NOT NULL,
    sources_json TEXT,
    fetched_at DATETIME DEFAULT (datetime('now')),
    ttl_hours INTEGER DEFAULT 24
);

-- Tool usage tracking (transparence)
CREATE TABLE IF NOT EXISTS tool_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER REFERENCES message(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    tool_input TEXT,
    tool_output TEXT,
    execution_time_ms INTEGER,
    cost_estimate REAL,
    created_at DATETIME DEFAULT (datetime('now'))
);

-- Préparation multi-utilisateur V4
ALTER TABLE learner_profile ADD COLUMN user_id TEXT DEFAULT 'default';
ALTER TABLE session ADD COLUMN user_id TEXT DEFAULT 'default';
```

---

## 5. Gestion centralisée des modèles

### 5.1 Principes

- **Catalogue unifié** : tous les modèles (local + cloud) sont déclarés dans `model_config`
- **Présets par tâche** : chaque type d'opération (génération, quiz, embedding) a son modèle par défaut
- **Format de sortie contrôlé** : chaque modèle a un `format_mode` (strict_json / json_or_markdown / markdown / free_text)
- **Fallback intelligent** : si un modèle échoue (401, timeout), bascule automatique sur le suivant
- **Format auto-détecté** : le parser de sortie est adapté au `format_mode` du modèle utilisé

### 5.2 Catalogue par défaut

```python
# apps/api/services/model_manager.py
DEFAULT_CATALOG = [
    {
        "model_name": "minimax-m3",
        "display_name": "minimax-m3 (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.3,
        "format_mode": "json_or_markdown",  # bavard
        "max_tokens": 4096,
    },
    {
        "model_name": "qwen2.5:1.5b",
        "display_name": "Qwen 2.5 1.5B (Local)",
        "provider": "ollama_local",
        "default_temperature": 0.2,
        "format_mode": "strict_json",  # discipliné
        "max_tokens": 2048,
    },
    {
        "model_name": "qwen3.5:397b",
        "display_name": "Qwen 3.5 397B (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.3,
        "format_mode": "json_or_markdown",
        "max_tokens": 8192,
    },
    {
        "model_name": "kimi-k2.7-code",
        "display_name": "Kimi K2.7 Code (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.2,
        "format_mode": "strict_json",
        "max_tokens": 4096,
    },
    {
        "model_name": "deepseek-v4-flash:preview",
        "display_name": "DeepSeek V4 Flash (Cloud)",
        "provider": "ollama_cloud",
        "default_temperature": 0.3,
        "format_mode": "json_or_markdown",
        "max_tokens": 4096,
    },
]

# Présets par type d'opération
OPERATION_PRESETS = {
    "chat": {"model_name": "minimax-m3", "temperature": 0.3},
    "quiz_generation": {"model_name": "qwen2.5:1.5b", "temperature": 0.2},
    "feynman_eval": {"model_name": "minimax-m3", "temperature": 0.2},
    "artifact": {"model_name": "kimi-k2.7-code", "temperature": 0.5},
    "diagnostic": {"model_name": "qwen2.5:1.5b", "temperature": 0.3},
    "relevance_check": {"model_name": "qwen2.5:1.5b", "temperature": 0.0},
    "embedding": {"model_name": "qwen3-embedding:0.6b", "provider": "ollama_local"},
}
```

### 5.3 API du Model Manager

```python
class ModelManager:
    def __init__(self, config: Config):
        self.config = config
        self._cache = {}

    def get_llm(self, operation: str, **overrides) -> ChatModel:
        """Retourne un LLM configuré pour l'opération demandée."""
        preset = {**OPERATION_PRESETS.get(operation, {}), **overrides}
        model_name = preset["model_name"]
        temperature = preset.get("temperature", 0.3)

        # Vérifier le format_mode
        model_config = self._get_model_config(model_name)
        format_mode = model_config.get("format_mode", "json_or_markdown")

        # Instancier selon le provider
        if model_config["provider"] == "ollama_cloud":
            llm = CloudOllamaChat(
                model=model_name,
                temperature=temperature,
                host=self.config.OLLAMA_BASE_URL,
                api_key=self.config.OLLAMA_API_KEY,
            )
        else:
            llm = ChatOllama(model=model_name, temperature=temperature)

        # Wrap avec parser adapté au format_mode
        return FormatControlledLLM(llm, format_mode)

    def _get_model_config(self, model_name: str) -> dict:
        """Lit la config depuis la DB ou fallback sur DEFAULT_CATALOG."""
        # Implémentation : SELECT * FROM model_config WHERE model_name = ?
        # Si vide : retourne DEFAULT_CATALOG entry
        ...

    def list_available(self) -> list[dict]:
        """Liste tous les modèles disponibles (DB + Ollama list())."""
        ...

    def fallback(self, failed_model: str) -> str:
        """Retourne un modèle de fallback si failed_model échoue."""
        ...
```

### 5.4 Format-controlled wrapper

Adapte le parser de sortie selon le `format_mode` du modèle :

```python
class FormatControlledLLM:
    """Wrap un LLM et adapte la sortie selon format_mode."""

    def __init__(self, llm, format_mode: str):
        self.llm = llm
        self.format_mode = format_mode
        self.parser = self._get_parser()

    def invoke(self, messages):
        response = self.llm.invoke(messages)
        return self.parser.parse(response.content)

    def _get_parser(self):
        if self.format_mode == "strict_json":
            return StrictJSONParser()      # plante si pas JSON
        elif self.format_mode == "json_or_markdown":
            return HybridParser()          # essaie JSON puis Markdown
        elif self.format_mode == "markdown":
            return MarkdownParser()       # accepte Markdown structuré
        else:
            return FreeTextParser()       # tout passe


class HybridParser:
    """Essaie JSON strict puis fallback sur Markdown parser."""
    def parse(self, content):
        # Tente JSON
        if content.strip().startswith("{") or "```json" in content:
            try:
                return {"type": "json", "data": json.loads(content)}
            except json.JSONDecodeError:
                pass
        # Fallback Markdown
        return {"type": "markdown", "data": content}
```

### 5.5 Configuration Ollama Cloud

Le système supporte les modèles Ollama Cloud (https://ollama.com) en priorité, avec fallback local.

```env
# .env
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_API_KEY=...
OLLAMA_CLOUD_MODELS=minimax-m3,qwen3.5:397b,kimi-k2.7-code,deepseek-v4-flash:preview
OLLAMA_LOCAL_MODELS=qwen2.5:1.5b,qwen2.5-coder:3b,qwen3-embedding:0.6b
DEFAULT_CHAT_MODEL=minimax-m3
DEFAULT_QUIZ_MODEL=qwen2.5:1.5b
```

Le Model Manager détecte automatiquement le provider selon que `OLLAMA_BASE_URL` est défini.

### 5.6 Fallback automatique

```python
def get_llm_with_fallback(operation: str, **overrides):
    """Essaie le modèle demandé, fallback sur le suivant si échec."""
    primary = MODEL_MANAGER.get_llm(operation, **overrides)

    try:
        # Test rapide
        primary.invoke([HumanMessage(content="test")])
        return primary
    except Exception as e:
        # Log + fallback
        logger.warning(f"Model {primary} failed: {e}, fallback...")
        fallback_name = MODEL_MANAGER.fallback(primary.model_name)
        return MODEL_MANAGER.get_llm(operation, model_name=fallback_name)
```

### 5.7 Routes API

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/models` | Liste tous les modèles disponibles |
| `GET` | `/api/models/active` | Modèle actif par opération |
| `POST` | `/api/models/active` | Change le modèle actif `{operation, model_name}` |
| `POST` | `/api/models/refresh` | Rafraîchit le catalogue depuis Ollama |
| `GET` | `/api/models/{name}/config` | Détail config d'un modèle |

### 5.8 Frontend : Page Modèles

```tsx
// apps/web/app/models/page.tsx
export default function ModelsPage() {
    return (
        <div className="p-6 space-y-6">
            <h1>Gestion des Modèles</h1>

            {/* Modèles actifs par opération */}
            <ModelSelector operation="chat" />
            <ModelSelector operation="quiz_generation" />
            <ModelSelector operation="artifact" />

            {/* Catalogue complet */}
            <ModelCatalog>
                {models.map(m => (
                    <ModelCard
                        key={m.name}
                        model={m}
                        actions={[
                            <SetActiveButton operation="chat" model={m} />,
                            <TestButton model={m} />,
                        ]}
                    />
                ))}
            </ModelCatalog>
        </div>
    );
}
```

---

## 6. RAG sémantique avec double-check

### 6.1 Principe

L'agent passe par **trois vérifications** avant d'utiliser le RAG comme base de réponse. Cela évite les hallucinations quand aucun document pertinent n'est disponible ou quand le retrieval ramène des chunks hors-sujet.

### 6.2 Flux des trois vérifications

```
Question utilisateur
        │
        ▼
   ┌─────────────────────────────────────┐
   │ Check 1 : Document existe ?        │
   │   → Liste documents uploadés        │
   │   → Si vide : skip RAG + répondre   │
   │     "Aucun document importé"        │
   └──────────────┬──────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
    Aucun doc        Au moins 1 doc
         │                 │
         ▼                 ▼
   ┌──────────────┐   ┌─────────────────────────────────────┐
   │ rag_needed = │   │ Check 2 : Score chunks >= seuil ? │
   │ FALSE        │   │   → Retrieve top_k=3                │
   │ skip RAG     │   │   → Best score >= 0.3 ?            │
   └──────────────┘   └──────────────┬──────────────────────┘
                                     │
                            ┌────────┴────────┐
                            │                 │
                       Score < seuil    Score >= seuil
                            │                 │
                            ▼                 ▼
                    ┌──────────────┐   ┌────────────────────────┐
                    │ rag_needed = │   │ Check 3 : Contexte     │
                    │ FALSE        │   │ exploitable ? (LLM)    │
                    │ répondre     │   │   → LLM valide la      │
                    │ "Je n'ai pas │   │     pertinence         │
                    │  trouvé"     │   └──────────┬─────────────┘
                    └──────────────┘              │
                                         ┌────────┴────────┐
                                         │                 │
                                    Validé            Non pertinent
                                         │                 │
                                         ▼                 ▼
                                ┌──────────────┐   ┌──────────────────┐
                                │ Utiliser le  │   │ Répondre sans    │
                                │ contexte RAG │   │ RAG (scaffold    │
                                └──────────────┘   │ pur)             │
                                                     └──────────────────┘
```

### 6.3 Implémentation

**Check 1 — Existence de documents**

```python
# apps/api/agent/nodes/router.py
def router_profil_node(state, db_path):
    """Vérifie d'abord l'existence de documents."""
    documents = db.list_documents(db_path)
    has_documents = any(d.get("num_chunks", 0) > 0 for d in documents)

    if not has_documents and state.get("rag_needed"):
        return {
            "has_documents": False,
            "rag_needed": False,
            "method": "scaffold",
            "answer": "Je n'ai aucun document importé pour le moment. "
                      "Tu peux en uploader un via la page Documents.",
        }

    return {"has_documents": True, "rag_needed": ..., ...}
```

**Check 2 — Score de pertinence**

```python
# apps/api/rag/retriever.py
def retrieve_semantic(query: str, top_k: int = 3, threshold: float = 0.3):
    """Retrieval avec seuil."""
    docs_with_scores = vectorstore.similarity_search_with_score(query, k=top_k)
    if not docs_with_scores:
        return [], 0.0, False
    relevant = [(d, s) for d, s in docs_with_scores if s >= threshold]
    if not relevant:
        return [], docs_with_scores[0][1], False
    return [d for d, _ in relevant], max(s for _, s in docs_with_scores), True
```

**Check 3 — Validation LLM**

```python
# apps/api/agent/nodes/retrieval.py
RELEVANCE_CHECK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Tu es un verificateur de pertinence. On te donne une question
et des extraits de documents. Tu dois determiner si les extraits contiennent
reellement l'information demandee.

Question : {question}

Extraits :
{context}

Reponds par JSON STRICT :
{{
  "is_relevant": true | false,
  "confidence": 0.0-1.0,
  "reason": "courte explication"
}}"""),
])

def retrieval_node(state, llm_factory):
    question = state["question"]

    # Check 2
    docs, best_score, is_relevant_score = retrieve_semantic(question, top_k=3, threshold=0.3)

    if not docs:
        return {
            "context": "",
            "rag_relevant": False,
            "rag_confidence": 0.0,
            "rag_reason": "Aucun chunk au-dessus du seuil.",
        }

    # Check 3 — LLM validation
    context_text = format_docs(docs)
    llm = llm_factory(operation="relevance_check")  # modèle déterministe

    try:
        response = llm.invoke(RELEVANCE_CHECK_PROMPT.format_messages(
            question=question,
            context=context_text[:2000],
        ))
        check = json.loads(extract_json(response.content))

        if not check.get("is_relevant"):
            return {
                "context": "",
                "rag_relevant": False,
                "rag_confidence": check.get("confidence", 0.0),
                "rag_reason": check.get("reason", "Chunks non pertinents."),
            }

        return {
            "context": context_text,
            "rag_relevant": True,
            "rag_confidence": check.get("confidence", 0.0),
            "rag_reason": check.get("reason", ""),
        }
    except Exception as e:
        # Fallback : confiance sémantique seule
        return {
            "context": context_text if is_relevant_score else "",
            "rag_relevant": is_relevant_score,
            "rag_confidence": best_score,
            "rag_reason": f"Fallback sémantique ({best_score:.2f}).",
        }
```

### 6.4 Génération conditionnelle

```python
# apps/api/agent/nodes/generate.py
def generate_node(state, llm_factory):
    rag_relevant = state.get("rag_relevant", False)
    rag_confidence = state.get("rag_confidence", 0.0)

    if rag_relevant and rag_confidence >= 0.6:
        # Contexte fiable : prompt normal
        prompt = SCAFFOLD_PROMPT
    elif rag_relevant and rag_confidence < 0.6:
        # Contexte partiel : prompt prudent
        prompt = CAUTIOUS_PROMPT
    else:
        # Pas de contexte : message honnête
        return {
            "answer": "Je n'ai pas trouvé d'information pertinente dans tes "
                      "documents. Je peux répondre avec mes connaissances générales "
                      "ou tu peux uploader un document pertinent.",
            "method": "scaffold",
        }

    llm = llm_factory(operation="chat")
    return {"answer": llm.invoke(prompt.format_messages(...)).content}
```

### 6.5 Métriques RAG

| Métrique | But |
|---|---|
| Taux RAG ignorés (Check 1 KO) | Onboarding incomplet |
| Taux RAG rejetés (Check 2 KO) | Seuil bien calibré ? |
| Taux RAG rejetés LLM (Check 3 KO) | Retriever ramène du bruit |
| Confiance moyenne | Qualité retrieval |
| Latence double-check | Coût acceptable ? |

---

## 7. Human-in-the-Loop (HITL)

### 7.1 Les 3 niveaux d'action

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│   Niveau 1              Niveau 2              Niveau 3         │
│   🟢 AUTO               🟡 CONFIRM            🔴 BLOQUANT      │
│                                                                │
│   Lecture               Quiz                  Modification DB  │
│   Salutations           Feynman               critique         │
│   Explication           Artefact                               │
│   Résumé                 Génération long                       │
│   Reformulation         contenu                                │
│                                                                │
│   → direct              → demande             → interrupt     │
│                          Oui/Non               + validation    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 7.2 Cas concrets

| # | Action / Question | Niveau | HITL ? | Pourquoi |
|---|---|---|---|---|
| 1 | "Bonjour" | 🟢 | ❌ | Salutation |
| 2 | "Explique-moi les listes" | 🟢 | ❌ | Lecture |
| 3 | "Résume le document" | 🟢 | ❌ | Lecture |
| 4 | "Quel est le prix du Bitcoin ?" | 🟢 | ❌ | Web search |
| 5 | "Donne-moi un quiz" | 🟡 | ✅ | Coût LLM |
| 6 | "Fais-moi un quiz de 10 questions" | 🟡 | ✅ | Coût élevé |
| 7 | "Explique Feynman sur X" | 🟡 | ✅ | 2 tours LLM |
| 8 | "Crée un schéma" | 🟡 | ✅ | Génération artefact |
| 9 | "Crée un exercice" | 🟡 | ✅ | Idem |
| 10 | "Fais-moi une révision" | 🟢 | ❌ | Lecture Leitner |
| 11 | "Crée une nouvelle compétence" | 🟡 | ✅ | Modification DB |
| 12 | "Supprime cette compétence" | 🔴 | ✅✅ | Suppression DB |
| 13 | "Reset ma progression" | 🔴 | ✅✅ | Reset DB massif |

### 7.3 Flux détaillé — Cas "Donne-moi un quiz"

```
User: "Donne-moi un quiz sur les listes"
        │
        ▼
   Router → method = "quiz" → Retrieve (3 chunks) → Method = quiz
        │
        ▼
   confirmation_node → pending_confirmation = TRUE
        │
        ▼
   END (graph en pause)
        │
        ▼
   Frontend affiche : "Je vais te préparer un quiz. Tu es prêt(e) ?"
   [✅ Oui, c'est parti !]  [❌ Pas maintenant]
        │
   ┌────┴────┐
   │         │
 OUI       NON
   │         │
   ▼         ▼
   Re-invoke avec user_confirmed=TRUE
        │
        ▼
   tool_execution_node → generate_quiz → 3 questions JSON
        │
        ▼
   Frontend affiche QuizArtifact (React)
```

### 7.4 Implémentation

```python
# apps/api/agent/nodes/confirmation.py
CONFIRMATION_METHODS = {
    "quiz": {
        "prompt": "Je vais te préparer un quiz. Tu es prêt(e) ?",
        "icon": "📝",
        "cost": "low",
    },
    "feynman": {
        "prompt": "On va tester ta compréhension (méthode Feynman). C'est parti ?",
        "icon": "🎤",
        "cost": "medium",
    },
    "artifact": {
        "prompt": "Je vais créer un artefact pédagogique. On y va ?",
        "icon": "🎨",
        "cost": "medium",
    },
}

def confirmation_node(state):
    method = state["method"]
    user_confirmed = state.get("user_confirmed")

    if method not in CONFIRMATION_METHODS:
        return {}

    if user_confirmed is None:
        return {
            "pending_confirmation": True,
            "confirmation_type": method,
            "confirmation_prompt": CONFIRMATION_METHODS[method]["prompt"],
        }

    if user_confirmed is True:
        return {"pending_confirmation": False, "user_confirmed": None}

    if user_confirmed is False:
        return {
            "pending_confirmation": False,
            "user_confirmed": None,
            "method": "scaffold",
            "answer": "Pas de souci ! Pose-moi une autre question.",
        }
```

```tsx
// apps/web/components/chat/ConfirmationButtons.tsx
export function ConfirmationButtons({ prompt, type, onConfirm, onCancel }) {
  const icons = { quiz: "📝", feynman: "🎤", artifact: "🎨" };
  return (
    <motion.div className="my-3 p-4 bg-blue-500/10 border border-blue-500/30 rounded-xl">
      <div className="flex items-start gap-3">
        <span className="text-2xl">{icons[type]}</span>
        <div className="flex-1">
          <p className="text-zinc-200 text-sm">{prompt}</p>
          <div className="flex gap-2 mt-3">
            <button onClick={onConfirm} className="px-4 py-2 bg-blue-600 ...">
              ✓ Oui, c'est parti
            </button>
            <button onClick={onCancel} className="px-4 py-2 bg-zinc-700 ...">
              ✗ Pas maintenant
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
```

---

## 8. Transparence des outils utilisés

### 8.1 Principe

Chaque réponse affiche **quels outils** ont été utilisés pour la produire, avec leur coût et leur durée. L'utilisateur voit la "recette" interne de l'agent.

### 8.2 Affichage

**Badge flottant au-dessus de la réponse**

```
┌──────────────────────────────────────────────────┐
│ 🧠 Tuteur IA                                      │
│                                                  │
│ ┌──────────────────────────────────────────────┐ │
│ │ 🔧 Outils utilisés (3) — 1.2s — 450 tokens │ │
│ │   📚 RAG (3 chunks, score 0.82)             │ │
│ │   🌐 Web search (Bitcoin, prix)              │ │
│ │   🎓 Méthode : Socratique                    │ │
│ └──────────────────────────────────────────────┘ │
│                                                  │
│ Le Bitcoin s'échange actuellement à environ      │
│ 45 000 USD, en hausse de 3% sur 24h...          │
└──────────────────────────────────────────────────┘
```

**Détail expand**

```
┌──────────────────────────────────────────────────┐
│ 🔧 Outils utilisés (3) — 1.2s — 450 tokens       │
│                                                  │
│   📚 RAG retrieval                               │
│      3 chunks depuis "cours_python.pdf"          │
│      Score max : 0.82                            │
│      Durée : 120ms                               │
│                                                  │
│   🌐 Web search                                  │
│      Query : "prix Bitcoin aujourd'hui"          │
│      Sources : coindesk.com, coinbase.com        │
│      Durée : 380ms                               │
│                                                  │
│   🎓 Méthode pédagogique                         │
│      Socratique (niveau intermédiaire)            │
│      Durée : 700ms                               │
└──────────────────────────────────────────────────┘
```

### 8.3 Implémentation backend

Chaque tool enregistre son usage dans `tool_usage` table :

```python
# apps/api/agent/nodes/tool.py
def tool_execution_node(state, model_manager):
    tool = state["method"]
    start = time.time()

    if tool == "quiz":
        result_str = generate_quiz.invoke(...)
        result = json.loads(result_str)
        duration = (time.time() - start) * 1000

        # Log l'usage
        db.log_tool_usage(
            message_id=state.get("message_id"),
            tool_name="generate_quiz",
            tool_input={"competency": state.get("active_competency")},
            tool_output={"num_questions": len(result)},
            execution_time_ms=duration,
            cost_estimate=duration * 0.0001,  # estimation
        )

        return {"quiz_questions": result, ...}
    # ...
```

### 8.4 SSE event "tool_used"

```typescript
type StreamEvent =
  | { event: "token"; data: { text: string } }
  | { event: "tool_used"; data: { tool: string; duration_ms: number; details: any } }
  | { event: "pending_confirmation"; data: { prompt: string; type: string } }
  | { event: "artifact"; data: { type: string; content: any } }
  | { event: "done"; data: { session_id: number; tools_used: ToolUsage[] } };
```

```tsx
// apps/web/components/chat/ToolBadge.tsx
export function ToolBadge({ tools }: { tools: ToolUsage[] }) {
  const [expanded, setExpanded] = useState(false);
  const totalDuration = tools.reduce((s, t) => s + t.duration_ms, 0);

  return (
    <div className="my-2 p-2 bg-zinc-900/50 border border-zinc-800 rounded-lg">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs text-zinc-400"
      >
        🔧 {tools.length} outil{tools.length > 1 ? 's' : ''}
        <span>· {totalDuration}ms</span>
        {expanded ? <ChevronUp /> : <ChevronDown />}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div className="mt-2 space-y-2">
            {tools.map(t => (
              <ToolUsageDetail key={t.tool} usage={t} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

---

## 9. Web search améliorée

### 9.1 Améliorations par rapport à V2

| Aspect | V2 | V3 |
|---|---|---|
| Provider | DDGS seul | DDGS + Tavily + Brave (configurable) |
| Cache | Aucun | Cache 24h dans `web_search_cache` |
| Sources citées | Non | Oui, chaque source cliquable |
| Routage | Patterns regex | Patterns + classification LLM |
| Déclenchement | Sur patterns | + sur "selon le web", "actuellement" |
| Résumé | Brut (titres+snippets) | Résumé LLM des sources + citation |

### 9.2 Configuration multi-provider

```python
# apps/api/services/web_search_service.py
SEARCH_PROVIDERS = {
    "ddgs": {"cost_per_query": 0.0, "speed": "fast", "quality": "good"},
    "tavily": {"cost_per_query": 0.005, "speed": "fast", "quality": "excellent"},
    "brave": {"cost_per_query": 0.003, "speed": "fast", "quality": "good"},
}

class WebSearchService:
    def __init__(self, config):
        self.providers = {
            "ddgs": DDGSProvider(),
            "tavily": TavilyProvider(api_key=config.TAVILY_API_KEY),
            "brave": BraveProvider(api_key=config.BRAVE_API_KEY),
        }
        self.default_provider = "ddgs"

    async def search(self, query: str, num_results: int = 5) -> SearchResult:
        # Check cache
        cached = self._check_cache(query)
        if cached:
            return cached

        # Router vers le provider actif
        provider = self.providers[self.default_provider]
        results = await provider.search(query, num_results)

        # Cache
        self._save_cache(query, results)

        return results
```

### 9.3 Routage amélioré

Au lieu de simples patterns regex, on ajoute une classification LLM en cas d'ambiguïté :

```python
# apps/api/agent/nodes/method.py
WEB_SEARCH_CLASSIFIER = ChatPromptTemplate.from_messages([
    ("system", """Determine si la question necessite une recherche web actualisee.

Question : {question}

Reponds JSON :
{{
  "needs_web": true | false,
  "reason": "explication courte"
}}

Exemples :
- "C'est quoi Python ?" → false (definition stable)
- "Prix du Bitcoin ?" → true (change)
- "Dernieres news sur l'IA ?" → true (actualite)
- "Comment marche une liste ?" → false (concept stable)"""),
])
```

### 9.4 Format de réponse enrichi

```markdown
🌐 **Recherche web** (3 résultats)

**1. [Bitcoin Price Today](https://coindesk.com/price/bitcoin)**
   Le Bitcoin s'échange à $45,234 (+3.2% 24h)...

**2. [Bitcoin USD Price](https://coinbase.com/price/bitcoin)**
   Current price: $45,189. Market cap: $880B...

**3. [BTC Live Chart](https://tradingview.com/symbols/BTCUSD/)**
   Real-time BTC/USD chart with technical analysis...

📌 _Source la plus fiable : CoinDesk (actualisé il y a 5 min)_
```

---

## 10. Profil enrichi — Contexte d'apprentissage

### 10.1 Nouveaux champs

```sql
-- Sur learner_profile
ALTER TABLE learner_profile ADD COLUMN learning_context TEXT DEFAULT '';
ALTER TABLE learner_profile ADD COLUMN goals TEXT DEFAULT '';

-- Sur mastery
ALTER TABLE mastery ADD COLUMN stable_since DATETIME;
ALTER TABLE mastery ADD COLUMN practice_count INTEGER DEFAULT 0;
```

**`learning_context`** : texte libre décrivant ce que l'utilisateur apprend, ses objectifs, son parcours.

Exemple : "Je suis en reconversion vers le développement web. J'ai 10 ans d'expérience en marketing digital. J'apprends Python pour automatiser mes tâches et créer des dashboards."

**`goals`** : objectifs d'apprentissage.

Exemple : "Maîtriser les bases Python en 3 mois, puis Django pour un projet personnel."

### 10.2 Profil enrichi dans l'AgentState

```python
class AgentState(TypedDict):
    # ... existants ...

    # Profil enrichi
    learning_context: str              # Contexte d'apprentissage (texte libre)
    goals: str                       # Objectifs

    # Ce que l'user sait/maîtrise déjà
    mastered_competencies: list[dict]  # score >= 0.7 ET stable_since > 7j
    learning_competencies: list[dict]  # 0.4 <= score < 0.7
    gaps: list[dict]                   # score < 0.4 OU en retard Leitner
    recent_topics: list[str]           # 5 derniers sujets abordés
    average_score: float
```

### 10.3 Chargement du profil dans le router

```python
# apps/api/agent/nodes/router.py
def router_profil_node(state, db_path):
    profile = db.get_profile(db_path)
    domain = profile.get("domain", "")

    # Compétences maîtrisées vs en apprentissage vs lacunes
    mastery_overview = db.get_mastery_overview(domain, db_path)
    mastered = [c for c in mastery_overview if c["score"] >= 0.7 and c["stable_since"]]
    learning = [c for c in mastery_overview if 0.4 <= c["score"] < 0.7]
    gaps = [c for c in mastery_overview if c["score"] < 0.4 or _is_overdue(c)]

    # Topics récents (depuis messages)
    recent = db.get_recent_topics(db_path, limit=5)

    return {
        "learner_profile": profile,
        "learning_context": profile.get("learning_context", ""),
        "goals": profile.get("goals", ""),
        "mastered_competencies": mastered,
        "learning_competencies": learning,
        "gaps": gaps,
        "recent_topics": recent,
        "active_competency": state.get("active_competency"),
        "has_documents": _check_documents(db_path),
        "method": "diagnostic" if not domain else "scaffold",
        "rag_needed": ...,
    }
```

### 10.4 Utilisation dans la génération

```python
# apps/api/agent/nodes/generate.py
def generate_node(state, llm_factory):
    profile = state.get("learner_profile", {})
    context = state.get("learning_context", "")
    mastered = state.get("mastered_competencies", [])
    learning = state.get("learning_competencies", [])
    gaps = state.get("gaps", [])

    system_prompt = f"""Tu es un tuteur pour {profile.get('domain', 'un domaine')}.

Contexte apprenant : {context or 'Non specifie'}
Objectifs : {profile.get('goals') or 'Non specifie'}

Competences MAITRISEES (ne pas re-expliquer les bases) :
{[c['nom'] for c in mastered]}

Competences en cours d'apprentissage (approfondir) :
{[c['nom'] for c in learning]}

LACUNES identifiees (prioriser) :
{[c['nom'] for c in gaps]}
"""
```

---

## 11. Méthodes auto-activées

### 11.1 Principe

L'agent **choisit automatiquement** la méthode appropriée selon le contexte, sans que l'utilisateur ait à la demander explicitement.

### 11.2 Quand chaque méthode s'active

| Méthode | Se déclenche quand | Exemple de question | Pourquoi |
|---|---|---|---|
| **Scaffold** | Compétence < 0.4 (nouveau sujet) | "Explique-moi les décorateurs" | Pas à pas pour nouveau |
| **Socratique** | Compétence 0.4-0.7 (en cours) | "Je bloque sur les boucles" | Questions guidées |
| **Feynman** | Compétence > 0.7 (avancé) OU user dit "explique-moi X comme à un enfant" | "Explique-moi la récursion comme si j'avais 12 ans" | Vérifier compréhension |
| **Quiz** | Compétence >= 0.5 ET user dit "teste-moi" OU après 3 échanges sur le sujet | "Donne-moi un quiz" ou auto-déclenché | Consolidation |
| **Diagnostic** | Pas de profil OU nouveau sujet | Premier message sans domaine | Calibration |
| **Revision** | User dit "réviser/rappel" OU Leitner overdue | "Que dois-je réviser ?" | Répétition espacée |
| **Web search** | Question actuelle/prix/news | "Prix du Bitcoin ?" | Information externe |
| **Artifact** | User dit "schéma/exercice/cours/carte" | "Crée un schéma de la photosynthèse" | Support visuel |
| **Explication simple** | Phrase "comme si j'avais X ans" | "Explique comme à un enfant" | Vulgarisation |

### 11.3 Auto-déclenchement après N échanges

```python
# apps/api/agent/nodes/method.py
def auto_trigger_quiz(state, db_path):
    """Déclenche automatiquement un quiz après 3 échanges sur un sujet."""
    competency = state.get("active_competency")
    if not competency:
        return False

    # Compter les messages sur cette compétence dans la session
    msg_count = db.count_messages_on_competency(
        db_path, state.get("session_id"), competency
    )

    # Déclenche si >= 3 messages et pas encore eu de quiz
    if msg_count >= 3 and not db.had_quiz_on_competency(db_path, competency):
        return True
    return False


def method_selection_node(state, db_path):
    profile = state.get("learner_profile", {})
    level = profile.get("niveau_global", "")
    mastery = _get_mastery_for_active_competency(state, db_path)

    # Auto-déclenchements
    if auto_trigger_quiz(state, db_path):
        return {"method": "quiz"}
    if _needs_revision(state["question"]):
        return {"method": "revision"}
    if _needs_web_search(state["question"]):
        return {"method": "web_search"}

    # Déclenchement basé sur le niveau
    if mastery is None or mastery["score"] < 0.4:
        return {"method": "scaffold"}
    elif 0.4 <= mastery["score"] < 0.7:
        return {"method": "socratic"}
    elif mastery["score"] >= 0.7:
        return {"method": "feynman"}

    return {"method": "scaffold"}
```

### 11.4 Séquence pédagogique naturelle

```
┌─────────────────────────────────────────────────────────────────┐
│ User ouvre une session sur "Python"                              │
│   → diagnostic (3 questions calibrées) → mastery score estimé   │
│                                                                  │
│ User : "C'est quoi une liste ?"                                  │
│   → mastery faible → SCAFFOLD (définition simple + analogie)    │
│                                                                  │
│ User : "Et comment on en fait une ?"                             │
│   → mastery < 0.5 → SCAFFOLD (exemple détaillé)                 │
│                                                                  │
│ User : "Et slicing ?"                                            │
│   → mastery ~0.5 → SOCRATIQUE (questions guidées)              │
│                                                                  │
│ [Après 3 échanges sur "Listes"]                                  │
│   → AUTO-DECLENCHEMENT : "Veux-tu un quiz ?" → HITL → QUIZ     │
│                                                                  │
│ User : "Donne-moi un autre exemple"                              │
│   → mastery 0.6 → SOCRATIQUE                                    │
│                                                                  │
│ User : "Explique comme à un enfant"                              │
│   → FEYNMAN (évaluation restitution)                             │
│                                                                  │
│ User : "Que dois-je réviser ?"                                   │
│   → REVISION (plan Leitner)                                     │
│                                                                  │
│ User : "Crée un schéma"                                          │
│   → ARTIFACT (HITL puis génération)                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 12. API Contract (FastAPI)

### 12.1 Endpoints principaux

| Méthode | Route | Body | Réponse |
|---|---|---|---|
| `POST` | `/api/chat` | `{question, session_id}` | `{message_id, pending_confirmation?}` |
| `GET` | `/api/chat/stream/{message_id}` | (SSE) | `event: token/tool_used/...` |
| `POST` | `/api/chat/confirm` | `{message_id, accepted: bool}` | `{answer, method, artifact?, tools_used}` |
| `GET` | `/api/sessions` | — | `[{id, title, started_at, message_count}]` |
| `POST` | `/api/sessions` | `{title?}` | `{id, thread_id}` |
| `DELETE` | `/api/sessions/{id}` | — | `204` |
| `GET` | `/api/sessions/{id}/messages` | — | `[{role, content, method, tools_used}]` |
| `POST` | `/api/documents/upload` | `multipart/form-data` | `{id, num_chunks}` |
| `GET` | `/api/documents` | — | `[{id, filename, num_chunks}]` |
| `DELETE` | `/api/documents/{id}` | — | `204` |
| `GET` | `/api/profile` | — | `{domain, niveau_global, learning_context, goals, mastered, learning, gaps}` |
| `PUT` | `/api/profile` | `{domain, niveau_global, learning_context, goals}` | `204` |
| `POST` | `/api/competencies` | `{nom, parent_id?, description?}` | `{id}` |
| `DELETE` | `/api/competencies/{id}` | — | `204` |
| `GET` | `/api/progress/summary` | — | `{total, average_score, mastered, gaps, due_for_review}` |
| `GET` | `/api/progress/revision-plan` | — | `{plan: [...]}` |
| `GET` | `/api/models` | — | `[{name, display, provider, format_mode}]` |
| `POST` | `/api/models/active` | `{operation, model_name}` | `204` |
| `POST` | `/api/models/refresh` | — | `{added: int, removed: int}` |

### 12.2 Format SSE

```
event: token
data: {"text": "Bonjour", "method": "scaffold"}

event: tool_used
data: {"tool": "rag_retrieval", "duration_ms": 120, "details": {"chunks": 3, "score": 0.82}}

event: tool_used
data: {"tool": "web_search", "duration_ms": 380, "details": {"query": "...", "sources": ["..."]}}

event: pending_confirmation
data: {"prompt": "Tu veux un quiz ?", "type": "quiz"}

event: artifact
data: {"type": "quiz", "title": "...", "content": [...]}

event: done
data: {"session_id": 42, "message_id": 123, "tools_used": [...]}
```

---

## 13. Artefacts — 4 types

### 13.1 Schema (Mermaid)
- Graphe Mermaid en Markdown
- Rendu via `react-mermaid` ou `<pre class="mermaid">`
- Nœuds cliquables, zoom

### 13.2 Quiz (React state)
États : non répondu → répondu → terminé. Barre de progression, score final, mise à jour Leitner.

### 13.3 Code (Monaco Editor)
- Coloration syntaxique
- Lang auto-détectée
- Boutons copier/modifier/tester

### 13.4 Chart (Recharts)
- Données JSON
- Type : bar, line, pie
- Interactif

---

## 14. Phases d'implémentation

| Phase | Durée | Contenu |
|---|---|---|
| **0 — Setup** | 1 j | Répertoires, Next.js 14, FastAPI, deps |
| **1 — Backend FastAPI** | 3 j | Routes de base, `/api/chat` sans SSE |
| **2 — RAG sémantique + double-check** | 2 j | `retrieve_semantic` + LLM validation |
| **3 — Model Manager** | 2 j | Catalogue, format control, fallback |
| **4 — Profil enrichi** | 1 j | learning_context, mastered/gaps, auto-trigger |
| **5 — Web search améliorée** | 1 j | Multi-provider, cache, sources citées |
| **6 — SSE + streaming** | 1 j | Token-by-token + tool_used events |
| **7 — Frontend chat** | 2 j | ChatWindow, StreamingText, ConfirmationButtons |
| **8 — Artefacts React** | 2 j | 4 types avec Framer Motion |
| **9 — Transparence outils** | 1 j | ToolBadge + SSE events |
| **10 — Pages annexes** | 2 j | Dashboard, Documents, Profile, Modèles |
| **11 — Polish** | 2 j | Dark mode, animations, error boundaries |

**Total** : ~20 jours ouvrés (4 semaines).

---

## 15. Risques identifiés

| Risque | Mitigation |
|---|---|
| SSE bloqué par certains proxys | Fallback polling ou WebSocket |
| Monaco Editor lourd (~5 MB) | Lazy load |
| Ollama Cloud latency (3-30s) | Streaming + skeleton UI |
| Migration DB V2 → V3 | Script additif, pas de DROP |
| Perte fonctionnalités V2 | Tests exhaustifs sur chaque feature |
| RAG embedding local pendant que LLM est cloud | Garder séparation embedding/LLM |
| Double-check LLM coûteux | Désactivable via env var |
| Fallback model trop fréquent | Monitoring + alertes |
| Web search quota épuisé | Cache 24h + multi-provider |

---

## 16. Critères d'acceptation

- [ ] Frontend Next.js démarre sur `:3000`, backend sur `:8000`
- [ ] Conversation complète : upload PDF → chat → quiz → Feynman → revision
- [ ] 4 types d'artefacts rendent correctement
- [ ] Streaming affiche tokens au fur et à mesure
- [ ] HITL fonctionne : bouton quiz → confirmation → execution
- [ ] RAG double-check : 3 vérifications avant utilisation
- [ ] User voit badges des outils utilisés sur chaque réponse
- [ ] Modèles Ollama Cloud fonctionnels avec fallback local
- [ ] Profil enrichi : mastered/learning/gaps affichés
- [ ] Méthodes auto-activées selon contexte
- [ ] Web search avec sources citées
- [ ] DB V2 reste compatible
- [ ] Tests e2e V2 passent toujours

---

## 17. Estimation

**Total** : ~20 jours ouvrés (4 semaines).

---

## 18. Prochaines étapes

1. Valider ce plan
2. Phase 0 : structure + dépendances
3. Phase 1 : backend FastAPI minimal
4. Itérations : tests e2e à chaque phase
5. Livraison incrémentale