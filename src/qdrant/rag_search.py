"""Module for searching relevant fragments in Qdrant"""
from src.qdrant.qdrant_conector import qdrant_conection
from src.config import QdrantConfig

client = qdrant_conection()

def search_in_rag(vector_pregunta, limit):
    """Rag Data Search - Búsqueda de datos en RAG."""
    if not isinstance(vector_pregunta, list) or not vector_pregunta:
        print("ERROR: El vector de pregunta no es válido o está vacío.")
        return ""

    if not isinstance(limit, int) or limit <= 0:
        print("ADVERTENCIA: El límite de búsqueda (limit) debe ser un entero positivo.")
        limit = 5

    try:
        print("Buscando fragmentos relevantes en Qdrant...")
        result_qdrant = client.query_points(
            collection_name=QdrantConfig.COLLECTION_NAME,
            query=vector_pregunta,
            limit=limit
        ).points
    except ConnectionError as e:
        print(f"ERROR FATAL al consultar Qdrant: {e}.")
        return ""

    context_chunks = []
    for j in result_qdrant:
        text_chunk = j.payload.get("page_content", "")
        if text_chunk:
            context_chunks.append(text_chunk)

    if not context_chunks:
        print("ADVERTENCIA: Qdrant devolvió resultados, ninguno contenía 'page_content' válido.")
        return ""

    if context_chunks:
        contex_recived = "\n\n---\n\n".join(context_chunks)
        print(f"Contexto recuperado de Qdrant: {len(context_chunks)} fragmentos encontrados.")
        return contex_recived

    else:
        print("-> No se encontró contexto relevante en Qdrant (vacío).")
        return "No se encontró información relevante en la base de datos."
