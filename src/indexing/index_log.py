"""Write a human-readable JSON Lines audit log for PDF indexing."""
import json
from datetime import datetime, timezone
from pathlib import Path

from src.config import PathConfig


def write_index_log(pdf_path, status, **details):
    """Append a timestamped indexing event; this log is not index state."""
    log_path = PathConfig.INDEX_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "file": Path(pdf_path).name,
        "status": status,
        **details,
    }
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        log_file.flush()
