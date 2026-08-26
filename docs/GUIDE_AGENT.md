# 🎓 Guide de l'Agent d'Apprentissage — Fonctionnement & Structure

> Ce guide explique **comment l'agent réagit à tes questions**, **comment il fonctionne** et **comment il est structuré**. Il s'adresse à toi (utilisateur) et à quiconque veut comprendre ou faire évoluer le système.

---

## 1. Vue d'ensemble : qu'est-ce que cet agent ?

C'est un **tuteur pédagogique adaptatif**. Contrairement à un chatbot classique qui répond juste aux questions, cet agent :

- **Évalue ton niveau** avant de t'enseigner (diagnostic interactif).
- **Choisit une méthode pédagogique** adaptée à ta maîtrise du sujet (scaffold, socratique, Feynman, quiz…).
- **Suit ta progression** dans une base de données (répétition espacée Leitner).
- **S'appuie sur tes documents** (RAG) quand c'est pertinent, et le dit honnêtement sinon.
- **Te propose une prochaine étape** après chaque évaluation.

**Stack technique** : FastAPI + LangGraph (backend), Next.js (frontend), SQLite (mémoire), ChromaDB (RAG), Ollama (LLM local + cloud).

---

## 2. Comment l'agent réagit à une question — le parcours complet

Quand tu envoies un message, il traverse un **graphe de décisions** (LangGraph). Voici le parcours, étape par étape :

```
┌─────────┐
│  START  │
└────┬────┘
     ▼
┌─────────┐   Pas de domaine défini ?
│ ROUTER  │──────────────────────────► DIAGNOSTIC (pose des questions)
└────┬────┘
     │ Domaine connu
     ▼
┌──────────────────┐   Réponse à un quiz / diagnostic / Feynman en cours ?
│ ANSWER_PROCESSING│──────────────────────────────────────────────────┐
└────┬─────────────┘                                                  │
     │ Question normale                                               │
     ▼                                                                │
┌─────────┐                                                           │
│ RETRIEVE│  (RAG : cherche dans tes documents + double-check)        │
└────┬────┘                                                           │
     ▼                                                                │
┌────────┐  Choisit la méthode selon ta maîtrise de la compétence     │
│ METHOD │────────────────────────────────────────────────────────────┤
└────┬───┘                                                            │
     │                                                                │
     ├─► CONFIRMATION (quiz/feynman/artifact : demande ton accord)    │
     ├─► TOOL (exécute quiz / recherche web / révision / Feynman)     │
     └─► GENERATE (réponse directe)                                   │
              │                                                       │
              ▼                                                       │
        ┌─────────┐                                                   │
        │EVALUATE │  (met à jour ta maîtrise Leitner)                 │
        └────┬────┘                                                   │
             ▼                                                        │
        ┌─────────┐                                                   │
        │GENERATE │  (formule la réponse + feedback adaptatif)        │
        └────┬────┘                                                   │
             ▼                                                        │
          ┌─────┐                                                     │
          │ END │◄────────────────────────────────────────────────────┘
          └─────┘
```

### Les 9 nœuds du graphe

