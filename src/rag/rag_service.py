"""Coordinate embedding generation and vector retrieval for RAG."""
from src.config import QdrantConfig
from src.ollama.embeddings import embed_query
from src.qdrant.vector_search import search_in_rag


def rag_search(question, limit=None):
    """Embed a natural-language query and retrieve its closest chunks."""
    query_vector = embed_query(question)
    return search_in_rag(query_vector, limit or QdrantConfig.LIMIT)
