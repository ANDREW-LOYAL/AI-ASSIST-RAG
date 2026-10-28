"""Create configured Qdrant clients."""
from qdrant_client import QdrantClient

from src.config import QdrantConfig


def get_qdrant_client():
    """Return a client for the configured Qdrant service."""
    return QdrantClient(url=QdrantConfig.QDRANT_URL,
                        timeout=QdrantConfig.QDRANT_TIMEOUT)


def qdrant_conection():
    """Backward-compatible alias for older scripts."""
    return get_qdrant_client()
