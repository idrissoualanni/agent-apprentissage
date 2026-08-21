"""Ingestion de documents PDF — chunking hiérarchique + embeddings Ollama."""

import os
import re
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings


def load_pdf(pdf_path: str) -> list:
    """Charge un PDF et retourne les documents bruts."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Le fichier '{pdf_path}' est introuvable.")
    loader = PyPDFLoader(pdf_path)
    return loader.load()


def _detect_section_heuristic(text: str) -> str:
    """Tente d'extraire un titre de section depuis le texte d'un chunk."""
    # Patterns courants : "Chapter N", "1. Introduction", "SECTION 2", "Titre en majuscules"
    patterns = [
        r'^(?:Chapter|Chapitre|Section|Partie|Part)\s+\d+[.:]\s*(.+)',
        r'^\d+(?:\.\d+)*\.?\s+([A-Z].{3,60})',
        r'^([A-Z][A-Z\s]{4,60})\s*$',  # tout en majuscules = titre
    ]
    for pattern in patterns:
        match = re.match(pattern, text.strip(), re.MULTILINE)
        if match:
            return match.group(0).strip()[:80]
    return ""


def chunk_documents(docs: list, chunk_size: int = 1000,
                    chunk_overlap: int = 200) -> list:
    """Découpe les documents en segments.

    Stratégie :
    1. Tenter un chunking hiérarchique (par section via header_separator)
    2. Fallback sur RecursiveCharacterTextSplitter par taille fixe
    """
    # Tenter le chunking hiérarchique avec séparateur de sections
    section_separator = "\n\n"
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=[section_separator, "\n", ". ", " ", ""],
    )
    splits = splitter.split_documents(docs)

    # Enrichir chaque chunk avec un titre de section détecté
    for split in splits:
        if not split.metadata.get("section_title"):
            section = _detect_section_heuristic(split.page_content)
            if section:
                split.metadata["section_title"] = section

    return splits


def create_embeddings(model_name: str = "qwen3-embedding:0.6b"):
    """Crée l'objet d'embedding Ollama."""
    return OllamaEmbeddings(model=model_name)


def ingest_pdf(pdf_path: str, chunk_size: int = 1000,
               chunk_overlap: int = 200) -> list:
    """Pipeline complet : chargement → chunking."""
    docs = load_pdf(pdf_path)
    splits = chunk_documents(docs, chunk_size, chunk_overlap)
    print(f"   -> {len(splits)} segments créés depuis {Path(pdf_path).name}")
    return splits
