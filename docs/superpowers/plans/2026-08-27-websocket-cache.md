# WebSocket temps réel + Cache — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un canal WebSocket bidirectionnel (streaming réel, HITL, notifications) relié aux sessions et aux threads LangGraph, plus une gestion de cache serveur pour réduire la latence.

**Architecture:** Endpoint FastAPI `/ws/{session_id}` — la connexion est liée à la session DB, qui est liée au thread LangGraph (`session.thread_id`). Un `ConnectionManager` en mémoire gère les connexions ; l'agent tourne dans un thread et pousse ses tokens via une file asyncio (pont `call_soon_threadsafe`). Caches mémoire TTL+LRU (`cachetools`) pour profil/compétences/RAG, avec invalidation explicite après écriture.

**Tech Stack:** FastAPI WebSocket, asyncio, cachetools, LangGraph (`graph.stream`, `Command(resume)`), Next.js (WebSocket natif navigateur).

**Spec :** `docs/superpowers/specs/2026-08-27-websocket-cache-design.md`

**Environnement de dev (Windows/PowerShell) :**
- Tests : `.\venv\Scripts\python.exe -m pytest tests/ -q`
- Installer une dépendance : `.\venv\Scripts\python.exe -m pip install <pkg>` puis l'ajouter à `apps/api/requirements.txt`
- Deploy backend : `$env:Path = "C:\Users\hp\.fly\bin;" + $env:Path; flyctl deploy --remote-only`
- Deploy frontend : `git push origin main` (auto-deploy Vercel) puis vérifier avec `vercel ls` depuis `apps/web`

---

## Structure des fichiers

**Créés :**
- `apps/api/services/cache.py` — caches mémoire TTL+LRU + helpers d'invalidation
- `apps/api/ws/__init__.py` — package WebSocket
- `apps/api/ws/manager.py` — ConnectionManager (registre session_id → websocket, busy flag)
- `apps/api/ws/protocol.py` — constructeurs de messages du protocole
- `apps/api/ws/router.py` — endpoint `/ws/{session_id}` + handlers chat/confirm/quiz + notifications
- `apps/web/lib/websocket.ts` — client WS avec reconnexion backoff + fallback
- `tests/test_cache.py`, `tests/test_ws.py`

**Modifiés :**
- `apps/api/requirements.txt` — ajouter `cachetools`
- `apps/api/db/crud.py` — cache dans `get_profile`/`get_competencies`, invalidation dans `update_profile`/`create_competency`
- `apps/api/agent/nodes.py` — cache RAG dans `retrieval_node`
- `apps/api/services/agent_service.py` — `run_agent_streaming` : détection d'interrupt, metadata complètes, support `resume_value`
- `apps/api/main.py` — enregistrer le router WS
- `apps/web/components/chat/ChatWindow.tsx` — streaming réel via socket, confirmations via socket, fallback HTTP

**Liaison session ↔ thread ↔ WebSocket (exigence utilisateur) :**
```
WebSocket /ws/{session_id}
   → crud.get_session(session_id)          # valide la session DB
   → get_thread_id_from_session(session_id) # résout/crée le thread LangGraph
   → toute la conversation WS utilise ce thread (continuité checkpointer)
   → les messages sont sauvés dans la session (crud.add_message)
```

---

## Task 1: Module de cache serveur

**Files:**
- Create: `apps/api/services/cache.py`
- Modify: `apps/api/requirements.txt`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Installer cachetools et l'ajouter aux requirements**

```powershell
.\venv\Scripts\python.exe -m pip install cachetools
```

Ajouter dans `apps/api/requirements.txt` (section Utilitaires) :
```
cachetools>=5.3.0
```

- [ ] **Step 2: Écrire les tests du cache (échec attendu)**

`tests/test_cache.py` :
```python
import time
import pytest
from apps.api.services import cache


def test_get_set():
    cache.clear_all()
    assert cache.cache_get(cache.profile_cache, "u1") is None
    cache.cache_set(cache.profile_cache, "u1", {"domain": "maths"})
    assert cache.cache_get(cache.profile_cache, "u1") == {"domain": "maths"}


def test_ttl_expire():
    cache.clear_all()
    cache.cache_set(cache.profile_cache, "u2", "v")
    time.sleep(cache.PROFILE_TTL + 0.2)
    assert cache.cache_get(cache.profile_cache, "u2") is None


def test_invalidate_profile():
    cache.clear_all()
    cache.cache_set(cache.profile_cache, "u3", "v")
    cache.invalidate_profile("u3")
    assert cache.cache_get(cache.profile_cache, "u3") is None


def test_invalidate_competencies():
    cache.clear_all()
    cache.cache_set(cache.competency_cache, "maths", [1, 2])
    cache.cache_set(cache.competency_cache, "physique", [3])
    cache.invalidate_competencies("maths")
    assert cache.cache_get(cache.competency_cache, "maths") is None
    assert cache.cache_get(cache.competency_cache, "physique") == [3]
    cache.invalidate_competencies()  # tout
    assert cache.cache_get(cache.competency_cache, "physique") is None


def test_rag_cache_key_stable():
    k1 = cache.rag_key("quelle question ?", 3)
    k2 = cache.rag_key("quelle question ?", 3)
    k3 = cache.rag_key("autre question", 3)
    assert k1 == k2 and k1 != k3
```

- [ ] **Step 3: Vérifier l'échec**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_cache.py -v`
Expected: FAIL (module `apps.api.services.cache` introuvable)

- [ ] **Step 4: Implémenter le module**

