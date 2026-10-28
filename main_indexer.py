"""Root entry point for PDF indexing and Qdrant verification."""
import sys

from src.indexing.pdf_indexer import process_inbox


def main():
    """Index pending PDFs, verify them in Qdrant, and report the exit status."""
    results = process_inbox()
    return 1 if results["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
