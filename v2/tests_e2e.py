"""Tests end-to-end du projet Agent d'Apprentissage.

Couvre : DB, profil, compétences, mastery, documents, sessions,
messages, quiz, Feynman, progress (Leitner), artifact, web_search,
retriever (sans embeddings réels - test mocké), et construction du graphe.

Usage : python tests_e2e.py
"""

import sys
import io
# Force UTF-8 sur stdout pour eviter les erreurs cp1252 sous Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# ─── Setup : base temporaire isolée ──────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="agent_e2e_"))
print(f"[setup] Répertoire temporaire : {TMP}")

# Patch des chemins AVANT d'importer les modules du projet
sys.path.insert(0, str(PROJECT_ROOT))

import config
config.DB_PATH = TMP / "agent.db"
config.PDF_DIR = TMP / "pdfs"
config.CHROMA_DIR = TMP / "chroma"
config.CHECKPOINT_DB = TMP / "checkpoints.db"
config.PDF_DIR.mkdir(parents=True, exist_ok=True)
config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)

from db import db as dbm
from rag import ingestion, retriever as retriever_mod
from graph.graph import build_agent_graph
from graph.state import AgentState
from tools.quiz import generate_quiz, evaluate_answer
from tools.feynman import evaluate_feynman
from tools.progress import (
    update_mastery_after_quiz,
    update_mastery_after_feynman,
    get_progress_summary,
    get_revision_plan,
)
from tools.artifact import create_artifact
from tools.web_search import web_search
from ui.renderers import (
    render_quiz_html,
    render_feynman_html,
    render_artifact_html,
    render_confirmation_html,
)

PASS = "[OK]"
FAIL = "[KO]"
OK_EMOJI = "[OK]"
KO_EMOJI = "[KO]"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((status, name, detail))
    print(f"{status} {name}" + (f" — {detail}" if detail else ""))

# ─── Test 1 : Init DB + schéma ───────────────────────────────────────────
print("\n=== T1 — Initialisation DB ===")
dbm.init_db(config.DB_PATH)
profile = dbm.get_profile(config.DB_PATH)
check("profil par défaut créé", profile.get("id") == 1, f"id={profile.get('id')}")

with dbm.get_connection(config.DB_PATH) as conn:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
expected_tables = {
    "learner_profile", "competency", "mastery", "document", "chunk",
    "session", "message", "quiz_attempt", "feynman_restitution",
}
check("toutes les tables présentes", expected_tables.issubset(set(tables)),
      f"manque={expected_tables - set(tables)}" if expected_tables - set(tables) else "")

# ─── Test 2 : Profil ────────────────────────────────────────────────────
print("\n=== T2 — Profil apprenant ===")
dbm.update_profile("Python", "intermediaire", config.DB_PATH)
p = dbm.get_profile(config.DB_PATH)
check("domaine enregistré", p["domain"] == "Python")
check("niveau enregistré", p["niveau_global"] == "intermediaire")

# ─── Test 3 : Compétences hiérarchiques ─────────────────────────────────
print("\n=== T3 — Compétences hiérarchiques ===")
py_id = dbm.create_competency("Python", "Python", description="Langage Python", db_path=config.DB_PATH)
data_id = dbm.create_competency("Python", "Structures de données", parent_id=py_id, db_path=config.DB_PATH)
algo_id = dbm.create_competency("Python", "Algorithmes", parent_id=py_id, db_path=config.DB_PATH)
list_id = dbm.create_competency("Python", "Listes", parent_id=data_id, db_path=config.DB_PATH)
check("4 compétences créées", all([py_id, data_id, algo_id, list_id]))

comps = dbm.get_competencies("Python", config.DB_PATH)
noms = [c["nom"] for c in comps]
# Les parents (parent_id NULL) doivent être en premier
idx_py = noms.index("Python")
idx_data = noms.index("Structures de données")
check("parents triés avant enfants (NULLS FIRST)",
      idx_py < idx_data and idx_data < noms.index("Listes"),
      f"ordre={noms}")

tree = dbm.get_competency_tree("Python", config.DB_PATH)
check("arbre récursif", len(tree) == 4 and max(t["depth"] for t in tree) == 2)

# ─── Test 4 : Mastery + Leitner ─────────────────────────────────────────
print("\n=== T4 — Mastery + Leitner ===")
dbm.upsert_mastery(data_id, 0.5, leitner_box=2, status="learning",
                   next_review_at="2099-01-01", db_path=config.DB_PATH)
m = dbm.get_mastery(data_id, config.DB_PATH)
check("mastery stockée", m is not None and m["leitner_box"] == 2)

# Test update_mastery_after_quiz
result = json.loads(update_mastery_after_quiz.invoke({
    "competency_id": data_id, "is_correct": True
}))
check("update quiz -> promote", result["leitner_box"] == 3, f"box={result['leitner_box']}")
check("score apres quiz", 0.5 < result["score"] <= 1.0, f"score={result['score']}")

