"""RAG Main builder"""
from src.qdrant.question_emb import turn_question_in_embedding
from src.qdrant.rag_search import search_in_rag

def rag_search(question, limit=10):
    """Builder for RAG system """
        # 1. Convertir pregunta a embedding
    question_emb = turn_question_in_embedding(question)
    print(f"Embedding de la pregunta: {question_emb}")

        # 2. Buscar en Qdrant
    search_result = search_in_rag(question_emb, limit)
    print(f"Resultados de la búsqueda RAG: {search_result}")

    return search_result
