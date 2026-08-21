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
    """Liste toutes les sessions ouvertes."""
    with db.get_connection(config.DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, langgraph_thread_id, started_at, ended_at FROM session ORDER BY started_at DESC"
        ).fetchall()
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
    }
    return badges.get(method, "")


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
            label = f"Session #{s['id']} — {s['started_at'][:16]}"
            if s["ended_at"]:
                label += " (closee)"
            col1, col2 = st.columns([5, 1])
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

                try:
                    agent_graph = _get_agent_graph(selected_model)
                    result = agent_graph.invoke(
                        {"question": question}, config=thread_config
                    )
                    answer = result.get(
                        "answer", "Desole, je n'ai pas pu generer de reponse."
                    )
                    method = result.get("method", "")
                except Exception as e:
                    answer = f"Erreur: {e}"
                    method = ""

                status.update(label="Termine", state="complete", expanded=False)

            badge = _method_badge(method)
            if badge:
                st.caption(badge)

            st.markdown(answer)

        # Sauvegarder la réponse
        db.add_message(
            st.session_state.active_session_id, "assistant", answer,
            method_used=method,
            db_path=config.DB_PATH,
        )
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()


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
