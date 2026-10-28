"""Extract text from a PDF and split it into indexing chunks."""
import hashlib
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.config import QdrantConfig


def file_sha256(pdf_path):
    """Hash the PDF bytes without loading the whole file into memory."""
    digest = hashlib.sha256()
    with Path(pdf_path).open("rb") as pdf_file:
        for block in iter(lambda: pdf_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pdf_chunks(pdf_path):
    """Extract pages and return their recursively split text chunks."""
    pages = PyPDFLoader(str(pdf_path)).load()
    if not pages:
        raise ValueError("El PDF no contiene páginas que se puedan procesar.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=QdrantConfig.CHUNK_SIZE,
        chunk_overlap=QdrantConfig.CHUNK_OVERLAP,
        add_start_index=True,
    )
    chunks = splitter.split_documents(pages)
    if not chunks:
        raise ValueError("No se pudo extraer texto del PDF.")
    return chunks


def fingerprint_chunks(chunks):
    """Hash normalized extracted text so equivalent PDF files can be deduplicated."""
    digest = hashlib.sha256()
    for chunk in chunks:
        normalized_text = " ".join(chunk.page_content.split())
        digest.update(normalized_text.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()
