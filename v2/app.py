"""Agent d'Apprentissage — Interface Streamlit V2."""

import streamlit as st
import json
import uuid
from pathlib import Path

import config
from db import db
from rag import ingestion, retriever as retriever_mod
from graph.graph import build_agent_graph
from tools.progress import get_progress_summary
from ui.renderers import render_quiz_html, render_feynman_html, render_artifact_html, render_confirmation_html

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agent d'Apprentissage",
    page_icon=":material/school:",
    layout="wide",
)

# ─── Init DB ────────────────────────────────────────────────────────────────
db.init_db(config.DB_PATH)

# ─── Session state init ─────────────────────────────────────────────────────
st.session_state.setdefault("active_session_id", None)
st.session_state.setdefault("nav_page", "chat")
st.session_state.setdefault("messages", [])  # messages de la session active
st.session_state.setdefault("pending_confirmation", False)
st.session_state.setdefault("confirmation_type", "")
st.session_state.setdefault("confirmation_prompt", "")
st.session_state.setdefault("last_result", {})


# ═══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE — ChromaDB persistant + ingestion incrémentale
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def _get_retriever(model_name: str):
    """Charge le retriever depuis ChromaDB persistant (ou en crée un vide)."""
    return retriever_mod.get_or_create_retriever(
        model_name=config.OLLAMA_EMBEDDING_MODEL,
        top_k=config.TOP_K,
        persist_dir=str(config.CHROMA_DIR),
    )


def _index_pending_pdfs():
    """Index les PDFs qui n'ont pas encore de chunks en base."""
    docs_db = db.list_documents(config.DB_PATH)
    docs_indexed = {d["filename"] for d in docs_db if d.get("num_chunks", 0) > 0}
    pdf_files = list(config.PDF_DIR.glob("*.pdf"))
    pending = [f for f in pdf_files if f.name not in docs_indexed]

    if not pending:
        return 0

    all_splits = []
    for pdf_file in pending:
        splits = ingestion.ingest_pdf(
            str(pdf_file),
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )
        # Mettre à jour le doc en base
        db.create_document(
            filename=pdf_file.name,
            file_path=str(pdf_file),
            num_chunks=len(splits),
            db_path=config.DB_PATH,
        )
        all_splits.extend(splits)

    if all_splits:
        retriever_mod.add_documents_to_retriever(
            splits=all_splits,
            model_name=config.OLLAMA_EMBEDDING_MODEL,
            top_k=config.TOP_K,
            persist_dir=str(config.CHROMA_DIR),
        )
        # Invalider le cache du retriever pour inclure les nouveaux docs
        _get_retriever.clear()

    return len(pending)


@st.cache_resource(show_spinner=False)
def _get_agent_graph(model_name: str):
    """Construit et compile le StateGraph (une seule fois par modèle)."""
    retriever = _get_retriever(model_name)
    return build_agent_graph(retriever, model_name, config.DB_PATH)


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _create_new_session(model_name: str, domain: str) -> int:
    """Crée une nouvelle session avec un thread_id unique (UUID)."""
    thread_id = f"agent_{model_name}_{domain}_{uuid.uuid4().hex[:8]}"
    return db.create_session(thread_id, config.DB_PATH)


def _get_or_create_session(thread_id: str) -> int:
    """Récupère ou crée une session par thread_id."""
    with db.get_connection(config.DB_PATH) as conn:
        existing = conn.execute(
            "SELECT id FROM session WHERE langgraph_thread_id = ?",
            (thread_id,),
        ).fetchone()
        if existing:
            return existing["id"]
    return db.create_session(thread_id, config.DB_PATH)


def _load_session_messages(session_id: int) -> list:
    """Charge les messages d'une session."""
    return db.get_session_messages(session_id, config.DB_PATH)