`apps/api/services/cache.py` :
```python
"""Caches memoire TTL+LRU (cachetools) avec invalidation explicite.

Bornes strictes pour la machine Fly 512 Mo : maxsize limites, LRU evince
automatiquement. Pas de cache des reponses LLM (volontaire, voir spec).
"""
import hashlib
import threading

from cachetools import TTLCache

PROFILE_TTL = 30        # secondes
COMPETENCY_TTL = 30
RAG_TTL = 600           # 10 minutes

_lock = threading.Lock()
profile_cache: TTLCache = TTLCache(maxsize=64, ttl=PROFILE_TTL)
competency_cache: TTLCache = TTLCache(maxsize=64, ttl=COMPETENCY_TTL)
rag_cache: TTLCache = TTLCache(maxsize=128, ttl=RAG_TTL)


def cache_get(cache: TTLCache, key: str):
    with _lock:
        return cache.get(key)


def cache_set(cache: TTLCache, key: str, value) -> None:
    with _lock:
        cache[key] = value


def invalidate_profile(user_id: str) -> None:
    with _lock:
        profile_cache.pop(user_id, None)


def invalidate_competencies(domain: str = None) -> None:
    with _lock:
        if domain is None:
            competency_cache.clear()
        else:
            competency_cache.pop(domain, None)


def rag_key(question: str, top_k: int) -> str:
    raw = f"{question.strip().lower()}|{top_k}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def clear_all() -> None:
    with _lock:
        profile_cache.clear()
        competency_cache.clear()
        rag_cache.clear()
```

- [ ] **Step 5: Vérifier le succès**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_cache.py -v`
Expected: 5 PASSED

- [ ] **Step 6: Commit**

```powershell
git add apps/api/services/cache.py apps/api/requirements.txt tests/test_cache.py
git commit -m "feat: module de cache memoire TTL+LRU (cachetools)"
```

---

## Task 2: Intégration du cache dans crud (profil + compétences)

**Files:**
- Modify: `apps/api/db/crud.py` (fonctions `get_profile`, `update_profile`, `get_competencies`, `create_competency`)
- Test: `tests/test_cache.py` (ajouts)

- [ ] **Step 1: Écrire les tests d'intégration (échec attendu)**

Ajouter dans `tests/test_cache.py` :
```python
from apps.api.db import crud


def test_profile_cached_and_invalidated(tmp_db):
    cache.clear_all()
    p1 = crud.get_profile(user_id="cache_user", db_path=tmp_db)
    p2 = crud.get_profile(user_id="cache_user", db_path=tmp_db)
    assert p1 == p2
    # 2e appel vient du cache : meme objet en memoire
    assert cache.cache_get(cache.profile_cache, f"cache_user|{tmp_db}") is not None
    # ecriture → invalidation
    crud.update_profile(niveau_global="avance", user_id="cache_user", db_path=tmp_db)
    assert cache.cache_get(cache.profile_cache, f"cache_user|{tmp_db}") is None
    p3 = crud.get_profile(user_id="cache_user", db_path=tmp_db)
    assert p3.get("niveau_global") == "avance"


def test_competencies_cached_and_invalidated(tmp_db):
    cache.clear_all()
    c1 = crud.get_competencies("maths", db_path=tmp_db)
    assert cache.cache_get(cache.competency_cache, f"maths|{tmp_db}") is not None
    crud.create_competency("maths", "Fractions", db_path=tmp_db)
    assert cache.cache_get(cache.competency_cache, f"maths|{tmp_db}") is None
    c2 = crud.get_competencies("maths", db_path=tmp_db)
    assert any(c["nom"] == "Fractions" for c in c2)
```

- [ ] **Step 2: Vérifier l'échec**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_cache.py -v`
Expected: FAIL sur les 2 nouveaux tests (cache non utilisé par crud)

- [ ] **Step 3: Modifier crud.py**

Dans `apps/api/db/crud.py`, ajouter en haut : `from apps.api.services import cache`.

`get_profile` — vérifier le cache avant la DB, remplir après :
```python
def get_profile(user_id: str = "default_user", db_path: Optional[Path] = None) -> dict:
    key = f"{user_id}|{db_path}"
    cached = cache.cache_get(cache.profile_cache, key)
    if cached is not None:
        return cached
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM learner_profile WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            result = dict(row)
        else:
            conn.execute(
                "INSERT INTO learner_profile (user_id, domain, niveau_global) "
                "VALUES (?, '', '')",
                (user_id,),
            )
            row = conn.execute(
                "SELECT * FROM learner_profile WHERE user_id = ?", (user_id,)
            ).fetchone()
            result = dict(row) if row else {}
    cache.cache_set(cache.profile_cache, key, result)
    return result
```

`update_profile` — invalider à la fin de la fonction (après le `with`) :
```python
    cache.invalidate_profile(user_id)
```

`get_competencies(domain, db_path=None)` — même pattern avec `cache.competency_cache` et la clé `f"{domain}|{db_path}"`.

`create_competency(domain, nom, ...)` — invalider à la fin :
```python
    cache.invalidate_competencies(domain)
```

- [ ] **Step 4: Vérifier le succès**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_cache.py tests/ -q`
Expected: tous PASSED (y compris les 29 tests existants)

- [ ] **Step 5: Commit**

```powershell
git add apps/api/db/crud.py tests/test_cache.py
git commit -m "feat: cache profil+competences dans crud avec invalidation"
```

---

## Task 3: Cache RAG dans retrieval_node

**Files:**
- Modify: `apps/api/agent/nodes.py` (`retrieval_node`, ligne ~278)
- Test: `tests/test_cache.py` (ajouts)

- [ ] **Step 1: Écrire le test (échec attendu)**

Ajouter dans `tests/test_cache.py` :
```python
def test_rag_cache_hit():
    from apps.api.agent import nodes

    calls = {"n": 0}

    class FakeRetriever:
        def invoke(self, q):
            calls["n"] += 1
            return []

    cache.clear_all()
    state = {
        "question": "qu'est-ce qu'une fraction ?",
        "rag_needed": True,
        "tool_transparency": [],
    }
    nodes.retrieval_node(state, FakeRetriever())
    nodes.retrieval_node(state, FakeRetriever())
    assert calls["n"] == 1  # 2e appel servi depuis le cache
