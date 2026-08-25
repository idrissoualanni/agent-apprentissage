"""Ingestion de documents PDF — chunking hiérarchique + embeddings Ollama.

Port de V2 rag/ingestion.py pour FastAPI V3.
"""

import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_pdf(pdf_path: str) -> list:
    """Charge un PDF et retourne les documents bruts."""
    from langchain_community.document_loaders import PyPDFLoader

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Le fichier '{pdf_path}' est introuvable.")
    loader = PyPDFLoader(pdf_path)
    return loader.load()


def _detect_section_heuristic(text: str) -> str:
    """Tente d'extraire un titre de section depuis le texte d'un chunk."""
    patterns = [
        r'^(?:Chapter|Chapitre|Section|Partie|Part)\s+\d+[.:]\s*(.+)',
        r'^\d+(?:\.\d+)*\.?\s+([A-Z].{3,60})',
        r'^([A-Z][A-Z\s]{4,60})\s*$',
    ]
    for pattern in patterns:
        match = re.match(pattern, text.strip(), re.MULTILINE)
        if match:
            return match.group(0).strip()[:80]
    return ""


def chunk_documents(
    docs: list,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list:
    """Découpe les documents en segments."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    splits = splitter.split_documents(docs)

    for split in splits:
        if not split.metadata.get("section_title"):
            section = _detect_section_heuristic(split.page_content)
            if section:
                split.metadata["section_title"] = section

    return splits


def create_embeddings(model_name: str = "qwen3-embedding:0.6b"):
    """Crée l'objet d'embedding Ollama."""
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=model_name)


def ingest_pdf(
    pdf_path: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list:
    """Pipeline complet : chargement → chunking."""
    docs = load_pdf(pdf_path)
    splits = chunk_documents(docs, chunk_size, chunk_overlap)
    logger.info(f"{len(splits)} segments créés depuis {Path(pdf_path).name}")
    return splits