def _list_all_sessions() -> list:
    """Liste toutes les sessions avec statistiques : nb messages, dernière méthode, aperçu."""
    with db.get_connection(config.DB_PATH) as conn:
        rows = conn.execute("""
            SELECT
                s.id,
                s.langgraph_thread_id,
                s.started_at,
                s.ended_at,
                COUNT(m.id) AS message_count,
                SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) AS user_count,
                SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) AS assistant_count,
                (
                    SELECT method_used FROM message
                    WHERE session_id = s.id AND method_used IS NOT NULL AND method_used != ''
                    ORDER BY created_at DESC LIMIT 1
                ) AS last_method,
                (
                    SELECT content FROM message
                    WHERE session_id = s.id AND role = 'user'
                    ORDER BY created_at DESC LIMIT 1
                ) AS last_user_msg
            FROM session s
            LEFT JOIN message m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.started_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def _delete_session(session_id: int):
    """Supprime une session et ses messages."""
    with db.get_connection(config.DB_PATH) as conn:
        conn.execute("DELETE FROM message WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM session WHERE id = ?", (session_id,))


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _method_badge(method: str) -> str:
    badges = {
        "socratique": ":material/psychology: Socratique",
        "socratic": ":material/psychology: Socratique",
        "feynman": ":material/record_voice_over: Feynman",
        "scaffold": ":material/escalator: Scaffolding",
        "diagnostic": ":material/biotech: Diagnostic",
        "quiz": ":material/quiz: Quiz",
        "artifact": ":material/draw: Artefact",
        "web_search": ":material/language: Recherche Web",
        "revision": ":material/event: Revision",
    }
    return badges.get(method, "")


def _render_answer(answer: str, method: str, result: dict):
    """Affiche la réponse avec le renderer HTML adapté si possible."""
    import streamlit.components.v1 as components

    if method == "quiz" and result.get("quiz_questions"):
        html = render_quiz_html(result["quiz_questions"], quiz_id="qz")
        components.html(html, height=400, scrolling=True)
        return

    if method == "feynman":
        topic = result.get("active_competency", result.get("feynman_topic", "cette notion"))
        score = result.get("feynman_score")
        feedback = answer if score is not None else None
        html = render_feynman_html(topic=topic, feedback=feedback, score=score)
        components.html(html, height=350, scrolling=True)
        return

    if method == "artifact":
        # Extraire titre + contenu depuis le markdown généré
        lines = answer.split("\n", 2)
        title = lines[0].replace("### :material/draw: ", "").strip() if lines else "Artefact"
        content = lines[2] if len(lines) > 2 else answer
        html = render_artifact_html(title=title, content=content,
                                    artifact_type=result.get("tool_result", "schema"))
        components.html(html, height=500, scrolling=True)
        return

    # Fallback : markdown classique
    st.markdown(answer)


def _sync_chroma_with_db():
    """Vérifie que les docs en DB ont bien des chunks dans ChromaDB, et réindexe si nécessaire."""
    pending_count = _index_pending_pdfs()
    return pending_count


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## :material/school: Agent d'Apprentissage")
    st.space("small")

    # Navigation
    page = st.segmented_control(
        "Navigation",
        [
            ":material/chat: Chat",
            ":material/bar_chart: Dashboard",
            ":material/upload: Import PDF",
            ":material/history: Historique",
            ":material/settings: Profil",
            ":material/database: DB",
        ],
        default=":material/chat: Chat",
        label_visibility="collapsed",
    )
    page_map = {
        ":material/chat: Chat": "chat",
        ":material/bar_chart: Dashboard": "dashboard",
        ":material/upload: Import PDF": "upload",
        ":material/history: Historique": "history",
        ":material/settings: Profil": "settings",
        ":material/database: DB": "db",
    }
    st.session_state.nav_page = page_map.get(page, "chat")

    st.divider()

    # Modèle
    selected_model = st.selectbox(
        "Modele Ollama",
        config.AVAILABLE_MODELS,
        index=config.AVAILABLE_MODELS.index(config.OLLAMA_MODEL)
        if config.OLLAMA_MODEL in config.AVAILABLE_MODELS
        else 0,
        label_visibility="collapsed",
    )

    st.divider()

    # Profil
    profile = db.get_profile(config.DB_PATH)
    domain = profile.get("domain", "")
    niveau = profile.get("niveau_global", "")
    if domain:
        st.caption(f":material/folder: **Domaine** {domain}")
    if niveau:
        st.caption(f":material/signal_cellular_alt: **Niveau** {niveau}")
    if not domain:
        st.caption(":material/warning: Domaine non defini — va dans Profil")

    st.divider()

    # Indexation bg
    pending = [f for f in config.PDF_DIR.glob("*.pdf")
               if f.name not in {d["filename"] for d in db.list_documents(config.DB_PATH) if d.get("num_chunks", 0) > 0}]
    if pending:
        with st.status(f":material/hourglass_top: {len(pending)} PDF(s) a indexer...", expanded=False) as status:
            try:
                count = _index_pending_pdfs()
                status.update(label=f":material/check_circle: {count} PDF(s) indexes", state="complete")
                st.rerun()
            except Exception as e:
                status.update(label=f":material/error: Erreur indexation", state="error")
                st.error(str(e))
    else:
        st.caption(":material/check_circle: Tous les PDFs sont indexes")

    st.divider()

    # ─── Sessions ────────────────────────────────────────────────────────────
    st.markdown("### :material/forum: Sessions")

    # Bouton nouvelle session
    if st.button(":material/add: Nouvelle session", width="stretch", key="new_session"):
        profile = db.get_profile(config.DB_PATH)
        domain = profile.get("domain", "default")
        session_id = _create_new_session(selected_model, domain)
        st.session_state.active_session_id = session_id
        st.session_state.messages = []
        st.rerun()

    sessions = _list_all_sessions()
    if sessions:
        for s in sessions:
            # Header de la session
            nb = s.get("message_count", 0) or 0
            last_method = s.get("last_method") or ""
            badge = _method_badge(last_method) if last_method else ""
            status = " (fermée)" if s["ended_at"] else ""
            label = f"**#{s['id']}** — {s['started_at'][:16]}{status}"
            if nb:
                label += f"  ·  {nb} msg"
            if badge:
                label += f"\n{badge}"

            col1, col2 = st.columns([6, 1])
            with col1:
                if st.button(
                    label,
                    key=f"session_{s['id']}",
                    width="stretch",
                    type="primary" if st.session_state.active_session_id == s["id"] else "secondary",
                ):
                    st.session_state.active_session_id = s["id"]
                    st.session_state.messages = _load_session_messages(s["id"])
                    st.rerun()
                # Aperçu du dernier message utilisateur
                preview = (s.get("last_user_msg") or "").strip()
                if preview:
                    short = (preview[:60] + "…") if len(preview) > 60 else preview
                    st.caption(f"💬 _{short}_")
            with col2:
                if st.button(":material/delete:", key=f"del_session_{s['id']}"):
                    _delete_session(s["id"])
                    if st.session_state.active_session_id == s["id"]:
                        st.session_state.active_session_id = None
                        st.session_state.messages = []
                    st.rerun()
    else:
        st.caption("Aucune session")

    st.divider()
    st.caption(f":material/vector_spread: Embedding: `{config.OLLAMA_EMBEDDING_MODEL}`")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: CHAT
# ═══════════════════════════════════════════════════════════════════════════════

if st.session_state.nav_page == "chat":
    st.title(":material/chat: Assistant d'Apprentissage")

    # Vérifier qu'une session est active
    if not st.session_state.active_session_id:
        profile = db.get_profile(config.DB_PATH)
        domain = profile.get("domain", "default")
        st.session_state.active_session_id = _create_new_session(selected_model, domain)
        st.session_state.messages = []

    messages = st.session_state.messages

    # Messages existants
    for msg in messages:
        avatar = ":material/person:" if msg["role"] == "user" else ":material/smart_toy:"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    # Suggestions avant premier message
    if not messages:
        st.caption("Pose une question ou choisis une suggestion pour commencer.")
        suggestions = [
            ("Resume le document", "Resume les points cles du document importe"),
            ("Teste-moi", "Genere un quiz de 3 questions sur le document"),
            ("Explique simplement", "Explique le concept principal comme si j'avais 12 ans"),
        ]
        cols = st.columns(3)
        for i, (label, prompt_text) in enumerate(suggestions):
            if cols[i].button(label, width="stretch", key=f"suggestion_{i}"):
                db.add_message(
                    st.session_state.active_session_id, "user", prompt_text,
                    db_path=config.DB_PATH,
                )
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

    # Chat input
    if question := st.chat_input("Pose ta question...", submit_mode="disable"):
        # Ajouter le message user
        db.add_message(
            st.session_state.active_session_id, "user", question,
            db_path=config.DB_PATH,
        )
        st.session_state.messages.append({"role": "user", "content": question})

        with st.chat_message("user", avatar=":material/person:"):
            st.markdown(question)

        with st.chat_message("assistant", avatar=":material/smart_toy:"):
            with st.status("Reflexion en cours...", expanded=True) as status:
                st.write(f":material/model_training: Modele: `{selected_model}`")
                st.write(":material/search: Recherche dans les documents...")

                # Récupérer le thread_id depuis la session active
                with db.get_connection(config.DB_PATH) as conn:
                    row = conn.execute(
                        "SELECT langgraph_thread_id FROM session WHERE id = ?",
                        (st.session_state.active_session_id,),
                    ).fetchone()
                    thread_id = row["langgraph_thread_id"] if row else f"agent_{selected_model}_{uuid.uuid4().hex[:8]}"
                thread_config = {"configurable": {"thread_id": thread_id}}

                result = {}
                try:
                    agent_graph = _get_agent_graph(selected_model)
                    result = agent_graph.invoke(
                        {"question": question, "thread_id": thread_id},
                        config=thread_config,
                    )
                    answer = result.get(
                        "answer", "Desole, je n'ai pas pu generer de reponse."
                    )
                    method = result.get("method", "")
                except Exception as e:
                    answer = f"Erreur: {e}"
                    method = ""

                status.update(label="Termine", state="complete", expanded=False)

            # ─── Human-in-the-loop : stocker et stopper ───
            if result.get("pending_confirmation"):
                st.session_state.pending_confirmation = True
                st.session_state.confirmation_type = result.get("confirmation_type", "")
                st.session_state.confirmation_prompt = result.get("confirmation_prompt", "")
                st.session_state.last_result = result
                st.stop()

            # ─── Affichage normal (avec renderers HTML si applicable) ───
            badge = _method_badge(method)
            if badge:
                st.caption(badge)

            _render_answer(answer, method, result)

        # Sauvegarder la réponse
        db.add_message(
            st.session_state.active_session_id, "assistant", answer,
            method_used=method,
            db_path=config.DB_PATH,
        )
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

    # ═══════════════════════════════════════════════════════════════════════
    # HITL : afficher les boutons si pending_confirmation (EN DEHORS de chat_input)
    # ═══════════════════════════════════════════════════════════════════════
    if st.session_state.pending_confirmation:
        st.info(st.session_state.confirmation_prompt)

        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button(":material/check: Oui, c'est parti !", key="conf_yes", width="stretch"):
                with db.get_connection(config.DB_PATH) as conn:
                    row = conn.execute(
                        "SELECT langgraph_thread_id FROM session WHERE id = ?",
                        (st.session_state.active_session_id,),
                    ).fetchone()
                    thread_id = row["langgraph_thread_id"] if row else f"agent_{selected_model}_{uuid.uuid4().hex[:8]}"
                thread_config = {"configurable": {"thread_id": thread_id}}
                agent_graph = _get_agent_graph(selected_model)
                result = agent_graph.invoke(
                    {"user_confirmed": True, "thread_id": thread_id},
                    config=thread_config,
                )
                answer = result.get("answer", "")
                method = result.get("method", "")
                st.session_state.messages.append({"role": "assistant", "content": answer})
                db.add_message(
                    st.session_state.active_session_id, "assistant", answer,
                    method_used=method, db_path=config.DB_PATH,
                )
                st.session_state.pending_confirmation = False
                st.rerun()
        with col_no:
            if st.button(":material/close: Non, pas maintenant", key="conf_no", width="stretch"):
                with db.get_connection(config.DB_PATH) as conn:
                    row = conn.execute(
                        "SELECT langgraph_thread_id FROM session WHERE id = ?",
                        (st.session_state.active_session_id,),
                    ).fetchone()
                    thread_id = row["langgraph_thread_id"] if row else f"agent_{selected_model}_{uuid.uuid4().hex[:8]}"
                thread_config = {"configurable": {"thread_id": thread_id}}
                agent_graph = _get_agent_graph(selected_model)
                result = agent_graph.invoke(
                    {"user_confirmed": False, "thread_id": thread_id},
                    config=thread_config,
                )
                answer = result.get("answer", "Pas de souci !")
                method = result.get("method", "")
                st.session_state.messages.append({"role": "assistant", "content": answer})
                db.add_message(
                    st.session_state.active_session_id, "assistant", answer,
                    method_used=method, db_path=config.DB_PATH,
                )
                st.session_state.pending_confirmation = False
                st.rerun()
        st.stop()  # On ne continue pas tant que l'utilisateur n'a pas répondu


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

elif st.session_state.nav_page == "dashboard":
    st.title(":material/bar_chart: Tableau de Progression")

    profile = db.get_profile(config.DB_PATH)
    domain = profile.get("domain", "")

    if not domain:
        st.warning("Definis d'abord un domaine dans :material/settings: Profil.")
        st.stop()

    try:
        summary_str = get_progress_summary.invoke({"domain": domain})
        summary = json.loads(summary_str)
    except Exception as e:
        st.error(f"Erreur chargement progression: {e}")
        st.stop()

    cols = st.columns(4)
    cols[0].metric("Competences", summary["total_competencies"])
    cols[1].metric("Score moyen", f"{summary['average_score']:.0%}")
    cols[2].metric("Acquises", summary["acquired"])
    cols[3].metric("A reviser", summary["due_for_review"])

    st.divider()

    overview = db.get_mastery_overview(domain, config.DB_PATH)
    if overview:
        import plotly.graph_objects as go

        names = [c["nom"] for c in overview]
        scores = [c["score"] for c in overview]
        colors = [
            "#22c55e" if s >= 0.8 else "#f59e0b" if s >= 0.4 else "#ef4444"
            for s in scores
        ]

        fig = go.Figure(go.Bar(
            x=names, y=scores, marker_color=colors,
            text=[f"{s:.0%}" for s in scores],
            textposition="outside",
        ))
        fig.update_layout(
            title="Maitrise par competence",
            xaxis_title="Competence", yaxis_title="Score",
            yaxis_range=[0, 1], height=400,
        )
        st.plotly_chart(fig, width="stretch")

        if summary["gaps"]:
            st.markdown("### :material/warning: Lacunes actives")
            for gap in summary["gaps"]:
                st.badge(f"{gap['nom']} — {gap['score']:.0%}", color="red")
    else:
        st.info("Aucune competence definie. Importe un PDF pour commencer.")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: UPLOAD PDF
# ═══════════════════════════════════════════════════════════════════════════════

elif st.session_state.nav_page == "upload":
    st.title(":material/upload: Import de Documents")

    uploaded = st.file_uploader(
        "Glisse un PDF ici ou clique pour selectionner",
        type=["pdf"],
    )

    if uploaded:
        save_path = config.PDF_DIR / uploaded.name
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())

        with st.spinner(f"Indexation de {uploaded.name}..."):
            try:
                splits = ingestion.ingest_pdf(
                    str(save_path),
                    chunk_size=config.CHUNK_SIZE,
                    chunk_overlap=config.CHUNK_OVERLAP,
                )
                doc_id = db.create_document(
                    filename=uploaded.name,
                    file_path=str(save_path),
                    num_chunks=len(splits),
                    db_path=config.DB_PATH,
                )
                # Ajouter au ChromaDB existant
                retriever_mod.add_documents_to_retriever(
                    splits=splits,
                    model_name=config.OLLAMA_EMBEDDING_MODEL,
                    top_k=config.TOP_K,
                    persist_dir=str(config.CHROMA_DIR),
                )
                _get_retriever.clear()  # Invalider le cache
                st.success(f"{uploaded.name} importe — {len(splits)} segments crees (ID: {doc_id})")
            except Exception as e:
                st.error(f"Erreur indexation: {e}")

        st.rerun()

    docs = db.list_documents(config.DB_PATH)
    if docs:
        st.markdown("### Documents importes")
        for d in docs:
            status_icon = ":material/check_circle:" if d.get("num_chunks", 0) > 0 else ":material/hourglass_top:"
            st.caption(f"{status_icon} **{d['filename']}** — {d.get('num_chunks', 0)} segments — {d['uploaded_at']}")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: PROFIL
# ═══════════════════════════════════════════════════════════════════════════════

elif st.session_state.nav_page == "settings":
    st.title(":material/settings: Profil Apprenant")

    profile = db.get_profile(config.DB_PATH)

    with st.form("profile_form"):
        domain = st.text_input(
            "Domaine d'apprentissage",
            value=profile.get("domain", ""),
            placeholder="ex: Mathematiques, Histoire, Python...",
        )
        niveau = st.selectbox(
            "Niveau estime",
            ["", "debutant", "intermediaire", "avance"],
            index=["", "debutant", "intermediaire", "avance"].index(
                profile.get("niveau_global", "")
            ),
        )
        submitted = st.form_submit_button("Sauvegarder", width="stretch")
        if submitted:
            db.update_profile(domain, niveau, config.DB_PATH)
            st.success("Profil mis a jour !")
            st.rerun()

    domain_val = profile.get("domain", "")
    if domain_val:
        st.divider()
        st.markdown("### Competences")
        comps = db.get_competencies(domain_val, config.DB_PATH)
        if comps:
            for c in comps:
                indent = "  " * (1 if c["parent_id"] else 0)
                st.caption(f"{indent}:material/check_circle: **{c['nom']}**")
        else:
            st.info("Aucune competence definie.")

        with st.expander("Ajouter une competence"):
            with st.form("add_comp"):
                nom = st.text_input("Nom de la competence")
                desc = st.text_area("Description (optionnel)")
                parent_id = st.selectbox(
                    "Parent (optionnel)",
                    [None] + [c["id"] for c in comps],
                    format_func=lambda x: next(
                        (c["nom"] for c in comps if c["id"] == x), "Aucun"
                    ),
                )
                if st.form_submit_button("Ajouter"):
                    db.create_competency(domain_val, nom, parent_id, desc, config.DB_PATH)
                    st.success("Competence ajoutee !")
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: HISTORIQUE DES SESSIONS
# ═══════════════════════════════════════════════════════════════════════════════

elif st.session_state.nav_page == "history":
    st.title(":material/history: Historique des Sessions")

    sessions = _list_all_sessions()

    if not sessions:
        st.info("Aucune session enregistrée. Pose une question dans le chat pour démarrer.")
        st.stop()

    # KPIs en haut
    total = len(sessions)
    total_msgs = sum((s.get("message_count") or 0) for s in sessions)
    closed = sum(1 for s in sessions if s["ended_at"])
    open_sessions = total - closed

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Sessions", total)
    k2.metric("Messages", total_msgs)
    k3.metric("Ouvertes", open_sessions)
    k4.metric("Fermées", closed)

    st.divider()

    # Filtres
    fc1, fc2, fc3 = st.columns([2, 2, 1])
    with fc1:
        search = st.text_input(
            "Recherche dans les messages",
            placeholder="mot-clé…",
            label_visibility="collapsed",
        )
    with fc2:
        method_filter = st.multiselect(
            "Méthode",
            ["socratique", "scaffold", "feynman", "quiz", "artifact", "diagnostic",
             "web_search", "revision"],
            default=[],
            label_visibility="collapsed",
        )
    with fc3:
        only_active = st.toggle("Actives seulement", value=False)

    # Appliquer les filtres
    filtered = []
    for s in sessions:
        if only_active and s["ended_at"]:
            continue
        last_m = s.get("last_method") or ""
        if method_filter and last_m not in method_filter:
            continue
        filtered.append(s)

    if search.strip():
        kw = search.strip().lower()
        keep = []
        for s in filtered:
            msgs = db.get_session_messages(s["id"], config.DB_PATH)
            if any(kw in (m.get("content") or "").lower() for m in msgs):
                keep.append(s)
        filtered = keep

    st.caption(f"{len(filtered)} session(s) affichée(s) sur {total}")

    # Tableau des sessions
    if filtered:
        rows_for_table = []
        for s in filtered:
            preview = (s.get("last_user_msg") or "").strip()
            short = (preview[:80] + "…") if len(preview) > 80 else preview
            thread_id = s.get("langgraph_thread_id") or ""
            model = thread_id.split("_")[1] if "_" in thread_id else "?"
            rows_for_table.append({
                "ID": s["id"],
                "Début": s["started_at"][:16],
                "Messages": s.get("message_count") or 0,
                "Dernière méthode": s.get("last_method") or "—",
                "Statut": "🔴 fermée" if s["ended_at"] else "🟢 active",
                "Dernier message": short or "—",
                "Modèle": model,
            })

        st.dataframe(
            rows_for_table,
            width="stretch",
            hide_index=True,
            use_container_width=True,
        )

        st.divider()
        st.markdown("### Détail d'une session")

        session_ids = [s["id"] for s in filtered]
        selected_id = st.selectbox(
            "Sélectionne une session",
            session_ids,
            format_func=lambda x: f"#{x} — {next((s['started_at'][:16] for s in filtered if s['id'] == x), '')}",
        )

        if selected_id:
            msgs = db.get_session_messages(selected_id, config.DB_PATH)
            st.caption(f"{len(msgs)} message(s)")

            ac1, ac2, ac3 = st.columns([1, 1, 4])
            with ac1:
                if st.button(":material/chat: Reprendre", width="stretch"):
                    st.session_state.active_session_id = selected_id
                    st.session_state.messages = msgs
                    st.session_state.nav_page = "chat"
                    st.rerun()
            with ac2:
                if st.button(":material/delete: Supprimer", width="stretch"):
                    _delete_session(selected_id)
                    if st.session_state.active_session_id == selected_id:
                        st.session_state.active_session_id = None
                        st.session_state.messages = []
                    st.rerun()

            st.divider()

            for m in msgs:
                role = m["role"]
                avatar = ":material/person:" if role == "user" else ":material/smart_toy:"
                with st.chat_message(role, avatar=avatar):
                    method = m.get("method_used") or ""
                    badge = _method_badge(method) if method else ""
                    if badge:
                        st.caption(badge)
                    st.markdown(m["content"])

            st.divider()
            export_text = f"Session #{selected_id} — {msgs[0]['created_at'] if msgs else ''}\n\n"
            for m in msgs:
                export_text += f"--- {m['role'].upper()} ({m['created_at']})"
                if m.get("method_used"):
                    export_text += f" [{m['method_used']}]"
                export_text += f" ---\n{m['content']}\n\n"
            st.download_button(
                ":material/download: Exporter en Markdown",
                data=export_text,
                file_name=f"session_{selected_id}.md",
                mime="text/markdown",
            )
    else:
        st.info("Aucune session ne correspond aux filtres.")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: DB EXPLORER
# ═══════════════════════════════════════════════════════════════════════════════

elif st.session_state.nav_page == "db":
    st.title(":material/database: Explorateur de Base de Donnees")

    import sqlite3 as _sqlite3

    tables_info = [
        ("learner_profile", "Profil apprenant"),
        ("competency", "Competences"),
        ("mastery", "Maitrise (Leitner)"),
        ("document", "Documents importes"),
        ("chunk", "Chunks indexes"),
        ("session", "Sessions"),
        ("message", "Messages"),
        ("quiz_attempt", "Tentatives quiz"),
        ("feynman_restitution", "Restitutions Feynman"),
    ]

    # Vue d'ensemble
    st.markdown("### Vue d'ensemble")
    cols = st.columns(3)
    for i, (table, label) in enumerate(tables_info):
        with _sqlite3.connect(str(config.DB_PATH)) as conn:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        cols[i % 3].metric(label, count)

    st.divider()

    # Sélecteur de table
    table_names = [t[0] for t in tables_info]
    selected_table = st.selectbox("Selectionne une table", table_names)

    if selected_table:
        st.markdown(f"### {selected_table}")
        with _sqlite3.connect(str(config.DB_PATH)) as conn:
            conn.row_factory = _sqlite3.Row
            rows = conn.execute(f"SELECT * FROM {selected_table} ORDER BY rowid DESC LIMIT 100").fetchall()

        if rows:
            # Convertir en liste de dicts
            data = [dict(r) for r in rows]
            st.dataframe(data, width="stretch", use_container_width=True)
        else:
            st.info("Table vide.")

    # Checkpoints LangGraph
    st.divider()
    st.markdown("### :material/history: Checkpoints LangGraph")
    checkpoint_db = config.CHECKPOINT_DB
    if checkpoint_db.exists():
        with _sqlite3.connect(str(checkpoint_db)) as conn:
            checkpoints = conn.execute(
                "SELECT thread_id, checkpoint_ns, checkpoint_id FROM checkpoint ORDER BY checkpoint_id DESC LIMIT 20"
            ).fetchall()
        if checkpoints:
            st.caption(f"{len(checkpoints)} checkpoint(s) recents:")
            for cp in checkpoints:
                st.code(f"thread={cp[0]}  ns={cp[1]}  id={cp[2]}", language=None)
        else:
            st.info("Aucun checkpoint enregistre.")
    else:
        st.info("Fichier checkpoints.db pas encore cree.")