```

- [ ] **Step 2: Vérifier l'échec**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_cache.py::test_rag_cache_hit -v`
Expected: FAIL (`calls["n"] == 2`)

- [ ] **Step 3: Modifier retrieval_node**

Dans `apps/api/agent/nodes.py`, ajouter en haut : `from apps.api.services import cache`.

Dans `retrieval_node`, avant l'appel au retriever (ligne ~294) :
```python
    question = state.get("question", "")
    rk = cache.rag_key(question, top_k)
    cached_docs = cache.cache_get(cache.rag_cache, rk)
    if cached_docs is not None:
        docs = cached_docs
    else:
        docs = _retrieve_docs(retriever, question, top_k=top_k, threshold=threshold)
        cache.cache_set(cache.rag_cache, rk, docs)
```
(Adapter au code exact de `retrieval_node` : l'appel existant au retriever devient la branche `else` ; conserver la logique de tracking d'outil `_track_tool` autour de l'appel réel uniquement.)

- [ ] **Step 4: Vérifier le succès**

Run: `.\venv\Scripts\python.exe -m pytest tests/ -q`
Expected: tous PASSED

- [ ] **Step 5: Commit**

```powershell
git add apps/api/agent/nodes.py tests/test_cache.py
git commit -m "feat: cache du retrieval RAG (TTL 10 min)"
```

---

## Task 4: Protocole WebSocket

**Files:**
- Create: `apps/api/ws/__init__.py` (vide)
- Create: `apps/api/ws/protocol.py`
- Test: `tests/test_ws.py`

- [ ] **Step 1: Écrire le test (échec attendu)**

`tests/test_ws.py` :
```python
def test_protocol_builders():
    from apps.api.ws import protocol as p
    assert p.token_msg("bon") == {"type": "token", "text": "bon"}
    assert p.pong_msg() == {"type": "pong"}
    err = p.error_msg("agent_busy")
    assert err == {"type": "error", "message": "agent_busy"}
    conf = p.confirmation_request_msg("competency_creation", "Veux-tu créer X ?")
    assert conf["type"] == "confirmation_request"
    assert conf["confirmation_type"] == "competency_creation"
    assert conf["confirmation_prompt"] == "Veux-tu créer X ?"
    notif = p.notification_msg("revision_due", {"count": 3})
    assert notif == {"type": "notification", "kind": "revision_due", "data": {"count": 3}}
    msg = p.final_message_msg({
        "answer": "réponse", "method": "scaffold", "thread_id": "t1",
        "artifacts": [], "tool_transparency": [],
    })
    assert msg["type"] == "message"
    assert msg["answer"] == "réponse"
```

- [ ] **Step 2: Vérifier l'échec**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_ws.py -v`
Expected: FAIL (module introuvable)

- [ ] **Step 3: Implémenter**

`apps/api/ws/__init__.py` : fichier vide.

`apps/api/ws/protocol.py` :
```python
"""Constructeurs de messages du protocole WebSocket (spec §3.2)."""


def token_msg(text: str) -> dict:
    return {"type": "token", "text": text}


def final_message_msg(result: dict) -> dict:
    return {
        "type": "message",
        "answer": result.get("answer", ""),
        "method": result.get("method"),
        "thread_id": result.get("thread_id"),
        "artifacts": result.get("artifacts", []),
        "tool_transparency": result.get("tool_transparency", []),
    }


def confirmation_request_msg(confirmation_type, prompt) -> dict:
    return {
        "type": "confirmation_request",
        "confirmation_type": confirmation_type,
        "confirmation_prompt": prompt,
    }


def notification_msg(kind: str, data: dict) -> dict:
    return {"type": "notification", "kind": kind, "data": data}


def error_msg(message: str) -> dict:
    return {"type": "error", "message": message}


def pong_msg() -> dict:
    return {"type": "pong"}
```

- [ ] **Step 4: Vérifier le succès**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_ws.py -v`
Expected: PASSED

- [ ] **Step 5: Commit**

```powershell
git add apps/api/ws/__init__.py apps/api/ws/protocol.py tests/test_ws.py
git commit -m "feat: protocole WebSocket (constructeurs de messages)"
```

---

## Task 5: ConnectionManager

**Files:**
- Create: `apps/api/ws/manager.py`
- Test: `tests/test_ws.py` (ajouts)

- [ ] **Step 1: Écrire le test (échec attendu)**

Ajouter dans `tests/test_ws.py` :
```python
import asyncio


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = None

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)


def test_manager_connect_send_disconnect():
    from apps.api.ws.manager import ConnectionManager

    async def run():
        m = ConnectionManager()
        ws = FakeWebSocket()
        await m.connect(1, ws)
        ok = await m.send(1, {"type": "pong"})
        assert ok and ws.sent == [{"type": "pong"}]
        m.disconnect(1, ws)
        assert await m.send(1, {"x": 1}) is False

    asyncio.run(run())


def test_manager_replace_connection():
    from apps.api.ws.manager import ConnectionManager

    async def run():
        m = ConnectionManager()
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        await m.connect(7, ws1)
        await m.connect(7, ws2)          # 2e onglet : remplace la 1re
        assert ws1.closed and ws1.closed[0] == 4000
        await m.send(7, {"type": "pong"})
        assert ws2.sent and not ws1.sent

    asyncio.run(run())


def test_manager_busy_flag():
    from apps.api.ws.manager import ConnectionManager
    m = ConnectionManager()
    assert not m.is_busy(3)
    m.set_busy(3, True)
    assert m.is_busy(3)
    m.set_busy(3, False)
    assert not m.is_busy(3)
```

- [ ] **Step 2: Vérifier l'échec**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_ws.py -v`
Expected: FAIL (module `manager` introuvable)

- [ ] **Step 3: Implémenter**

