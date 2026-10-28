"""Generate query and document vectors with the configured Ollama model."""
from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

from src.config import OllamaConfig


@lru_cache(maxsize=1)
def _embedding_client():
    return OllamaEmbeddings(model=OllamaConfig.EMBEDDING_MODEL)


def embed_query(text):
    """Return an embedding for one search query."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("La consulta para generar embeddings no puede estar vacía.")
    return _embedding_client().embed_query(text)


def embed_documents(texts):
    """Return one embedding for each document chunk."""
    if not texts:
        return []
    return _embedding_client().embed_documents(texts)


def turn_question_in_embedding(question):
    """Backward-compatible Spanish name for query embedding generation."""
    return embed_query(question)