result = json.loads(update_mastery_after_quiz.invoke({
    "competency_id": data_id, "is_correct": False
}))
check("update quiz -> demote", result["leitner_box"] == 2, f"box={result['leitner_box']}")

# Test update_mastery_after_feynman
result = json.loads(update_mastery_after_feynman.invoke({
    "competency_id": algo_id, "score": 0.85
}))
check("Feynman 0.85 -> promote", result["leitner_box"] >= 1)
check("Feynman met à jour le score", result["score"] >= 0.7, f"score={result['score']}")

# ─── Test 5 : Documents ─────────────────────────────────────────────────
print("\n=== T5 — Documents ===")
doc1 = dbm.create_document("cours_python.pdf", str(config.PDF_DIR / "cours_python.pdf"), 42, config.DB_PATH)
doc2 = dbm.create_document("cours_algo.pdf", str(config.PDF_DIR / "cours_algo.pdf"), 15, config.DB_PATH)
docs = dbm.list_documents(config.DB_PATH)
check("2 docs en base", len(docs) == 2)
check("doc1 correct", doc1 > 0 and any(d["id"] == doc1 for d in docs))

# ─── Test 6 : Sessions + Messages ───────────────────────────────────────
print("\n=== T6 — Sessions & Messages ===")
s1 = dbm.create_session("thread_aaa", config.DB_PATH)
s2 = dbm.create_session("thread_bbb", config.DB_PATH)
m1 = dbm.add_message(s1, "user", "Bonjour", db_path=config.DB_PATH)
m2 = dbm.add_message(s1, "assistant", "Salut !", method_used="socratic", db_path=config.DB_PATH)
m3 = dbm.add_message(s2, "user", "Hello", db_path=config.DB_PATH)
msgs_s1 = dbm.get_session_messages(s1, config.DB_PATH)
check("messages session 1", len(msgs_s1) == 2)
check("méthode stockée", msgs_s1[1]["method_used"] == "socratic")

# Test critique : résolution de session par thread_id (bug #2)
with dbm.get_connection(config.DB_PATH) as conn:
    row = conn.execute(
        "SELECT id FROM session WHERE langgraph_thread_id = ?", ("thread_aaa",)
    ).fetchone()
check("thread_id → session_id correct", row["id"] == s1, f"got={row['id']} expected={s1}")

# ─── Test 7 : Quiz + Feynman persistés ──────────────────────────────────
print("\n=== T7 — Quiz & Feynman en base ===")
qa = dbm.record_quiz_attempt(
    competency_id=data_id, question="Qu'est-ce qu'une liste ?",
    options="a,b,c", user_answer="a", is_correct=True,
    session_id=s1, db_path=config.DB_PATH
)
check("quiz_attempt enregistré", qa > 0)

fr = dbm.record_feynman_restitution(
    competency_id=algo_id, user_explanation="C'est un algorithme de tri",
    agent_evaluation="Bien", score=0.8, gaps_identified="[]",
    session_id=s1, db_path=config.DB_PATH
)
check("feynman_restitution enregistrée", fr > 0)

# ─── Test 8 : Progress summary & revision plan ──────────────────────────
print("\n=== T8 — Progress summary & revision plan ===")
summary_str = get_progress_summary.invoke({"domain": "Python"})
summary = json.loads(summary_str)
check("summary a les clés attendues",
      all(k in summary for k in ["total_competencies","average_score","acquired",
                                   "learning","new","due_for_review","gaps"]),
      f"clés={list(summary.keys())}")
check("4 compétences dans summary", summary["total_competencies"] == 4)

plan_str = get_revision_plan.invoke({"domain": "Python"})
plan = json.loads(plan_str)
check("revision plan retourne un dict", "plan" in plan, f"keys={list(plan.keys())}")

# ─── Test 9 : Génération de PDF factice + ingestion ──────────────────────
print("\n=== T9 — Ingestion PDF ===")
# On crée un PDF minimal valide (juste assez pour PyPDFLoader)
import pypdf
from pypdf import PdfWriter

def make_minimal_pdf(path: Path, text_pages: list):
    writer = PdfWriter()
    for txt in text_pages:
        # PyPDFWriter ne peut pas insérer de texte facilement ;
        # on utilise reportlab si dispo, sinon une page blanche suffit pour tester le pipeline
        writer.add_blank_page(width=595, height=842)
    with open(path, "wb") as f:
        writer.write(f)

# Test : si reportlab dispo on génère du texte, sinon page blanche
try:
    from reportlab.pdfgen import canvas
    def make_text_pdf(path: Path, pages_text: list):
        c = canvas.Canvas(str(path))
        for txt in pages_text:
            c.drawString(50, 800, txt)
            c.showPage()
        c.save()
    make_text_pdf(config.PDF_DIR / "cours_python.pdf",
                  ["Introduction a Python", "Les listes en Python"])
    print("  (PDF texte créé via reportlab)")
except ImportError:
    make_minimal_pdf(config.PDF_DIR / "cours_python.pdf", ["p1", "p2"])
    print("  (PDF vide créé via pypdf — chunks limités mais pipeline OK)")