`apps/api/ws/manager.py` :
```python
"""Registre des connexions WebSocket actives — une connexion par session.

Si une deuxieme connexion arrive pour la meme session (2 onglets),
la plus recente remplace l'ancienne (close code 4000). Spec §6.
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[int, object] = {}
        self._busy: set = set()

    async def connect(self, session_id: int, websocket) -> None:
        old = self._connections.get(session_id)
        if old is not None:
            try:
                await old.close(code=4000, reason="replaced_by_new_connection")
            except Exception:
                pass
        self._connections[session_id] = websocket
        logger.info(f"WS connecte: session={session_id}")

    def disconnect(self, session_id: int, websocket) -> None:
        if self._connections.get(session_id) is websocket:
            self._connections.pop(session_id, None)
            logger.info(f"WS deconnecte: session={session_id}")
        self._busy.discard(session_id)

    async def send(self, session_id: int, payload: dict) -> bool:
        ws = self._connections.get(session_id)
        if ws is None:
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            self._connections.pop(session_id, None)
            return False

    def is_busy(self, session_id: int) -> bool:
        return session_id in self._busy

    def set_busy(self, session_id: int, busy: bool) -> None:
        if busy:
            self._busy.add(session_id)
        else:
            self._busy.discard(session_id)


manager = ConnectionManager()
```

NB : l'accept du websocket est fait par l'endpoint (router) avant `connect`, pour pouvoir envoyer un close code custom si la session est inconnue.

- [ ] **Step 4: Vérifier le succès**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_ws.py -v`
Expected: tous PASSED

- [ ] **Step 5: Commit**

```powershell
git add apps/api/ws/manager.py tests/test_ws.py
git commit -m "feat: ConnectionManager WebSocket (1 connexion par session)"
```

---

## Task 6: run_agent_streaming — interrupt, metadata, resume

**Files:**
- Modify: `apps/api/services/agent_service.py` (`run_agent_streaming`, ligne ~311)
- Test: `tests/test_ws.py` (ajouts avec graphe mocké)

- [ ] **Step 1: Écrire le test (échec attendu)**

Ajouter dans `tests/test_ws.py` :
```python
def test_streaming_done_metadata_shape(monkeypatch):
    """Le done final doit contenir method/artifacts/interrupt."""
    from apps.api.services import agent_service

    class FakeSnapshot:
        values = {"method": "scaffold", "artifacts": [{"kind": "quiz"}],
                  "tool_transparency": []}
        next = ()
        tasks = ()

    class FakeGraph:
        def stream(self, inp, config=None):
            yield {"generate": {"answer": "Bonjour"}}
        def get_state(self, config):
            return FakeSnapshot()

    monkeypatch.setattr(agent_service, "get_graph", lambda: FakeGraph())
    monkeypatch.setattr(agent_service, "_build_initial_state",
                        lambda *a, **kw: {"question": "x"})

    events = list(agent_service.run_agent_streaming(
        question="salut", thread_id="t-test", user_id="u"))
    done = [e for e in events if e.get("done")]
    assert done, "doit avoir un evenement done"
    meta = done[0].get("metadata", {})
    assert meta.get("method") == "scaffold"
    assert meta.get("artifacts") == [{"kind": "quiz"}]
    assert "interrupt" in done[0]
    assert done[0]["interrupt"] is None
```

- [ ] **Step 2: Vérifier l'échec**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_ws.py::test_streaming_done_metadata_shape -v`
Expected: FAIL (metadata incomplète / pas de clé `interrupt`)

- [ ] **Step 3: Modifier run_agent_streaming**

Dans `apps/api/services/agent_service.py` :

a) Signature — ajouter le paramètre de reprise HITL :
```python
def run_agent_streaming(
    question: str,
    thread_id: Optional[str] = None,
    user_id: str = "default_user",
    model_override: Optional[str] = None,
    force_web_search: bool = False,
    session_id: Optional[int] = None,
    resume_value=None,
):
```

b) Choix de l'input (après `config_dict`) :
```python
    if resume_value is not None:
        # Reprise HITL : Command(resume=...) realimente interrupt()
        from langgraph.types import Command
        invoke_input = Command(resume=resume_value)
    else:
        invoke_input = _build_initial_state(
            graph, config_dict, question=question, user_id=user_id,
            thread_id=thread_id, model_override=model_override,
            force_web_search=force_web_search, streaming=True,
            session_id=session_id,
        )
```

c) Boucle : `for event in graph.stream(invoke_input, config=config_dict):` (remplace `initial_state`).

d) Après la boucle, remplacer le bloc final par :
```python
        # Etat final : method, artifacts, et interrupt eventuel (HITL)
        method, artifacts, transparency, interrupt_payload = None, [], [], None
        try:
            snapshot = graph.get_state(config_dict)
            if snapshot is not None:
                values = snapshot.values or {}
                method = values.get("method")
                artifacts = values.get("artifacts", [])
                transparency = values.get("tool_transparency", [])
                if snapshot.next:
                    for task in getattr(snapshot, "tasks", None) or []:
                        interrupts = getattr(task, "interrupts", None)
                        if interrupts:
                            interrupt_payload = interrupts[0].value
                            break
        except Exception:
            pass

        yield {
            "token": "",
            "done": True,
            "metadata": {
                "thread_id": thread_id,
                "method": method,
                "artifacts": artifacts,
                "tool_transparency": transparency,
            },
            "interrupt": interrupt_payload,
        }
```

- [ ] **Step 4: Vérifier le succès**

Run: `.\venv\Scripts\python.exe -m pytest tests/ -q`
Expected: tous PASSED

- [ ] **Step 5: Commit**

```powershell
git add apps/api/services/agent_service.py tests/test_ws.py
git commit -m "feat: streaming avec detection interrupt, metadata completes et resume HITL"
```

---

## Task 7: Endpoint WebSocket `/ws/{session_id}` (cœur du système)

