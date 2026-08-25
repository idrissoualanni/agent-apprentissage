"""Script de démarrage FastAPI V3.

Usage :
    python start_api.py
    python start_api.py --port 8080
"""

import sys
import os
import argparse
from pathlib import Path

# Ajoute la racine au sys.path AVANT tout import
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="Lance FastAPI V3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("ERREUR : uvicorn non installé. pip install uvicorn")
        sys.exit(1)

    print(f"Démarrage FastAPI V3 sur http://{args.host}:{args.port}")
    print(f"Docs Swagger : http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "apps.api.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()