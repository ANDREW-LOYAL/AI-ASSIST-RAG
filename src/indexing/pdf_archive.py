"""Move successfully indexed or already-present PDFs to the archive folder."""
import shutil
from pathlib import Path

from src.config import PathConfig


def archive_pdf(pdf_path, content_hash):
    """Archive a PDF without replacing a file already in the destination."""
    pdf_path = Path(pdf_path)
    archive_dir = PathConfig.DATA_PROCESSED_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / pdf_path.name

    if target.exists():
        target = archive_dir / (
            f"{pdf_path.stem}__{content_hash[:12]}{pdf_path.suffix}"
        )
    counter = 2
    while target.exists():
        target = archive_dir / (
            f"{pdf_path.stem}__{content_hash[:12]}_{counter}{pdf_path.suffix}"
        )
        counter += 1

    shutil.move(str(pdf_path), str(target))
    return target