**Files:**
- Create: `apps/api/ws/router.py`
- Test: `tests/test_ws.py` (ajouts)

- [ ] **Step 1: Écrire les tests (échec attendu)**

Ajouter dans `tests/test_ws.py` :
```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


@pytest.fixture
def ws_client(monkeypatch):
    """App FastAPI isolee avec le router WS + stubs (pas de DB ni LLM)."""
    from apps.api.ws import router as wr

    saved_messages = []

    monkeypatch.setattr(wr, "get_thread_id_from_session",
                        lambda sid, db_path=None: "thread-test")
    monkeypatch.setattr(wr.crud, "get_session",
                        lambda sid, db_path=None: {"id": sid, "title": "t"})
    monkeypatch.setattr(wr.crud, "add_message",
                        lambda **kw: saved_messages.append(kw) or 1)
    monkeypatch.setattr(wr, "_notify_due_reviews", lambda sid: None)

    def fake_stream(**kwargs):
        yield {"token": "Bonjour", "done": False}
        yield {"token": "", "done": True,
               "metadata": {"thread_id": kwargs.get("thread_id"),
                            "method": "scaffold", "artifacts": [],
                            "tool_transparency": []},
               "interrupt": None}

    monkeypatch.setattr(wr.agent_service, "run_agent_streaming", fake_stream)

    app = FastAPI()
    app.include_router(wr.router)
    return TestClient(app), saved_messages


def test_ws_ping_pong(ws_client):
    client, _ = ws_client
    with client.websocket_connect("/ws/1?user_id=u") as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_ws_unknown_session_closed_4404(ws_client, monkeypatch):
    client, _ = ws_client
    from apps.api.ws import router as wr
    monkeypatch.setattr(wr.crud, "get_session", lambda sid, db_path=None: None)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/999?user_id=u") as ws:
            ws.receive_json()
    assert exc.value.code == 4404


def test_ws_chat_streams_tokens_then_final(ws_client):
    client, saved = ws_client
    with client.websocket_connect("/ws/5?user_id=u") as ws:
        ws.send_json({"type": "chat", "question": "salut"})
        got_token, got_final = None, None
        for _ in range(10):
            msg = ws.receive_json()
            if msg["type"] == "token":
                got_token = msg
            elif msg["type"] == "message":
                got_final = msg
                break
        assert got_token and got_token["text"] == "Bonjour"
        assert got_final["answer"] == "Bonjour"
        assert got_final["method"] == "scaffold"
        # Messages sauvegardes dans la session (liaison session ↔ WS)
        roles = [m["role"] for m in saved]
        assert "user" in roles and "assistant" in roles


def test_ws_chat_concurrent_refuse(ws_client):
    client, _ = ws_client
    from apps.api.ws import router as wr

    import time

    def slow_stream(**kwargs):
        yield {"token": "lent", "done": False}
        time.sleep(1.0)
        yield {"token": "", "done": True,
               "metadata": {"thread_id": "t", "method": "scaffold",
                            "artifacts": [], "tool_transparency": []},
               "interrupt": None}

    # Note: monkeypatch dans le test remplace le fake du fixture
    wr.agent_service.run_agent_streaming = slow_stream
    with client.websocket_connect("/ws/6?user_id=u") as ws:
        ws.send_json({"type": "chat", "question": "q1"})
        ws.send_json({"type": "chat", "question": "q2"})
        types = []
        for _ in range(10):
            msg = ws.receive_json()
            types.append(msg["type"])
            if msg["type"] == "message":
                break
        assert "error" in types  # q2 refuse : agent_busy
```

- [ ] **Step 2: Vérifier l'échec**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_ws.py -v`
Expected: FAIL (module `router` introuvable)

- [ ] **Step 3: Implémenter le router**

