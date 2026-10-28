"""Persist PDF chunks and verify complete document versions in Qdrant."""
import uuid
from collections import defaultdict
from qdrant_client import models
from src.config import OllamaConfig, QdrantConfig
from src.ollama.embeddings import embed_documents, embed_query
from src.qdrant.client import get_qdrant_client


def source_id_for_pdf(pdf_path):
    """Create a stable document identity from the normalized filename."""
    normalized_name = str(pdf_path.name).casefold()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"pdf-indexer:{normalized_name}"))


def current_pipeline_version():
    """Describe the extraction, chunking, and embedding recipe in use."""

    return (
        f"pdf-recursive-v1:chunk={QdrantConfig.CHUNK_SIZE}:overlap={QdrantConfig.CHUNK_OVERLAP}:"
        f"embedding={OllamaConfig.EMBEDDING_MODEL}"
    )


def _new_point_id(source_id, content_hash, pipeline_version, chunk_index):
    seed = f"{source_id}:{content_hash}:{pipeline_version}:{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def _legacy_point_id(source_id, source_hash, chunk_index):
    """Point ID format used by the former SQLite-manifest indexer."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{source_hash}:{chunk_index}"))


def _field_match(key, value):
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


class QdrantIndexStore:
    """Qdrant-backed index state and chunk persistence."""

    def __init__(self, client=None):
        if client is None:


            client = get_qdrant_client()
        self.client = client
        self.collection_name = QdrantConfig.COLLECTION_NAME
        self._collection_ready = False

    def ensure_collection(self):
        """Create the collection if needed and validate embedding dimensions."""
        if self._collection_ready:
            return
        vector_size = len(embed_query("dimension check"))
        if vector_size == 0:
            raise ValueError("El modelo de embeddings devolvió un vector vacío.")

        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        else:
            collection = self.client.get_collection(self.collection_name)
            vectors_config = collection.config.params.vectors
            stored_size = getattr(vectors_config, "size", None)
            if stored_size != vector_size:
                raise ValueError(
                    f"La colección '{self.collection_name}' usa vectores de "
                    f"{stored_size} dimensiones, pero '{OllamaConfig.EMBEDDING_MODEL}' "
                    f"devuelve {vector_size}. Corrige o recrea la colección antes de indexar."
                )

        self._ensure_payload_indexes()
        self._collection_ready = True

    def _ensure_payload_indexes(self):
        collection = self.client.get_collection(self.collection_name)
        payload_schema = collection.payload_schema or {}
        for field_name in ("source_id", "source_hash", "content_hash", "pipeline_version", "index_status"):
            if field_name not in payload_schema:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                    wait=True,
                )

    def _scroll(self, scroll_filter):
        offset = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=scroll_filter,
                limit=QdrantConfig.SCROLL_PAGE_SIZE,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            yield from points
            if next_offset is None:
                break
            offset = next_offset

    @staticmethod
    def _group_by_source(points):
        groups = defaultdict(list)
        for point in points:
            payload = point.payload or {}
            source_id = payload.get("source_id")
            if source_id:
                groups[source_id].append(point)
        return groups

    @staticmethod
    def _is_complete(points, expected_count):
        if len(points) != expected_count:
            return False
        expected_indices = set(range(expected_count))
        indices = set()
        for point in points:
            payload = point.payload or {}
            if payload.get("chunk_count") != expected_count:
                return False
            chunk_index = payload.get("chunk_index")
            if not isinstance(chunk_index, int):
                return False
            indices.add(chunk_index)
        return indices == expected_indices

    def find_complete_version(self, content_hash, pipeline_version, expected_count):
        """Find a complete version, even if its final activation was interrupted."""
        query_filter = models.Filter(
            must=[
                _field_match("content_hash", content_hash),
                _field_match("pipeline_version", pipeline_version),
            ]
        )
        groups = self._group_by_source(list(self._scroll(query_filter)))
        for source_id, points in groups.items():
            if self._is_complete(points, expected_count):
                point_ids = [point.id for point in points]
                self.activate_version(source_id, content_hash, pipeline_version)
                return source_id, point_ids
        return None

    def reconcile_legacy_version(
        self,
        source_id,
        source_hash,
        content_hash,
        chunks,
        pipeline_version,
    ):
        """Validate old points by deterministic IDs, then enrich their payloads."""
        legacy_filter = models.Filter(
            must=[
                models.IsEmptyCondition(
                    is_empty=models.PayloadField(key="content_hash")
                ),
            ],
            should=[
                _field_match("source_hash", source_hash),
                _field_match("source_id", source_id),
            ],
        )
        legacy_groups = defaultdict(list)
        for point in self._scroll(legacy_filter):
            payload = point.payload or {}
            candidate_source_id = payload.get("source_id")
            candidate_source_hash = payload.get("source_hash")
            if candidate_source_id and candidate_source_hash:
                legacy_groups[(candidate_source_id, candidate_source_hash)].append(point)

        for (legacy_source_id, legacy_source_hash), _points in legacy_groups.items():
            expected_ids = [
                _legacy_point_id(legacy_source_id, legacy_source_hash, index)
                for index in range(len(chunks))
            ]
            records = self.client.retrieve(
                collection_name=self.collection_name,
                ids=expected_ids,
                with_payload=True,
                with_vectors=False,
            )
            records_by_id = {str(point.id): point for point in records}
            if set(records_by_id) != set(expected_ids):
                continue

            complete = True
            for index, chunk in enumerate(chunks):
                payload = records_by_id[expected_ids[index]].payload or {}
                if (
                    payload.get("source_hash") != legacy_source_hash
                    or payload.get("page_content") != chunk.page_content
                ):
                    complete = False
                    break
            if not complete:
                continue

            operations = [
                models.SetPayloadOperation(
                    set_payload=models.SetPayload(
                        points=[point_id],
                        payload={
                            "content_hash": content_hash,
                            "pipeline_version": pipeline_version,
                            "chunk_index": index,
                            "chunk_count": len(chunks),
                            "index_status": "active",
                        },
                    )
                )
                for index, point_id in enumerate(expected_ids)
            ]
            for start in range(0, len(operations), QdrantConfig.SCROLL_PAGE_SIZE):
                self.client.batch_update_points(
                    collection_name=self.collection_name,
                    update_operations=operations[start:start + QdrantConfig.SCROLL_PAGE_SIZE],
                    wait=True,
                )

            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            _field_match("source_id", legacy_source_id),
                            _field_match("source_hash", legacy_source_hash),
                        ],
                        must_not=[models.HasIdCondition(has_id=expected_ids)],
                    )
                ),
                wait=True,
            )

            return legacy_source_id, expected_ids

        return None

    def delete_unverified_legacy_hash(self, source_hash):
        """Remove incomplete legacy points for a hash before retrying it."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[_field_match("source_hash", source_hash)],
                    must_not=[_field_match("content_hash", source_hash)],
                )
            ),
            wait=True,
        )

    def delete_incomplete_version(self, source_id, content_hash, pipeline_version):
        """Clear a prior partial attempt for this exact document version."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        _field_match("source_id", source_id),
                        _field_match("content_hash", content_hash),
                        _field_match("pipeline_version", pipeline_version),
                    ]
                )
            ),
            wait=True,
        )

    def upsert_staged_chunks(
        self,
        pdf_path,
        source_id,
        source_hash,
        content_hash,
        pipeline_version,
        chunks,
    ):
        """Embed and upsert a complete staged version, then verify every chunk."""
        chunk_count = len(chunks)
        self.delete_incomplete_version(source_id, content_hash, pipeline_version)

        for batch_start in range(0, chunk_count, QdrantConfig.EMBEDDING_BATCH_SIZE):
            batch = chunks[batch_start:batch_start + QdrantConfig.EMBEDDING_BATCH_SIZE]
            vectors = embed_documents([chunk.page_content for chunk in batch])
            if len(vectors) != len(batch):
                raise ValueError("El modelo no devolvió un embedding por cada fragmento.")

            points = []
            for offset, (chunk, vector) in enumerate(zip(batch, vectors)):
                chunk_index = batch_start + offset
                payload = {
                    "page_content": chunk.page_content,
                    "source": pdf_path.name,
                    "source_id": source_id,
                    "source_hash": source_hash,
                    "content_hash": content_hash,
                    "pipeline_version": pipeline_version,
                    "chunk_index": chunk_index,
                    "chunk_count": chunk_count,
                    "index_status": "staging",
                    "page": chunk.metadata.get("page"),
                    "start_index": chunk.metadata.get("start_index"),
                }
                points.append(
                    models.PointStruct(
                        id=_new_point_id(source_id, content_hash, pipeline_version, chunk_index),
                        vector=vector,
                        payload={key: value for key, value in payload.items() if value is not None},
                    )
                )

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )

        staged_filter = models.Filter(
            must=[
                _field_match("source_id", source_id),
                _field_match("content_hash", content_hash),
                _field_match("pipeline_version", pipeline_version),
            ]
        )
        staged_points = list(self._scroll(staged_filter))
        if not self._is_complete(staged_points, chunk_count):
            raise RuntimeError("Qdrant no confirmó todos los fragmentos del PDF.")

        self.activate_version(source_id, content_hash, pipeline_version)
        active_points = list(self._scroll(staged_filter))
        if not self._is_complete(active_points, chunk_count) or any(
            (point.payload or {}).get("index_status") != "active"
            for point in active_points
        ):
            raise RuntimeError("No se pudo confirmar la activación completa en Qdrant.")

        return [point.id for point in active_points]

    def activate_version(self, source_id, content_hash, pipeline_version):
        """Make a fully uploaded version visible to RAG searches."""
        self.client.set_payload(
            collection_name=self.collection_name,
            payload={"index_status": "active"},
            points=models.Filter(
                must=[
                    _field_match("source_id", source_id),
                    _field_match("content_hash", content_hash),
                    _field_match("pipeline_version", pipeline_version),
                ]
            ),
            wait=True,
        )

    def delete_previous_versions(self, source_id, keep_point_ids=()):
        """Remove older versions only after the replacement is verified active."""
        filter_conditions = [_field_match("source_id", source_id)]
        if keep_point_ids:
            filter_conditions.append(
                models.HasIdCondition(has_id=list(keep_point_ids))
            )
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[filter_conditions[0]],
                    must_not=filter_conditions[1:],
                )
            ),
            wait=True,
        )
