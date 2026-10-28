"""Index PDFs from the inbox, record their status, and archive successes."""
import hashlib
import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from src.config import OllamaConfig, PathConfig, QdrantConfig
from src.qdrant.qdrant_conector import qdrant_conection


CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
EMBEDDING_BATCH_SIZE = 32


def _now():
    """Return a timezone-aware timestamp for the manifest and audit log."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _file_sha256(pdf_path):
    """Calculate a content hash without loading the entire PDF into memory."""
    digest = hashlib.sha256()
    with Path(pdf_path).open("rb") as pdf_file:
        for block in iter(lambda: pdf_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_id(pdf_path):
    """Create a stable Qdrant source ID from the inbox filename."""
    normalized_name = Path(pdf_path).name.casefold()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"pdf-indexer:{normalized_name}"))


def _open_manifest():
    """Create the manifest schema and return a SQLite connection."""
    PathConfig.INDEX_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(PathConfig.INDEX_MANIFEST_PATH)
    connection.execute(
        """CREATE TABLE IF NOT EXISTS indexed_files (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            chunk_count INTEGER NOT NULL
        )"""
    )
    connection.commit()
    return connection


def _write_log(pdf_path, status, **details):
    """Append one JSON record to the human-readable indexing audit log."""
    PathConfig.INDEX_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": _now(),
        "file": Path(pdf_path).name,
        "status": status,
        **details,
    }
    with PathConfig.INDEX_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        log_file.flush()


def _archive_pdf(pdf_path, sha256):
    """Move an indexed PDF to the archive without overwriting prior files."""
    PathConfig.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = Path(pdf_path)
    target = PathConfig.DATA_PROCESSED_DIR / pdf_path.name

    if target.exists():
        target = PathConfig.DATA_PROCESSED_DIR / (
            f"{pdf_path.stem}__{sha256[:12]}{pdf_path.suffix}"
        )
    counter = 2
    while target.exists():
        target = PathConfig.DATA_PROCESSED_DIR / (
            f"{pdf_path.stem}__{sha256[:12]}_{counter}{pdf_path.suffix}"
        )
        counter += 1

    shutil.move(str(pdf_path), str(target))
    return target


def _ensure_collection(client, embeddings):
    """Create the collection using the embedding model's actual vector size."""
    vector_size = len(embeddings.embed_query("dimension check"))
    if vector_size == 0:
        raise ValueError("El modelo de embeddings devolvió un vector vacío.")

    if not client.collection_exists(QdrantConfig.COLLECTION_NAME):
        client.create_collection(
            collection_name=QdrantConfig.COLLECTION_NAME,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        return

    collection = client.get_collection(QdrantConfig.COLLECTION_NAME)
    vectors_config = collection.config.params.vectors
    stored_size = getattr(vectors_config, "size", None)
    if stored_size != vector_size:
        raise ValueError(
            f"La colección '{QdrantConfig.COLLECTION_NAME}' usa vectores de "
            f"{stored_size} dimensiones, pero '{OllamaConfig.EMBEDDING_MODEL}' "
            f"devuelve {vector_size}. Corrige o recrea la colección antes de indexar."
        )


def _delete_source_points(client, source_id):
    """Remove prior chunks for a changed PDF before replacing its content."""
    client.delete(
        collection_name=QdrantConfig.COLLECTION_NAME,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="source_id",
                    match=MatchValue(value=source_id),
                )
            ]
        ),
        wait=True,
    )


def _index_pdf(pdf_path, source_id, sha256):
    """Load, split, embed, and upsert one PDF with deterministic point IDs."""
    print(f"Cargando PDF: {pdf_path}")
    documents = PyPDFLoader(str(pdf_path)).load()
    if not documents:
        raise ValueError("El PDF no contiene páginas que se puedan procesar.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        add_start_index=True,
    )
    chunks = splitter.split_documents(documents)
    if not chunks:
        raise ValueError("No se pudo extraer texto del PDF.")

    embeddings = OllamaEmbeddings(model=OllamaConfig.EMBEDDING_MODEL)
    client = qdrant_conection()
    _ensure_collection(client, embeddings)

    # Keep the input PDF in the inbox unless Qdrant accepts every batch.
    # If a batch fails, the deterministic IDs make the next run safe to retry.
    _delete_source_points(client, source_id)

    for batch_start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[batch_start:batch_start + EMBEDDING_BATCH_SIZE]
        texts = [chunk.page_content for chunk in batch]
        vectors = embeddings.embed_documents(texts)
        if len(vectors) != len(batch):
            raise ValueError("El modelo no devolvió un embedding por cada fragmento.")

        points = []
        for offset, (chunk, vector) in enumerate(zip(batch, vectors)):
            chunk_index = batch_start + offset
            point_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{source_id}:{sha256}:{chunk_index}",
                )
            )
            payload = {
                "page_content": chunk.page_content,
                "source": Path(pdf_path).name,
                "source_id": source_id,
                "source_hash": sha256,
                "page": chunk.metadata.get("page"),
                "start_index": chunk.metadata.get("start_index"),
            }
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={key: value for key, value in payload.items() if value is not None},
                )
            )

        client.upsert(
            collection_name=QdrantConfig.COLLECTION_NAME,
            points=points,
            wait=True,
        )

    return len(chunks)