`apps/api/ws/router.py` :
```python
"""Endpoint WebSocket /ws/{session_id} — relie session DB ↔ thread LangGraph.

Spec : docs/superpowers/specs/2026-08-27-websocket-cache-design.md
- La connexion est validee contre la session DB (close 4404 si inconnue)
- Le thread LangGraph est resolu depuis la session (continuite checkpointer)
- Les messages sont sauvegardes dans la session (crud.add_message)
- L'agent tourne dans un thread ; tokens pousses via file asyncio
  (pont loop.call_soon_threadsafe — Queue.put direct depuis un thread
  n'est pas sur)
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.api.db import crud
from apps.api.services import agent_service
from apps.api.services.checkpoint import get_thread_id_from_session
from apps.api.ws.manager import manager
from apps.api.ws import protocol as p
import apps.api.config as config

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


def _notify_due_reviews(session_id: int) -> None:
    """Pousse une notification si des revisions sont dues (fire-and-forget)."""
    try:
        from apps.api.agent.memory import revision_planner
        due = revision_planner.get_due_reviews(db_path=config.DB_PATH, limit=5)
        if due:
            asyncio.get_event_loop().create_task(manager.send(
                session_id,
                p.notification_msg("revision_due", {
                    "count": len(due),
                    "items": [d.get("competency_name", d.get("nom", "")) for d in due],
                }),
            ))
    except Exception:
        pass


async def _run_stream_to_socket(session_id: int, thread_id: int, user_id: str,
                                question: str, force_web_search: bool,
                                resume_value=None) -> None:
    """Execute l'agent (streaming) dans un thread et pousse les tokens."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def worker():
        try:
            for event in agent_service.run_agent_streaming(
                question=question,
                thread_id=thread_id,
                user_id=user_id,
                force_web_search=force_web_search,
                session_id=session_id,
                resume_value=resume_value,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as e:
            logger.error(f"WS agent error: {e}", exc_info=True)
            loop.call_soon_threadsafe(queue.put_nowait, {"token": "", "done": True, "error": str(e)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    asyncio.get_running_loop().run_in_executor(None, worker)

    full_answer = ""
    final_meta = {}
    interrupt_payload = None
    error = None
    while True:
        event = await queue.get()
        if event is None:
            break
        if event.get("error"):
            error = event["error"]
        token = event.get("token")
        if token:
            full_answer += token
            await manager.send(session_id, p.token_msg(token))
        if event.get("interrupt"):
            interrupt_payload = event["interrupt"]
        if event.get("done"):
            final_meta = event.get("metadata", {}) or {}

    if error:
        await manager.send(session_id, p.error_msg(error))
        manager.set_busy(session_id, False)
        return

    # Interrupt (HITL) : demander confirmation, pas de message final complet
    if interrupt_payload is not None:
        payload = interrupt_payload if isinstance(interrupt_payload, dict) else {"question": str(interrupt_payload)}
        await manager.send(session_id, p.confirmation_request_msg(
            payload.get("type"), payload.get("question", "")))
        # Sauvegarder la question de l'utilisateur seulement
        try:
            crud.add_message(session_id=session_id, role="user",
                             content=question, user_id=user_id,
                             db_path=config.DB_PATH)
        except Exception:
            pass
        manager.set_busy(session_id, False)
        return

    # Message final + sauvegarde dans la session
    result = {
        "answer": full_answer,
        "method": final_meta.get("method"),
        "thread_id": thread_id,
        "artifacts": final_meta.get("artifacts", []),
        "tool_transparency": final_meta.get("tool_transparency", []),
    }
    try:
        if question:
            crud.add_message(session_id=session_id, role="user",
                             content=question, user_id=user_id,
                             db_path=config.DB_PATH)
        crud.add_message(session_id=session_id, role="assistant",
                         content=full_answer,
                         method_used=result["method"],
                         user_id=user_id, db_path=config.DB_PATH)
    except Exception as e:
        logger.warning(f"WS save message failed: {e}")

    await manager.send(session_id, p.final_message_msg(result))
    _notify_due_reviews(session_id)
    manager.set_busy(session_id, False)


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: int,
                             user_id: str = "default_user"):
    await websocket.accept()

    # Liaison session DB ↔ WebSocket
    session = crud.get_session(session_id, db_path=config.DB_PATH)
    if not session:
        await websocket.close(code=4404, reason="session_not_found")
        return

    # Liaison session ↔ thread LangGraph
    thread_id = get_thread_id_from_session(session_id)
    if not thread_id:
        thread_id = str(uuid.uuid4())
        try:
            crud.update_session(session_id, thread_id=thread_id,
                                db_path=config.DB_PATH)
        except Exception:
            pass

    await manager.connect(session_id, websocket)
    try:
        # Resync HITL : interrupt en attente dans le checkpoint → re-emission
        pending = agent_service._get_pending_interrupt(
            agent_service.get_graph(),
            {"configurable": {"thread_id": thread_id}},
        )
        if pending is not None:
            payload = pending if isinstance(pending, dict) else {"question": str(pending)}
            await manager.send(session_id, p.confirmation_request_msg(
                payload.get("type"), payload.get("question", "")))

        while True:
            data = await websocket.receive_json()
            mtype = data.get("type")

            if mtype == "ping":
                await manager.send(session_id, p.pong_msg())

            elif mtype == "chat":
                if manager.is_busy(session_id):
                    await manager.send(session_id, p.error_msg("agent_busy"))
                    continue
                question = (data.get("question") or "").strip()
                if not question:
                    await manager.send(session_id, p.error_msg("empty_question"))
                    continue
                manager.set_busy(session_id, True)
                asyncio.create_task(_run_stream_to_socket(
                    session_id, thread_id, user_id, question,
                    bool(data.get("force_web_search", False)),
                ))

            elif mtype == "confirm":
                if manager.is_busy(session_id):
                    await manager.send(session_id, p.error_msg("agent_busy"))
                    continue
                manager.set_busy(session_id, True)
                asyncio.create_task(_run_stream_to_socket(
                    session_id, thread_id, user_id, "",
                    False, resume_value=bool(data.get("accepted")),
                ))

            elif mtype == "quiz_submit":
                # Reutilise la route existante (synchrone, rapide)
                try:
                    from apps.api.agent.tools.progress import update_mastery_from_score
                    import json as _json
                    res = update_mastery_from_score.invoke({
                        "competency_id": data.get("competency_id"),
                        "correct": int(data.get("correct", 0)),
                        "total": int(data.get("total", 1)),
                    })
                    await manager.send(session_id, {
                        "type": "quiz_result",
                        "mastery": _json.loads(res),
                    })
                except Exception as e:
                    await manager.send(session_id, p.error_msg(f"quiz_submit_failed: {e}"))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS error session={session_id}: {e}", exc_info=True)
    finally:
        manager.disconnect(session_id, websocket)
```

NB : vérifier que `crud.update_session` existe (utilisé par `apps/api/routes/sessions.py`) ; sinon ajouter une fonction minimale qui UPDATE le `thread_id`.

- [ ] **Step 4: Vérifier le succès**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_ws.py -v`
Expected: tous PASSED

- [ ] **Step 5: Commit**

```powershell
git add apps/api/ws/router.py tests/test_ws.py
git commit -m "feat: endpoint WebSocket /ws/{session_id} - session↔thread↔WS, streaming, HITL"
```

---

## Task 8: Enregistrement du router dans main.py

**Files:**
- Modify: `apps/api/main.py` (après les `include_router`, ligne ~74)

- [ ] **Step 1: Ajouter le router WS**

Dans `apps/api/main.py`, après les imports de routers :
```python
from apps.api.ws.router import router as ws_router
```
Et après les `app.include_router(...)` :
```python
app.include_router(ws_router)  # pas de prefix : /ws/{session_id}
```

- [ ] **Step 2: Vérifier que l'app démarre**

Run: `.\venv\Scripts\python.exe -c "from apps.api.main import app; print([r.path for r in app.routes if 'ws' in str(r.path)])"`
Expected: affiche `['/ws/{session_id}']` (ou similaire)

Run: `.\venv\Scripts\python.exe -m pytest tests/ -q`
Expected: tous PASSED

- [ ] **Step 3: Commit**

```powershell
git add apps/api/main.py
git commit -m "feat: enregistre le router WebSocket dans l'app FastAPI"
```

---

## Task 9: Client WebSocket frontend

**Files:**
- Create: `apps/web/lib/websocket.ts`

- [ ] **Step 1: Implémenter le client**

`apps/web/lib/websocket.ts` :
```typescript
// Client WebSocket de l'agent — reconnexion backoff + fallback HTTP.
// L'URL WS est derivee de NEXT_PUBLIC_API_URL :
//   https://host/api  →  wss://host

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";
const WS_BASE = API_BASE
  .replace(/^https:/, "wss:")
  .replace(/^http:/, "ws:")
  .replace(/\/api\/?$/, "");

