"""Modulo para eliminar todas las colecciones en Qdrant - Module to delete all collections in Qdrant."""
from src.qdrant.client import get_qdrant_client

def delete_all_collections():
    """RAG collections deleter - Función para eliminar todas las colecciones en Qdrant."""
    client = get_qdrant_client()

    try:

        collections_response = client.get_collections()
        colecciones = [col.name for col in collections_response.collections]

        if not colecciones:
            print("No hay colecciones para borrar.")
            return

        for nombre_col in colecciones:
            client.delete_collection(collection_name=nombre_col)
            print(f"Colección eliminada: {nombre_col}")

        print("\nTodas las colecciones han sido borradas")

    except Exception as e:
        print(f"Error al limpiar las colecciones: {e}")


def rag_deletor():
    """Backward-compatible alias for the former function name."""
    return delete_all_collections()
