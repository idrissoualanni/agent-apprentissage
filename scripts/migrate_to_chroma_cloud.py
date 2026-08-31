"""Migration : re-indexe les documents existants vers Chroma Cloud.

Usage :
    python -m scripts.migrate_to_chroma_cloud

Ce que fait le script :
1. Lit les documents connus de la DB (table document) et les PDFs du dossier.
2. Chunk les documents (si PDF present) ou reutilise le texte existant.
3. Upsert vers la collection cloud "agent_documents" avec embeddings serveur
   (dense qwen + sparse splade generes automatiquement par Chroma Cloud).
   Les IDs sont deterministes → relancer le script est idempotent.
4. Affiche un rapport (documents migres, chunks, erreurs).

Aucune donnee n'est supprimee : la collection locale reste intacte.
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_chroma")

# Permet l'execution directe : python scripts/migrate_to_chroma_cloud.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.api.rag.ingestion import load_pdf, chunk_documents  # noqa: E402
from apps.api.rag.retriever import (  # noqa: E402
    get_or_create_retriever,
    add_documents_to_retriever,
    _use_chroma_cloud,
)


def migrate(dry_run: bool = False) -> dict:
    import apps.api.config as config
    from apps.api.db import crud

    if not _use_chroma_cloud():
        logger.error(
            "CHROMA_API_KEY absente — la migration vers Chroma Cloud est "
            "impossible. Definis CHROMA_API_KEY (ou CHROMA_CLOUD_API_KEY)."
        )
        return {"migrated": 0, "chunks": 0, "errors": ["no cloud config"]}

    retriever = get_or_create_retriever(
        top_k=config.TOP_K, persist_dir=str(config.CHROMA_DIR)
    )
    before = retriever.count() if hasattr(retriever, "count") else -1

    docs_db = crud.list_documents(config.DB_PATH)
    pdf_files = sorted(config.PDF_DIR.glob("*.pdf"))

    report = {"migrated": 0, "chunks": 0, "errors": []}
    all_splits = []

    for pdf in pdf_files:
        try:
            docs = load_pdf(str(pdf))
            splits = chunk_documents(docs, config.CHUNK_SIZE,
                                     config.CHUNK_OVERLAP)
            # source_doc_id = nom de fichier (dedup group-by)
            for s in splits:
                s.metadata["source_doc_id"] = pdf.name
            all_splits.extend(splits)
            logger.info(f"Pret : {pdf.name} ({len(splits)} chunks)")
        except Exception as e:
            msg = f"Erreur lecture {pdf.name}: {e}"
            logger.error(msg)
            report["errors"].append(msg)

    if docs_db and not pdf_files:
        logger.info(
            f"{len(docs_db)} documents en base mais aucun PDF dans "
            f"{config.PDF_DIR} — les chunks ne peuvent pas etre re-embeddes."
        )

    if all_splits and not dry_run:
        added = add_documents_to_retriever(retriever, all_splits)
        report["chunks"] = added
        report["migrated"] = len(pdf_files)
        after = retriever.count() if hasattr(retriever, "count") else -1
        logger.info(f"Upsert {added} chunks (count: {before} → {after})")
    elif all_splits:
        report["chunks"] = len(all_splits)
        report["migrated"] = len(pdf_files)
        logger.info(f"[DRY RUN] {len(all_splits)} chunks prets a etre upsertes")

    return report


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    r = migrate(dry_run=dry)
    print(f"\nRapport: {r['migrated']} documents, {r['chunks']} chunks, "
          f"{len(r['errors'])} erreurs")
    sys.exit(1 if r["errors"] and not r["chunks"] else 0)