export interface AgentSocketHandlers {
  onToken: (text: string) => void;
  onMessage: (msg: Record<string, unknown>) => void;
  onConfirmationRequest: (confirmationType: string, prompt: string) => void;
  onNotification: (kind: string, data: Record<string, unknown>) => void;
  onError: (message: string) => void;
  onStatusChange: (connected: boolean) => void;
}

export interface AgentSocket {
  send: (payload: Record<string, unknown>) => boolean;
  close: () => void;
  isOpen: () => boolean;
}

export function createAgentSocket(
  sessionId: number,
  userId: string,
  handlers: AgentSocketHandlers,
  maxRetries: number = 3
): AgentSocket {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let closedByUser = false;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function clearTimers() {
    if (pingTimer) clearInterval(pingTimer);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    pingTimer = null;
    reconnectTimer = null;
  }

  function connect() {
    try {
      ws = new WebSocket(
        `${WS_BASE}/ws/${sessionId}?user_id=${encodeURIComponent(userId)}`
      );
    } catch {
      handlers.onStatusChange(false);
      return;
    }

    ws.onopen = () => {
      attempt = 0;
      handlers.onStatusChange(true);
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, 25000);
    };

    ws.onmessage = (event) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      switch (msg.type) {
        case "token":
          handlers.onToken(String(msg.text || ""));
          break;
        case "message":
          handlers.onMessage(msg);
          break;
        case "confirmation_request":
          handlers.onConfirmationRequest(
            String(msg.confirmation_type || ""),
            String(msg.confirmation_prompt || "")
          );
          break;
        case "notification":
          handlers.onNotification(
            String(msg.kind || ""),
            (msg.data as Record<string, unknown>) || {}
          );
          break;
        case "error":
          handlers.onError(String(msg.message || "erreur"));
          break;
        case "pong":
          break;
      }
    };

    ws.onclose = (event) => {
      clearTimers();
      handlers.onStatusChange(false);
      if (closedByUser) return;
      // 4000 = remplace par un autre onglet : ne pas reconnecter
      if (event.code === 4000) return;
      if (attempt >= maxRetries) return; // le fallback HTTP prend le relais
      const delay = Math.min(15000, 1000 * Math.pow(2, attempt))
        + Math.random() * 500;
      attempt += 1;
      reconnectTimer = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose suivra et gerera la reconnexion
    };
  }

  connect();

  return {
    send: (payload) => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
        return true;
      }
      return false;
    },
    close: () => {
      closedByUser = true;
      clearTimers();
      ws?.close();
    },
    isOpen: () => ws?.readyState === WebSocket.OPEN,
  };
}
```

- [ ] **Step 2: Vérifier la compilation TypeScript**

Run (depuis `apps/web`): `npx tsc --noEmit`
Expected: pas d'erreur sur `lib/websocket.ts`

- [ ] **Step 3: Commit**

```powershell
git add apps/web/lib/websocket.ts
git commit -m "feat: client WebSocket avec reconnexion backoff et fallback"
```

---

## Task 10: Intégration dans ChatWindow (streaming réel + confirmations)

**Files:**
- Modify: `apps/web/components/chat/ChatWindow.tsx`

- [ ] **Step 1: Ajouter l'état socket et la connexion par session**

En haut du composant, ajouter les imports :
```typescript
import { createAgentSocket, type AgentSocket } from "@/lib/websocket";
```

Dans le composant, ajouter les états :
```typescript
const socketRef = useRef<AgentSocket | null>(null);
const [socketConnected, setSocketConnected] = useState(false);
const [notification, setNotification] = useState<string | null>(null);
const streamingRef = useRef("");
```

Effet de connexion (remplace le chargement des messages pour la partie socket ; le chargement des messages existant reste) :
```typescript
useEffect(() => {
  if (!sessionId) return;
  const socket = createAgentSocket(sessionId, "default_user", {
    onToken: (text) => {
      streamingRef.current += text;
      setStreamingText(streamingRef.current);
    },
    onMessage: (msg) => {
      const assistantMsg: ChatMessage = {
        id: Date.now(),
        role: "assistant",
        content: String(msg.answer || ""),
        method: msg.method as string | undefined,
        tools_used: msg.tool_transparency as ToolUsage[] | undefined,
        artifacts: msg.artifacts as ChatMessage["artifacts"],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setStreamingText("");
      streamingRef.current = "";
      setIsStreaming(false);
    },
    onConfirmationRequest: (type, prompt) => {
      setPendingConfirmation({ type, prompt, messageId: Date.now() });
      setIsStreaming(false);
      setStreamingText("");
      streamingRef.current = "";
    },
    onNotification: (kind, data) => {
      if (kind === "revision_due") {
        setNotification(`📅 ${data.count} révision(s) due(s)`);
      }
    },
    onError: (message) => {
      if (message === "agent_busy") return; // l'UI desactive deja l'envoi
      console.error("WS error:", message);
    },
    onStatusChange: setSocketConnected,
  });
  socketRef.current = socket;
  return () => socket.close();
}, [sessionId]);
```

- [ ] **Step 2: Modifier handleSend — socket d'abord, fallback HTTP**

Au début de `handleSend`, après l'ajout du message utilisateur :
```typescript
    // Chemin WebSocket (streaming reel) si connecte
    const sent = socketRef.current?.send({
      type: "chat",
      question: trimmed,
      force_web_search: forceWebSearch,
    });
    if (sent) {
      streamingRef.current = "";
      setStreamingMethod(undefined);
      return; // la reponse arrive par onToken/onMessage
    }
    // Sinon : fallback HTTP (code existant en dessous)
```
(Le code HTTP existant reste inchangé après ce bloc.)

- [ ] **Step 3: Modifier handleConfirm — passer par le socket**

Dans `handleConfirm`, avant l'appel HTTP :
```typescript
    const sent = socketRef.current?.send({ type: "confirm", accepted });
    if (sent) {
      setPendingConfirmation(null);
      setIsStreaming(true);
      return;
    }
```

- [ ] **Step 4: Afficher le statut de connexion et la notification**

Dans le header de la zone de messages (ou au-dessus du Composer) :
```tsx
{!socketConnected && (
  <div className="text-xs text-amber-400 px-4 py-1">
    Connexion temps réel indisponible — mode classique
  </div>
)}
{notification && (
  <div className="text-xs text-primary-400 px-4 py-1 flex justify-between">
    <span>{notification}</span>
    <button onClick={() => setNotification(null)}>✕</button>
  </div>
)}
```

- [ ] **Step 5: Vérifier la compilation**

Run (depuis `apps/web`): `npx tsc --noEmit`
Expected: pas d'erreur

- [ ] **Step 6: Commit**

```powershell
git add apps/web/components/chat/ChatWindow.tsx
git commit -m "feat: ChatWindow en streaming reel via WebSocket avec fallback HTTP"
```

---

## Task 11: Déploiement backend + frontend

- [ ] **Step 1: Tests complets**

Run: `.\venv\Scripts\python.exe -m pytest tests/ -q`
Expected: tous PASSED (29 existants + nouveaux)

- [ ] **Step 2: Push GitHub (déclenche l'auto-deploy Vercel du frontend)**

```powershell
git push origin main
```

- [ ] **Step 3: Deploy backend Fly.io**

```powershell
$env:Path = "C:\Users\hp\.fly\bin;" + $env:Path
flyctl deploy --remote-only
```
Expected: « Visit your newly deployed app at https://agent-apprentissage-api.fly.dev/ »

- [ ] **Step 4: Vérifier l'auto-deploy Vercel**

```powershell
cd apps/web; vercel ls
```
Expected: dernier deployment ● Ready (43-60s)

---

## Task 12: Vérification E2E en production

- [ ] **Step 1: Script de test WS contre la prod**

Créer `test_ws_prod.py` (temporaire, ne pas committer) :
```python
import asyncio
import json
import websockets

API = "wss://agent-apprentissage-api.fly.dev/ws"

async def main():
    # 1. Creer une session via HTTP
    import urllib.request
    req = urllib.request.Request(
        "https://agent-apprentissage-api.fly.dev/api/sessions",
        data=json.dumps({"title": "test ws", "user_id": "default_user"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    session = json.loads(urllib.request.urlopen(req, timeout=60).read())
    sid = session["id"]
    print(f"session: {sid}")

    # 2. Connexion WebSocket
    async with websockets.connect(f"{API}/{sid}?user_id=default_user") as ws:
        await ws.send(json.dumps({"type": "ping"}))
        print("ping ->", await asyncio.wait_for(ws.recv(), 30))

        await ws.send(json.dumps({"type": "chat", "question": "Je veux apprendre les fractions."}))
        tokens = 0
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 240))
            if msg["type"] == "token":
                tokens += 1
                print(msg["text"], end="", flush=True)
            elif msg["type"] == "confirmation_request":
                print("\nHITL:", msg["confirmation_prompt"])
                break
            elif msg["type"] == "message":
                print(f"\n[message final] method={msg.get('method')}")
                break
            elif msg["type"] == "error":
                print("ERREUR:", msg["message"])
                break
        print(f"\ntokens recus: {tokens}")

asyncio.run(main())
```

Run: `.\venv\Scripts\python.exe test_ws_prod.py`
Expected: pong reçu, puis tokens en streaming réel (diagnostic fractions), tokens > 1

- [ ] **Step 2: Vérifier dans l'UI**

Ouvrir https://web-seven-nu-xdmbicvsxb.vercel.app/chat :
- Nouvelle session → message « Je veux apprendre les fractions »
- Expected: le texte s'écrit en temps réel (pas mot par mot saccadé), pas de badge « mode classique »
- Continuer le diagnostic 3 tours → confirmation de compétence via les boutons (passe par le socket)

- [ ] **Step 3: Nettoyer et commit final**

```powershell
Remove-Item test_ws_prod.py
git add -A; git commit -m "chore: verification E2E WebSocket OK" --allow-empty
git push origin main
```

---

## Récapitulatif de la liaison session ↔ thread ↔ WebSocket

| Étape | Mécanisme |
|---|---|
| Connexion WS | `/ws/{session_id}` valide la session DB (`crud.get_session`) — close 4404 si inconnue |
| Thread | `get_thread_id_from_session(session_id)` résout le thread LangGraph (créé + sauvé dans la session si absent) |
| Continuité | tout le flux WS utilise ce thread → le checkpointer LangGraph préserve l'état (diagnostic, HITL, historique) |
| Messages | chaque tour est sauvé dans la session via `crud.add_message` (visible au rechargement) |
| Reconnexion | l'interrupt en attente est ré-émis à la connexion (checkpoint) — la confirmation n'est jamais perdue |
| 2 onglets | la connexion la plus récente remplace l'ancienne (close 4000) |
