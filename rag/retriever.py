"""Retriever ChromaDB — création, chargement, ajout incrémental."""

from pathlib import Path
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings
import config


def _get_embedding(model_name: str = "qwen3-embedding:0.6b"):
    """Instancie les embeddings Ollama (local ou distant)."""
    kwargs = {"model": model_name}

    # Si serveur distant configuré, utiliser la base URL et les headers
    if config.OLLAMA_BASE_URL:
        kwargs["base_url"] = config.OLLAMA_BASE_URL
    if config.OLLAMA_API_KEY:
        kwargs["headers"] = {
            "Authorization": f"Bearer {config.OLLAMA_API_KEY}",
        }

    return OllamaEmbeddings(**kwargs)


def create_retriever(splits: list, model_name: str = "qwen3-embedding:0.6b",
                     top_k: int = 3, persist_dir: str = None):
    """Crée un retriever ChromaDB à partir de documents chunkés."""
    embedding = _get_embedding(model_name)

    if persist_dir:
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embedding,
            persist_directory=persist_dir,
        )
    else:
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embedding,
        )

    return vectorstore.as_retriever(search_kwargs={"k": top_k})


def get_or_create_retriever(model_name: str = "qwen3-embedding:0.6b",
                            top_k: int = 3, persist_dir: str = None):
    """Charge un retriever existant, ou en crée un vide si le dossier n'existe pas."""
    embedding = _get_embedding(model_name)

    if persist_dir and Path(persist_dir).exists():
        vectorstore = Chroma(
            persist_directory=persist_dir,
            embedding_function=embedding,
        )
    else:
        # Créer un vectorstore vide avec un document placeholder
        from langchain_core.documents import Document
        vectorstore = Chroma.from_documents(
            documents=[Document(page_content="placeholder", metadata={"source": "init"})],
            embedding=embedding,
            persist_directory=persist_dir,
        )
        # Supprimer le placeholder
        if persist_dir:
            ids = vectorstore.get()["ids"]
            if ids:
                vectorstore.delete(ids=ids[:1])

    return vectorstore.as_retriever(search_kwargs={"k": top_k})


def add_documents_to_retriever(splits: list, model_name: str = "qwen3-embedding:0.6b",
                               top_k: int = 3, persist_dir: str = None):
    """Ajoute des documents au vectorstore existant (ou en crée un nouveau)."""
    embedding = _get_embedding(model_name)

    if persist_dir and Path(persist_dir).exists():
        vectorstore = Chroma(
            persist_directory=persist_dir,
            embedding_function=embedding,
        )
        vectorstore.add_documents(splits)
    else:
        if persist_dir:
            Path(persist_dir).mkdir(parents=True, exist_ok=True)
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embedding,
            persist_directory=persist_dir,
        )

    return vectorstore.as_retriever(search_kwargs={"k": top_k})
