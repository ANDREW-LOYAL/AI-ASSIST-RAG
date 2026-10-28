"""Coordinate PDF extraction, Qdrant verification, activation, and archiving."""
from pathlib import Path

from src.config import PathConfig
from src.indexing.index_log import write_index_log
from src.indexing.pdf_archive import archive_pdf
from src.indexing.pdf_reader import file_sha256, fingerprint_chunks, load_pdf_chunks
from src.indexing.qdrant_index_store import (
    QdrantIndexStore,
    current_pipeline_version,
    source_id_for_pdf,
)


def _process_one(pdf_path, store=None):
    """Index one PDF, or archive it if Qdrant already has its full content."""
    pdf_path = Path(pdf_path)
    source_id = source_id_for_pdf(pdf_path)
    source_hash = file_sha256(pdf_path)
    chunks = load_pdf_chunks(pdf_path)
    content_hash = fingerprint_chunks(chunks)
    pipeline_version = current_pipeline_version()

    store = store or QdrantIndexStore()
    store.ensure_collection()

    existing = store.find_complete_version(
        content_hash,
        pipeline_version,
        expected_count=len(chunks),
    )
    if existing:
        indexed_source_id, point_ids = existing
        chunk_count = len(point_ids)
        store.delete_previous_versions(
            source_id,
            point_ids if indexed_source_id == source_id else (),
        )
        log_status = "already_indexed" if indexed_source_id == source_id else "duplicate_content"
        write_index_log(
            pdf_path,
            log_status,
            sha256=source_hash,
            content_hash=content_hash,
            chunks=chunk_count,
            indexed_source_id=indexed_source_id,
        )
        archived_path = archive_pdf(pdf_path, source_hash)
        print(f"El contenido ya estaba completo en Qdrant; archivado en {archived_path}")
        return "already_indexed"

    legacy = store.reconcile_legacy_version(
        source_id,
        source_hash,
        content_hash,
        chunks,
        pipeline_version,
    )
    if legacy:
        indexed_source_id, point_ids = legacy
        chunk_count = len(point_ids)
        store.delete_previous_versions(indexed_source_id, point_ids)
        if source_id != indexed_source_id:
            store.delete_previous_versions(source_id)
        write_index_log(
            pdf_path,
            "already_indexed",
            sha256=source_hash,
            content_hash=content_hash,
            chunks=chunk_count,
            reconciled_legacy=True,
            indexed_source_id=indexed_source_id,
        )
        archived_path = archive_pdf(pdf_path, source_hash)
        print(f"Versión previa verificada en Qdrant; archivado en {archived_path}")
        return "already_indexed"


    store.delete_unverified_legacy_hash(source_hash)
    point_ids = store.upsert_staged_chunks(
        pdf_path,
        source_id,
        source_hash,
        content_hash,
        pipeline_version,
        chunks,
    )
    chunk_count = len(point_ids)
    store.delete_previous_versions(source_id, point_ids)

    write_index_log(
        pdf_path,
        "indexed",
        sha256=source_hash,
        content_hash=content_hash,
        chunks=chunk_count,
        pipeline_version=pipeline_version,
    )
    archived_path = archive_pdf(pdf_path, source_hash)
    print(f"Indexado: {pdf_path.name} ({chunk_count} fragmentos) -> {archived_path}")
    return "indexed"


def process_inbox(pdf_dir=None):
    """Process every PDF in the inbox and leave failures there for retry."""
    inbox = Path(pdf_dir) if pdf_dir else PathConfig.DATA_DIR
    inbox.mkdir(parents=True, exist_ok=True)
    PathConfig.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    PathConfig.INDEX_LOG_PATH.touch(exist_ok=True)

    pdf_files = sorted(
        (path for path in inbox.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.name.casefold(),
    )
    counts = {"indexed": 0, "already_indexed": 0, "failed": 0}
    if not pdf_files:
        print(f"No hay PDFs pendientes en {inbox}")
        return counts

    store = None
    for pdf_path in pdf_files:
        try:
            if store is None:
                store = QdrantIndexStore()
            result = _process_one(pdf_path, store)
            counts[result] += 1
        except Exception as error:
            counts["failed"] += 1
            try:
                write_index_log(pdf_path, "failed", error=str(error))
            except OSError as log_error:
                print(f"No se pudo escribir indexing.log: {log_error}")
            print(f"Falló {pdf_path.name}; permanece en la bandeja: {error}")

    print(f"Resumen de indexación: {counts}")
    return counts


def index_pdf(pdf_path=None):
    """Compatibility entry point; no argument processes the full inbox."""
    if pdf_path is None:
        return process_inbox()

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        print(f"El archivo {pdf_path} no existe.")
        return None

    try:
        return _process_one(pdf_path)
    except Exception as error:
        try:
            write_index_log(pdf_path, "failed", error=str(error))
        except OSError as log_error:
            print(f"No se pudo escribir indexing.log: {log_error}")
        print(f"Falló {pdf_path.name}: {error}")
        return None