def _process_one(pdf_path, manifest):
    """Index one inbox PDF, recording success before moving it to the archive."""
    pdf_path = Path(pdf_path)
    source_id = _source_id(pdf_path)
    sha256 = _file_sha256(pdf_path)

    previous = manifest.execute(
        "SELECT sha256, chunk_count FROM indexed_files WHERE source_id = ?",
        (source_id,),
    ).fetchone()

    if previous and previous[0] == sha256:
        archived_path = _archive_pdf(pdf_path, sha256)
        _write_log(
            pdf_path,
            "already_indexed",
            sha256=sha256,
            chunks=previous[1],
            archived_as=archived_path.name,
        )
        print(f"Ya estaba indexado; movido a {archived_path}")
        return "already_indexed"

    if previous is None:
        duplicate = manifest.execute(
            "SELECT source_name FROM indexed_files WHERE sha256 = ? LIMIT 1",
            (sha256,),
        ).fetchone()
        if duplicate:
            archived_path = _archive_pdf(pdf_path, sha256)
            _write_log(
                pdf_path,
                "duplicate_content",
                sha256=sha256,
                indexed_as=duplicate[0],
                archived_as=archived_path.name,
            )
            print(f"Contenido ya indexado como {duplicate[0]}; PDF archivado.")
            return "already_indexed"

    chunk_count = _index_pdf(pdf_path, source_id, sha256)
    indexed_at = _now()
    manifest.execute(
        """INSERT INTO indexed_files (source_id, source_name, sha256, indexed_at, chunk_count)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(source_id) DO UPDATE SET
               source_name = excluded.source_name,
               sha256 = excluded.sha256,
               indexed_at = excluded.indexed_at,
               chunk_count = excluded.chunk_count""",
        (source_id, pdf_path.name, sha256, indexed_at, chunk_count),
    )
    manifest.commit()

    archived_path = _archive_pdf(pdf_path, sha256)
    _write_log(
        pdf_path,
        "indexed",
        sha256=sha256,
        chunks=chunk_count,
        archived_as=archived_path.name,
    )
    print(f"Indexado: {pdf_path.name} ({chunk_count} fragmentos)")
    return "indexed"


def process_inbox(pdf_dir=None):
    """Process all PDFs in the inbox; leave failures there for a later retry."""
    inbox = Path(pdf_dir) if pdf_dir else PathConfig.DATA_DIR
    inbox.mkdir(parents=True, exist_ok=True)
    PathConfig.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    PathConfig.INDEX_LOG_PATH.touch(exist_ok=True)

    pdf_files = sorted(
        (path for path in inbox.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.name.casefold(),
    )
    if not pdf_files:
        print(f"No hay PDFs pendientes en {inbox}")
        return {"indexed": 0, "already_indexed": 0, "failed": 0}

    manifest = _open_manifest()
    counts = {"indexed": 0, "already_indexed": 0, "failed": 0}
    try:
        for pdf_path in pdf_files:
            try:
                result = _process_one(pdf_path, manifest)
                counts[result] += 1
            except Exception as error:
                counts["failed"] += 1
                _write_log(pdf_path, "failed", error=str(error))
                print(f"Falló {pdf_path.name}; permanece en la bandeja: {error}")
    finally:
        manifest.close()

    print(f"Resumen de indexación: {counts}")
    return counts


def index_pdf(pdf_path=None):
    """Backward-compatible entry point; no argument processes the whole inbox."""
    if pdf_path is None:
        return process_inbox()

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        print(f"El archivo {pdf_path} no existe.")
        return None

    PathConfig.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    PathConfig.INDEX_LOG_PATH.touch(exist_ok=True)
    manifest = _open_manifest()
    try:
        return _process_one(pdf_path, manifest)
    except Exception as error:
        _write_log(pdf_path, "failed", error=str(error))
        print(f"Falló {pdf_path.name}: {error}")
        return None
    finally:
        manifest.close()


if __name__ == "__main__":
    process_inbox()
