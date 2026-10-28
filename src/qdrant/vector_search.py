"""Retrieve active or legacy document chunks from Qdrant."""
from qdrant_client import models

from src.config import QdrantConfig
from src.qdrant.client import get_qdrant_client


def active_document_filter():
    """Include active chunks and pre-workflow chunks with no status field."""
    return models.Filter(
        should=[
            models.FieldCondition(
                key="index_status",
                match=models.MatchValue(value="active"),
            ),
            models.IsEmptyCondition(
                is_empty=models.PayloadField(key="index_status"),
            ),
        ]
    )


def search_in_rag(vector_pregunta, limit=10):
    """Search the collection and return the matching chunk text."""
    if not isinstance(vector_pregunta, list) or not vector_pregunta:
        raise ValueError("El vector de búsqueda no es válido o está vacío.")
    if not isinstance(limit, int) or limit <= 0:
        limit = QdrantConfig.LIMIT

    client = get_qdrant_client()
    response = client.query_points(
        collection_name=QdrantConfig.COLLECTION_NAME,
        query=vector_pregunta,
        query_filter=active_document_filter(),
        limit=limit,
        with_payload=True,
    )

    chunks = [
        point.payload.get("page_content", "")
        for point in response.points
        if point.payload and point.payload.get("page_content")
    ]
    return "\n\n---\n\n".join(chunks)
