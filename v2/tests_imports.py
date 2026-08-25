"""Test de la chaîne d'imports du projet."""
import sys
import time

print("Python:", sys.version)
print("Exe:", sys.executable)

t0 = time.time()
print("Import config...", flush=True)
import config
print(f"  OK ({time.time()-t0:.1f}s)", flush=True)

t0 = time.time()
print("Import db.db...", flush=True)
from db import db
print(f"  OK ({time.time()-t0:.1f}s)", flush=True)

t0 = time.time()
print("Import langchain_community.document_loaders...", flush=True)
try:
    from langchain_community.document_loaders import PyPDFLoader
    print(f"  OK ({time.time()-t0:.1f}s)", flush=True)
except Exception as e:
    print(f"  ERREUR : {type(e).__name__}: {e}", flush=True)

t0 = time.time()
print("Import rag.ingestion...", flush=True)
try:
    from rag import ingestion
    print(f"  OK ({time.time()-t0:.1f}s)", flush=True)
except Exception as e:
    print(f"  ERREUR : {type(e).__name__}: {e}", flush=True)

t0 = time.time()
print("Import rag.retriever...", flush=True)
try:
    from rag import retriever
    print(f"  OK ({time.time()-t0:.1f}s)", flush=True)
except Exception as e:
    print(f"  ERREUR : {type(e).__name__}: {e}", flush=True)

t0 = time.time()
print("Import graph.graph...", flush=True)
try:
    from graph.graph import build_agent_graph
    print(f"  OK ({time.time()-t0:.1f}s)", flush=True)
except Exception as e:
    print(f"  ERREUR : {type(e).__name__}: {e}", flush=True)

t0 = time.time()
print("Import tools.web_search...", flush=True)
try:
    from tools.web_search import web_search
    print(f"  OK ({time.time()-t0:.1f}s)", flush=True)
except Exception as e:
    print(f"  ERREUR : {type(e).__name__}: {e}", flush=True)