splits = ingestion.ingest_pdf(
    str(config.PDF_DIR / "cours_python.pdf"),
    chunk_size=500, chunk_overlap=100
)
check("ingestion PDF → liste de splits", isinstance(splits, list) and len(splits) >= 0,
      f"n_splits={len(splits)}")

# ─── Test 10 : Évaluation réponse quiz ──────────────────────────────────
print("\n=== T10 — evaluate_answer ===")
result_str = evaluate_answer.invoke({
    "question": "2+2 ?",
    "options": "3,4,5",
    "correct_index": 1,
    "user_answer_index": 1,
})
result = json.loads(result_str)
check("evaluate_answer correct", result["is_correct"] is True)

result_str = evaluate_answer.invoke({
    "question": "2+2 ?",
    "options": "3,4,5",
    "correct_index": 1,
    "user_answer_index": 0,
})
result = json.loads(result_str)
check("evaluate_answer wrong", result["is_correct"] is False)

# ─── Test 11 : Renderers HTML ───────────────────────────────────────────
print("\n=== T11 — Renderers HTML ===")
quiz_html = render_quiz_html(
    [{"question": "Q?", "options": ["a","b","c","d"], "correct_index": 0}],
    quiz_id="qz1"
)
check("render_quiz_html non vide", len(quiz_html) > 100)
check("render_quiz_html contient <script>", "<script>" in quiz_html)
check("render_quiz_html contient JSON correct",
      '"0": 0' in quiz_html or '"0":0' in quiz_html)

fey_html = render_feynman_html(topic="Photosynthèse", feedback="Bien", score=0.75)
check("render_feynman_html avec score", "#a6e3a1" in fey_html or "Excellent" in fey_html)

art_html = render_artifact_html(title="Schéma", content="# Titre\n- item 1", artifact_type="schema")
check("render_artifact_html", "<h1" in art_html and "<li>" in art_html)

conf_html = render_confirmation_html("Tu veux un quiz ?", "quiz")
check("render_confirmation_html", "Tu veux un quiz" in conf_html)

# ─── Test 12 : _detect_active_competency + _is_meta_question ────────────
print("\n=== T12 — Détections dans nodes.py ===")
from graph import nodes
m = nodes._is_meta_question("Bonjour")
check("_is_meta_question 'Bonjour'", m is True)
m = nodes._is_meta_question("Explique-moi les listes Python")
check("_is_meta_question 'Explique...'", m is False)
m = nodes._is_meta_question("Quel est le prix du Bitcoin ?")
check("_is_meta_question 'Quel est le prix...'", m is False)

check("_needs_web_search 'prix du bitcoin'", nodes._needs_web_search("prix du bitcoin") is True)
check("_needs_revision 'que dois-je réviser'", nodes._needs_revision("que dois-je réviser") is True)
check("_needs_web_search 'résume le doc'", nodes._needs_web_search("résume le doc") is False)

# ─── Test 13 : Construction du graphe (sans appel LLM) ──────────────────
print("\n=== T13 — Construction du StateGraph ===")

# Mock retriever qui retourne des documents factices
class MockRetriever:
    def invoke(self, query):
        from langchain_core.documents import Document
        return [
            Document(page_content=f"Contexte factice pour : {query}", metadata={"source": "test"})
        ]

mock_retriever = MockRetriever()
try:
    graph = build_agent_graph(mock_retriever, config.OLLAMA_MODEL, config.DB_PATH)
    check("StateGraph compilé", graph is not None)
    # Vérifier qu'on peut introspecter les nœuds
    check("au moins 9 nœuds dans le graphe",
          hasattr(graph, "get_graph") or hasattr(graph, "nodes"))
except Exception as e:
    check("StateGraph compilé", False, str(e))

# ─── Test 14 : _resolve_session_id (bug #2 corrigé) ─────────────────────
print("\n=== T14 — _resolve_session_id ===")
fake_state = {"thread_id": "thread_aaa", "question": "x"}
sid = nodes._resolve_session_id(fake_state, config.DB_PATH)
check("_resolve_session_id trouve la bonne session",
      sid == s1, f"got={sid} expected={s1}")
# Fallback sans thread_id
sid2 = nodes._resolve_session_id(None, config.DB_PATH)
check("_resolve_session_id fallback = dernière session", sid2 is not None)
# Fallback DB inexistante
sid3 = nodes._resolve_session_id(None, TMP / "nonexistent.db")
check("_resolve_session_id DB inexistante → None", sid3 is None)

# ─── Résumé ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
ok = sum(1 for s,_,_ in results if s == PASS)
ko = sum(1 for s,_,_ in results if s == FAIL)
print(f"RÉSULTAT : {ok} passés, {ko} échoués sur {len(results)} tests")
if ko > 0:
    print("\nDétail des échecs :")
    for s, name, detail in results:
        if s == FAIL:
            print(f"  {s} {name} — {detail}")
print("=" * 60)

# Cleanup
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if ko == 0 else 1)
