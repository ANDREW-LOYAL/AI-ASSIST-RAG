"""Module to establish a connection with Qdrant - Módulo para establecer una conexión con Qdrant."""
from qdrant_client import QdrantClient
from src.config import QdrantConfig

def qdrant_conection():
    """Establece una conexión con Qdrant."""
    # QdrantClient connects lazily; let request errors propagate to the caller,
    # which can then report the failed file and leave it in the inbox for retry.
    return QdrantClient(url=QdrantConfig.QDRANT_URL)
