"""Diagnostic : inspecte la base de checkpoints et l'agent DB."""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent

print("=" * 70)
print("1. AGENT DB (db/agent.db)")
print("=" * 70)
agent_db = ROOT / "db" / "agent.db"
if agent_db.exists():
    conn = sqlite3.connect(str(agent_db))
    conn.row_factory = sqlite3.Row

    # Profil
    print("\n[learner_profile]")
    for r in conn.execute("SELECT * FROM learner_profile").fetchall():
        print(f"  id={r['id']} domain='{r['domain']}' niveau='{r['niveau_global']}'")

    # Compétences
    print("\n[competency]")
    n = 0
    for r in conn.execute("SELECT * FROM competency LIMIT 10").fetchall():
        print(f"  id={r['id']} domain='{r['domain']}' nom='{r['nom']}' parent={r['parent_id']}")
        n += 1
    if n == 0:
        print("  (vide)")

    # Sessions
    print("\n[session]")
    n = 0
    for r in conn.execute("SELECT * FROM session ORDER BY started_at DESC LIMIT 5").fetchall():
        print(f"  id={r['id']} thread_id='{r['langgraph_thread_id']}' started={r['started_at']}")
        n += 1
    print(f"  Total sessions: {conn.execute('SELECT COUNT(*) FROM session').fetchone()[0]}")

    # Messages
    print("\n[message] (5 derniers)")
    n = 0
    for r in conn.execute("SELECT * FROM message ORDER BY created_at DESC LIMIT 5").fetchall():
        print(f"  session_id={r['session_id']} role={r['role']} method={r['method_used']}")
        print(f"    content: {r['content'][:80]}...")
        n += 1
    print(f"  Total messages: {conn.execute('SELECT COUNT(*) FROM message').fetchone()[0]}")

    # Quiz attempts
    print("\n[quiz_attempt]")
    n = conn.execute("SELECT COUNT(*) FROM quiz_attempt").fetchone()[0]
    print(f"  Total: {n}")

    # Feynman
    print("\n[feynman_restitution]")
    n = conn.execute("SELECT COUNT(*) FROM feynman_restitution").fetchone()[0]
    print(f"  Total: {n}")

    # Mastery
    print("\n[mastery]")
    n = 0
    for r in conn.execute("SELECT * FROM mastery LIMIT 10").fetchall():
        print(f"  competency_id={r['competency_id']} score={r['score']} box={r['leitner_box']} status={r['status']}")
        n += 1
    if n == 0:
        print("  (vide)")

    conn.close()
else:
    print(f"  Fichier non trouvé : {agent_db}")

print("\n" + "=" * 70)
print("2. CHECKPOINT DB (checkpoints.db)")
print("=" * 70)
cp_db = ROOT / "checkpoints.db"
if cp_db.exists():
    sz = cp_db.stat().st_size
    print(f"  Taille : {sz} octets")
    conn = sqlite3.connect(str(cp_db))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    print(f"  Tables : {tables}")
    for t in tables:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"    {t}: {n} lignes")
        except Exception as e:
            print(f"    {t}: ERREUR {e}")

    if "checkpoints" in tables:
        print("\n[checkpoints] (5 derniers)")
        for r in conn.execute(
            "SELECT thread_id, checkpoint_ns, checkpoint_id, thread_ts "
            "FROM checkpoints ORDER BY thread_ts DESC LIMIT 5"
        ).fetchall():
            print(f"  thread={r[0][:30]}... ns={r[1]} ts={r[3]}")
    if "writes" in tables:
        n = conn.execute("SELECT COUNT(*) FROM writes").fetchone()[0]
        print(f"\n[writes] {n} entrees")
    conn.close()
else:
    print(f"  Fichier non trouvé : {cp_db}")

print("\n" + "=" * 70)
print("3. CHROMA DB (data/chroma)")
print("=" * 70)
chroma_dir = ROOT / "data" / "chroma"
if chroma_dir.exists():
    for f in chroma_dir.iterdir():
        print(f"  {f.name} ({f.stat().st_size if f.is_file() else 'dir'})")
else:
    print(f"  Répertoire non trouvé : {chroma_dir}")

print("\n" + "=" * 70)
print("4. PDF DIR (data/documents)")
print("=" * 70)
pdf_dir = ROOT / "data" / "documents"
if pdf_dir.exists():
    pdfs = list(pdf_dir.glob("*.pdf"))
    print(f"  {len(pdfs)} PDF(s) :")
    for p in pdfs:
        print(f"    {p.name} ({p.stat().st_size} octets)")
else:
    print(f"  Répertoire non trouvé : {pdf_dir}")
