"""Verifica la existencia y estado de la colección RAG en Qdrant(Discontinuado)"""
from src.config import QdrantConfig
from src.qdrant.client import get_qdrant_client

def verify_collections():
    """Verify the existence and state of the RAG collection in Qdrant."""
    print(f"-> Verificando colección '{QdrantConfig.COLLECTION_NAME}' en Qdrant...")

    client = get_qdrant_client()
    try:
        colecciones = client.get_collections().collections
        nombres_existentes = [col.name for col in colecciones]

        if QdrantConfig.COLLECTION_NAME not in nombres_existentes:
            print(f"¡ALERTA! La colección '{QdrantConfig.COLLECTION_NAME}' NO existe.")
            print(f"Colecciones disponibles en esta BD: {nombres_existentes}")
            return False

        info_col = client.get_collection(collection_name=QdrantConfig.COLLECTION_NAME)
        print("Colección encontrada.")
        print(f"Puntos totales almacenados: {info_col.points_count}")
        print(f"Dimensión del vector: {info_col.config.params.vectors.size}")

        if info_col.points_count == 0:
            print("ADVERTENCIA: La colección existe pero está VACÍA")
            return False

        # 3. Inspeccionar un punto de muestra para ver las llaves del payload
        muestra, _ = client.scroll(
            collection_name=QdrantConfig.COLLECTION_NAME,
            limit=1,
            with_payload=True
        )
        if muestra:
            print(f"""Claves de payload encontradas en el registro:
                  {list(muestra[0].payload.keys())}""")

        return True

    except ConnectionError as e:
        print(f"Error: {e}")
        return False