| Nœud | Rôle |
|---|---|
| **router** | Analyse ta question : est-ce une question "méta" (sur l'agent) ? Y a-t-il un domaine défini ? Faut-il un diagnostic ? |
| **answer_processing** | Traite ta réponse si tu es au milieu d'un quiz, d'un diagnostic ou d'une explication Feynman. |
| **diagnostic** | Génère 3 questions pour estimer ton niveau (voir §3). |
| **retrieve** | Cherche dans tes documents (RAG) avec double-check de pertinence (voir §6). |
| **method** | Choisit la méthode pédagogique selon ta maîtrise (voir §4). |
| **confirmation** | Demande ton accord avant de lancer un quiz, un Feynman ou un artefact (HITL). |
| **tool** | Exécute l'outil choisi : génère le quiz, fait la recherche web, lance le Feynman… |
| **evaluate** | Met à jour ta maîtrise Leitner après une évaluation. |
| **generate** | Formule la réponse finale avec la bonne méthode + feedback adaptatif. |

---

## 3. Le diagnostic : comment l'agent estime ton niveau

**Avant** : l'agent devinait ton niveau sans te poser de questions (❌ faux).
**Après le Correctif 1** : il te pose réellement les questions et attend tes réponses.

### Déroulement
1. **Premier message** sans domaine défini → l'agent déclenche le diagnostic.
2. Il génère **3 questions** (facile → difficile) via le LLM.
3. Il te pose la **question 1** et attend ta réponse.
4. À chaque réponse, il pose la **question suivante** (2/3, puis 3/3).
5. Une fois les 3 réponses collectées, il **analyse tes réponses** via le LLM (`DIAGNOSTIC_EVAL_PROMPT`) et en déduit ton niveau : `debutant`, `intermediaire` ou `avance`.
6. Il **initialise ta maîtrise** pour toutes les compétences du domaine selon ce niveau, puis t'accueille.

### Pourquoi c'est important
Le niveau estimé sert de **point de départ** à la répétition espacée. Un diagnostic réel = un point de départ précis = des quiz et des explications calibrés.

---

## 4. Le choix de la méthode pédagogique

**Avant** : l'agent choisissait la méthode selon ton niveau **global** (❌ trop grossier).
**Après le Correctif 3** : il choisit selon ta **maîtrise de la compétence active** (✅ précis).

### Les méthodes disponibles

| Méthode | Quand elle est utilisée | Ce qu'elle fait |
|---|---|---|
| **scaffold** | Maîtrise < 0.4 | Explication pas-à-pas, très guidée, avec exemples simples. |
| **socratic** | Maîtrise 0.4 – 0.7 | Pose des questions pour te faire réfléchir et découvrir la réponse. |
| **feynman** | Maîtrise ≥ 0.7 | Te demande d'expliquer le concept avec tes mots, puis évalue. |
| **quiz** | Sur demande ou après confirmation | Génère un quiz interactif de 3 questions. |
| **web_search** | Question d'actualité ou toggle activé | Cherche sur le web (DuckDuckGo). |
| **revision** | Des révisions sont dues | Propose un plan de révision Leitner. |
| **artifact** | Demande de schéma/code/graphique | Génère un artefact visuel. |

### La logique de sélection
```
1. Un quiz est en cours ?              → quiz
2. Une explication Feynman est attendue ? → feynman
3. Toggle "recherche web" activé ?     → web_search
4. Question de révision ?              → revision
5. Question d'actualité ?              → web_search
6. Maîtrise de la compétence active :
     < 0.4   → scaffold
     0.4-0.7 → socratic
     ≥ 0.7   → feynman
7. Sinon, fallback sur le niveau global.
```

---

## 4bis. Les 8 méthodes d'apprentissage en détail

Chaque méthode repose sur un **principe pédagogique éprouvé**. Voici ce que chacune fait concrètement, quand elle est déclenchée, et un exemple de dialogue.

### 🔍 1. Diagnostic — l'évaluation initiale
- **Principe** : on ne peut pas enseigner efficacement sans savoir d'où part l'apprenant (évaluation diagnostique).
- **Quand** : au tout premier échange, quand aucun domaine n'est défini dans ton profil.
- **Déroulement** : l'agent génère 3 questions (facile → difficile), te les pose une par une, puis analyse tes réponses pour estimer ton niveau (`debutant` / `intermediaire` / `avance`).
- **Exemple** :
  > 🤖 « Avant de commencer, j'aimerais estimer ton niveau en Python. Question 1/3 : Qu'est-ce qu'une variable ? »
  > 👤 « C'est un nom qui stocke une valeur. »
  > 🤖 « Question 2/3 : Quelle est la différence entre une liste et un tuple ? »

### 🧱 2. Scaffold — l'étayage (pour débutant)
- **Principe** : le *scaffolding* (Bruner) — on fournit une structure de soutien que l'on retire progressivement à mesure que l'apprenant gagne en autonomie. Idéal pour une notion totalement nouvelle.
- **Quand** : maîtrise de la compétence < 0.4.
- **Déroulement** : l'agent structure sa réponse en 4 étapes fixes :
  1. **Définition simple** en une phrase,
  2. **Analogie concrète** (lien avec le quotidien),
  3. **Exemple détaillé**,
  4. **Point de vigilance** (l'erreur fréquente à éviter).
- **Exemple** :
  > 👤 « C'est quoi une boucle for ? »
  > 🤖 « 1. Une boucle `for` répète une action pour chaque élément d'une collection. 2. C'est comme distribuer des cartes : tu donnes une carte à chaque joueur, l'un après l'autre. 3. `for carte in paquet: distribuer(carte)`. 4. Attention : n'oublie pas les deux-points `:` après le `for`. »

### 💬 3. Socratic — la maïeutique (pour intermédiaire)
- **Principe** : la méthode socratique — on ne donne pas la réponse, on pose des questions pour amener l'apprenant à la découvrir par lui-même. On apprend mieux ce qu'on construit.
- **Quand** : maîtrise de la compétence entre 0.4 et 0.7.
- **Déroulement** : l'agent ne donne **jamais** la réponse directement. Il guide par des questions de plus en plus précises, en s'adaptant à ton niveau.
- **Exemple** :
  > 👤 « Comment trier une liste en Python ? »
  > 🤖 « Avant de te donner la méthode, réfléchis : si tu devais trier des cartes dans ta main, comment t'y prendrais-tu ? … Et à ton avis, Python a-t-il déjà une fonction qui fait ce travail ? »

### 🎓 4. Feynman — apprendre en expliquant (pour avancé)
- **Principe** : la technique Feynman — si tu ne peux pas expliquer un concept simplement, c'est que tu ne le maîtrises pas assez. Expliquer révèle les lacunes.
- **Quand** : maîtrise de la compétence ≥ 0.7.
- **Déroulement** :
  1. L'agent t'invite à expliquer la notion « comme si j'avais 12 ans ».
  2. Tu rédiges ton explication.
  3. L'agent l'**évalue** (via `evaluate_feynman`), identifie les trous, et te donne un score.
  4. Ta maîtrise Leitner est mise à jour selon ce score.
- **Exemple** :
  > 🤖 « Explique-moi la récursivité comme si j'avais 12 ans. »
  > 👤 « C'est une fonction qui s'appelle elle-même… »
  > 🤖 « Bonne base ! Mais tu n'as pas mentionné le cas d'arrêt — sans lui, la fonction tourne à l'infini. Score : 0.6. »

### ✅ 5. Quiz — l'évaluation formative
- **Principe** : l'évaluation formative + la répétition espacée. Se tester active la mémoire et renforce la rétention bien mieux que la simple relecture.
- **Quand** : sur ta demande, ou proposé par l'agent après une explication.
- **Déroulement** : l'agent génère 3 questions à choix multiples, les affiche en **carte interactive**, tu réponds puis valides. Le score met à jour ta boîte Leitner (voir §5).
- **Exemple** : voir la section 5 ci-dessous.

### 🌐 6. Web search — la recherche d'actualité
- **Principe** : les connaissances du LLM ont une date de coupe. Pour l'actualité ou les infos récentes, on interroge le web en temps réel.
- **Quand** : question d'actualité détectée, ou quand tu actives le **toggle globe** 🌐 dans le chat.
- **Déroulement** : l'agent cherche sur DuckDuckGo, synthétise les résultats, et cite ses sources.
- **Exemple** :
  > 👤 (toggle 🌐 activé) « Quelle est la dernière version de Python ? »
  > 🤖 « D'après mes recherches, Python 3.14 est sorti en octobre 2025… [sources] »

### 🔁 7. Revision — la répétition espacée
- **Principe** : la courbe de l'oubli d'Ebbinghaus — on oublie vite si on ne révise pas. La répétition espacée programme des révisions juste avant l'oubli.
- **Quand** : quand des compétences ont une révision due (boîte Leitner arrivée à échéance), ou quand tu demandes « qu'est-ce que je dois réviser ? ».
- **Déroulement** : l'agent consulte les `next_review_at` en base et te propose un plan de révision priorisé.
- **Exemple** :
  > 👤 « Qu'est-ce que je dois réviser ? »
  > 🤖 « 2 révisions dues : les listes (boîte 2, à réviser aujourd'hui) et les dictionnaires (boîte 1, en retard). On commence par les dictionnaires ? »

### 🎨 8. Artifact — la génération de contenu visuel
- **Principe** : le double codage (Paivio) — on retient mieux une information quand elle est à la fois verbale et visuelle.
- **Quand** : quand tu demandes un schéma, un morceau de code ou un graphique.
- **Déroulement** : l'agent génère un artefact (schema / code / chart) affiché dans une carte dédiée.
- **Exemple** :
  > 👤 « Fais-moi un schéma du fonctionnement d'une classe. »
  > 🤖 (affiche une carte "Schema" avec le diagramme)

---

## 5. Le quiz interactif et la progression Leitner

**Avant** : le quiz générait 3 questions mais n'en évaluait qu'**une seule**, et le score n'était **jamais enregistré** (❌).
**Après le Correctif 2** : le quiz s'affiche en **artefact interactif**, tu réponds aux 3 questions, et le score **met à jour ta maîtrise**.

### Déroulement
1. Tu demandes un quiz (ou l'agent le propose).
2. L'agent génère **3 questions** et te les affiche dans une **carte interactive**.
3. Tu sélectionnes tes réponses et cliques **"Valider"**.
4. Le frontend calcule ton score et l'**envoie au backend** (`POST /api/chat/quiz-submit`).
5. Le backend met à jour ta **maîtrise Leitner** et te renvoie un **feedback adaptatif**.

### La répétition espacée Leitner
Chaque compétence a une **boîte Leitner** (0 à 5). Plus la boîte est haute, plus l'intervalle avant la prochaine révision est long :

| Boîte | Intervalle |
|---|---|
| 0 | 1 jour |
| 1 | 2 jours |
| 2 | 5 jours |
| 3 | 10 jours |
| 4 | 21 jours |
| 5 | 45 jours |

- **Bonne réponse** → la boîte monte (+1), le score de maîtrise augmente.
- **Mauvaise réponse** → la boîte descend (-1), le score baisse.
- Le score de maîtrise est une **moyenne pondérée** : `60% ancien + 40% nouveau`.

---

## 6. Le RAG avec double-check de pertinence

**Avant** : l'agent injectait le contexte de tes documents **sans vérifier** s'il était pertinent (❌ risque d'hallucination).
**Après le Correctif 5** : il vérifie la pertinence **avant** d'utiliser le contexte.

### Les 3 contrôles
1. **Un document existe-t-il ?** (géré par le router).
2. **Le chunk est-il assez proche ?** Recherche sémantique avec score. Si aucun chunk ne dépasse le seuil (`RAG_SEMANTIC_THRESHOLD = 0.3`), le contexte est rejeté.
3. **Le LLM confirme-t-il ?** Si `RAG_DOUBLE_CHECK_ENABLED`, un second LLM vérifie que les extraits répondent vraiment à la question.

### Si le contexte n'est pas pertinent
L'agent te répond **honnêtement** :
> « Je n'ai pas trouvé cette information dans tes documents. Je préfère ne pas inventer de réponse. Tu peux uploader un document (bouton +) ou activer la recherche web (icône globe). »

---

## 7. Le feedback adaptatif

**Avant** : après un échec, l'agent disait juste "❌ Incorrect" sans proposer d'aide (❌).
**Après le Correctif 4** : il propose une **prochaine étape adaptée**.

| Résultat | Feedback |
|---|---|
| Échec (score bas) | « Veux-tu que je t'explique cette notion plus simplement ? » |
| Réussite moyenne | « On continue sur cette lancée ? » |
| Réussite (score haut) | « Bien joué ! On approfondit, ou on passe à un quiz plus difficile ? » |

---

## 8. Structure du projet

```
test_python/
├── apps/
│   ├── api/                      # Backend FastAPI
│   │   ├── main.py               # Point d'entrée FastAPI
│   │   ├── config.py             # Configuration (seuils RAG, modèles…)
│   │   ├── agent/
│   │   │   ├── graph.py          # Construction du graphe LangGraph
│   │   │   ├── nodes.py          # Les 9 nœuds + prompts
│   │   │   ├── state.py          # État partagé (AgentState)
│   │   │   ├── studio_graph.py   # Version LangGraph Studio (local)
│   │   │   └── tools/
│   │   │       ├── quiz.py       # Génération + évaluation de quiz
│   │   │       ├── progress.py   # Maîtrise Leitner
│   │   │       ├── web_search.py # Recherche web
│   │   │       └── artifacts.py  # Schémas / code / graphiques
│   │   ├── services/
│   │   │   ├── agent_service.py  # Exécution du graphe (sync + streaming)
│   │   │   ├── model_manager.py  # Sélection des LLM par opération
│   │   │   └── streaming.py      # SSE streaming
│   │   ├── routes/
│   │   │   ├── chat.py           # /api/chat, /confirm, /quiz-submit
│   │   │   ├── sessions.py       # Gestion des sessions
│   │   │   ├── documents.py      # Upload + indexation PDF
│   │   │   ├── profile.py        # Profil apprenant
│   │   │   └── models.py         # Config des modèles
│   │   ├── rag/
│   │   │   ├── loader.py         # Chargement + chunking PDF
│   │   │   ├── retriever.py      # ChromaDB + retrieve_semantic
│   │   │   └── embeddings.py     # Embeddings locaux
│   │   └── db/
│   │       ├── crud.py           # Accès SQLite
│   │       ├── migrations.py     # Migrations V3 idempotentes
│   │       └── schema_v3.sql     # Schéma de base
│   └── web/                      # Frontend Next.js
│       ├── components/
│       │   ├── chat/             # ChatWindow, MessageBubble, Composer…
│       │   └── artifacts/        # QuizArtifact, ArtifactRenderer…
│       └── lib/
│           ├── api.ts            # Client API
│           └── types.ts          # Types TypeScript
├── docs/
│   ├── ARCHITECTURE.md           # Architecture validée
│   ├── LANGGRAPH_STUDIO.md       # Guide debug Studio
│   └── GUIDE_AGENT.md            # Ce guide
├── langgraph.json                # Config LangGraph Studio
├── start_api.py                  # Lanceur FastAPI
└── start_studio.ps1              # Lanceur LangGraph Studio
```

---

## 9. Les modèles LLM utilisés

L'agent utilise **plusieurs modèles** selon la tâche (via `ModelManager`) :

| Opération | Modèle par défaut | Pourquoi |
|---|---|---|
| chat / réponse | minimax-m3 (cloud) | Qualité de rédaction |
| quiz_generation | qwen2.5-coder:3b (local) | Rapide, structuré |
| feynman_eval | minimax-m3 (cloud) | Évaluation fine |
| diagnostic | minimax-m3 (cloud) | Estimation de niveau |
| relevance_check | qwen2.5-coder:3b (local) | Filtre de pertinence |
| artifact | kimi-k2.7-code (cloud) | Génération de code |

**Mode local** : si Ollama Cloud est indisponible (quota), l'agent bascule sur `qwen2.5-coder:3b` local pour toutes les opérations.

**LangGraph Studio** : utilise désormais les **modèles cloud** (`force_local=False` dans `studio_graph.py`, config dans `.env.studio`). ⚠️ Le debug en Studio consomme donc du quota Ollama Cloud. Pour revenir au 100 % local, remets `ModelManager(force_local=True)`.

---

## 10. Résumé des 5 correctifs pédagogiques

| # | Correctif | Impact |
|---|---|---|
| 1 | **Diagnostic réel** | Le niveau est estimé **après** tes réponses, pas deviné. |
| 2 | **Quiz multi-questions** | Les 3 questions sont évaluées et le score **met à jour ta maîtrise**. |
| 3 | **Méthode par compétence** | La méthode s'adapte à ta maîtrise du **sujet précis**, pas à ton niveau global. |
| 4 | **Feedback adaptatif** | Après chaque évaluation, l'agent propose une **prochaine étape**. |
| 5 | **Double-check RAG** | Le contexte n'est utilisé que s'il est **réellement pertinent**. |

---

## 11. Pour aller plus loin

- **Debugger le graphe** : voir `docs/LANGGRAPH_STUDIO.md` (LangGraph Studio sur le port 2024).
- **Architecture détaillée** : voir `docs/ARCHITECTURE.md`.
- **Lancer le backend** : `python -m uvicorn apps.api.main:app --reload --port 8000`
- **Lancer le frontend** : `npm run dev` dans `apps/web` (port 3000).
- **Lancer Studio** : `.\start_studio.ps1` — utilise les **modèles cloud** (minimax-m3, kimi-k2.7-code). ⚠️ Consomme du quota Ollama Cloud ; les embeddings restent locaux.
