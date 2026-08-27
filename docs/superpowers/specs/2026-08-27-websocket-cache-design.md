# Design : WebSocket temps réel + gestion de cache

**Date** : 2026-08-27
**Projet** : Agent d'Apprentissage (FastAPI + LangGraph sur Fly.io / Next.js sur Vercel / Neon Postgres / Chroma Cloud)
**Statut** : Approuvé par l'utilisateur

## 1. Objectif

Remplacer le schéma HTTP requête/réponse du chat par un canal WebSocket bidirectionnel unique couvrant :

1. **Streaming réel** des réponses de l'agent (token par token, remplace la simulation frontend mot par mot)
2. **Canal bidirectionnel complet** : envoi de messages, confirmations HITL (`interrupt()`/`Command(resume)`), soumission de quiz — sur la même connexion persistante
3. **Notifications temps réel** : révisions dues (Leitner), mises à jour de progression
4. **Gestion de cache** serveur et client pour réduire la latence (Neon ~500 ms/requête depuis cdg, Chroma Cloud, LLM)

Hors périmètre : scaling multi-machines (1 machine Fly, 1 utilisateur actif), authentification complexe (user_id en query param comme sur les routes HTTP existantes).

## 2. Architecture

```
Navigateur (Vercel)
   │  wss://agent-apprentissage-api.fly.dev/ws/{session_id}?user_id=...
   ▼
Proxy Fly.io (supporte WebSocket nativement)
   ▼
FastAPI — endpoint /ws/{session_id}
   ├── ConnectionManager (registre session_id → websocket, heartbeat)
   ├── asyncio.to_thread(run_agent_streaming / run_agent)
   │      └── file asyncio de tokens → websocket.send_json({type:"token"})
   └── NotificationService (révisions dues après chaque tour)

Caches :
   ├── serveur : profil+compétences (TTL 30 s), retrieval RAG (TTL 10 min), recherche web (DB, TTL 24 h existant)
   └── client : messages par session, liste de sessions (déjà en place)
```

Les endpoints HTTP existants (`/api/chat`, `/api/chat/confirm`, …) restent opérationnels : le WebSocket est le chemin principal, HTTP sert de fallback.

## 3. Composants backend

### 3.1 `apps/api/ws/manager.py` — ConnectionManager
- `connect(session_id, websocket)` / `disconnect(session_id)`
- `send(session_id, payload: dict)` avec tolérance aux erreurs (connexion morte → nettoyage)
- Heartbeat : ping serveur toutes les 30 s ; si le pong manque 2 fois → fermeture
- Un seul registre en mémoire (singleton module) — suffisant pour 1 machine

### 3.2 `apps/api/ws/protocol.py` — types de messages
Client → serveur :
- `{type: "chat", question: str, force_web_search?: bool, model_override?: str}`
- `{type: "confirm", accepted: bool}`
- `{type: "quiz_submit", competency_id, correct, total}`
- `{type: "ping"}`

Serveur → client :
- `{type: "token", text: str}` — token de streaming
- `{type: "message", message_id, answer, method, artifacts, tool_transparency, thread_id}` — réponse finale
- `{type: "confirmation_request", confirmation_type, confirmation_prompt}` — HITL
- `{type: "notification", kind: "revision_due"|"progress_update", data}` 
- `{type: "error", message}`
- `{type: "pong"}`

### 3.3 `apps/api/ws/router.py` — endpoint `/ws/{session_id}`
1. Valide la session (DB) ; refuse avec close code 4404 si inconnue
2. Enregistre la connexion dans le ConnectionManager
3. Boucle de réception : pour chaque message client, lance le traitement dans un thread (`asyncio.to_thread`) pour ne pas bloquer la boucle d'écoute
4. `chat` → `run_agent_streaming` ; les tokens sont poussés au fur et à mesure via une file asyncio ; à la fin, `message` final + sauvegarde DB + notification éventuelle
5. `confirm` → détection de l'interrupt en attente → `Command(resume=accepted)` ; si un nouvel interrupt survient, renvoie `confirmation_request`
6. `quiz_submit` → même logique que `/api/chat/quiz-submit` + notification de progression

### 3.4 Adaptation de `agent_service`
- `run_agent_streaming` yield déjà des dicts `{token|done|metadata}` — réutilisé tel quel
- Détection d'interrupt dans le flux streaming : si le graphe s'arrête sur un interrupt, émettre `confirmation_request` (parallèle à `_extract_interrupt` de `run_agent`)

## 4. Gestion de cache

### 4.1 Serveur — `apps/api/services/cache.py`
Cache mémoire TTL+LRU borné (max 128 entrées par namespace, pour rester dans les 512 Mo de la machine) :
- **`profile`** : `get_profile(user_id)` TTL 30 s — invalidé par `update_profile`
- **`competencies`** : `get_competencies(domain)` TTL 30 s — invalidé par `create_competency`
- **`rag_retrieval`** : clé = hash(question + top_k), TTL 10 min — évite les allers-retours Chroma Cloud répétés

Invalidation explicite dans `crud.py` (wrapper après écriture) pour garantir la cohérence.

### 4.2 Existant conservé
- Recherche web : table `web_search_cache`, TTL 24 h ✅
- Client : `messagesCache` + fetch unique de la liste de sessions ✅

## 5. Frontend

### 5.1 `apps/web/lib/websocket.ts`
- `createAgentSocket(sessionId, handlers)` : ouvre `wss://…/ws/{session_id}?user_id=…`
- Reconnexion automatique avec backoff exponentiel (1 s, 2 s, 4 s, max 15 s) + jitter
- Après 3 échecs : bascule en mode HTTP (comportement actuel) et badge « connexion dégradée »
- Ping client toutes les 25 s

### 5.2 `ChatWindow.tsx`
- Utilise le socket quand disponible : affichage token par token réel (plus de simulation)
- `confirmation_request` → `ConfirmationButtons` ; la réponse repart par le socket
- `notification` → toast/badge (révisions dues)
- Fallback : si pas de socket, chemin HTTP actuel inchangé

## 6. Gestion d'erreurs

- **Coupure réseau** : reconnexion auto ; les messages envoyés pendant la coupure basculent en HTTP
- **Machine Fly endormie** : le premier WS peut échouer (réveil) → reconnexion auto le couvre
- **Agent en erreur** : `{type:"error"}` + message sauvegardé côté serveur
- **Double connexion même session** (2 onglets) : la connexion la plus récente remplace l'ancienne (close 4000)

## 7. Tests

- pytest + `TestClient.websocket_connect` :
  - connexion/déconnexion, ping/pong
  - `chat` → réception de `token` puis `message`
  - `confirm` → reprise HITL
  - session inconnue → close 4404
- Cache : hit/miss/invalidation
- Tests existants (29) doivent rester verts

## 8. Déploiement

- Fly.io : le proxy passe WebSocket nativement (aucune config supplémentaire) ; deploy habituel
- Vercel : le navigateur se connecte directement à Fly (pas de WS via Vercel) ; variable `NEXT_PUBLIC_WS_URL` dérivée de `NEXT_PUBLIC_API_URL`
- Vérification post-deploy : echo WS + chat complet en streaming depuis l'UI

## 9. Ordre d'implémentation

1. Cache serveur (indépendant, gain immédiat même sans WS)
2. Module WS backend (manager, protocole, router) + adaptation streaming/interrupt
3. Tests backend WS
4. Frontend `websocket.ts` + intégration ChatWindow
5. Déploiement + vérification E2E
