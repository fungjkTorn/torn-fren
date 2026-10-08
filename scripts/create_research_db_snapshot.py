import argparse
import hashlib
import json
import sqlite3
import time
import sys
from pathlib import Path

# Allow both `python -m scripts.create_research_db_snapshot` and direct
# `python scripts/create_research_db_snapshot.py` execution from the repo root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.history_service import DB_PATH


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_snapshot(destination):
    source = Path(DB_PATH).resolve()
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if not source.exists():
        raise FileNotFoundError(source)
    if source == destination:
        raise ValueError("Destination must not overwrite the live database.")

    tmp = destination.with_suffix(destination.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()

    # SQLite backup creates a transactionally consistent snapshot even while the
    # production poller continues writing to the source database.
    source_uri = f"file:{source.as_posix()}?mode=ro"
    with sqlite3.connect(source_uri, uri=True, timeout=30.0) as src:
        with sqlite3.connect(tmp) as dst:
            src.backup(dst)
            check = dst.execute("PRAGMA integrity_check").fetchone()
            if not check or check[0].lower() != "ok":
                raise RuntimeError(f"Snapshot integrity check failed: {check}")

    tmp.replace(destination)

    metadata = {
        "created_at": int(time.time()),
        "source": str(source),
        "snapshot": str(destination),
        "size_bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
    }
    metadata_path = destination.with_suffix(destination.suffix + ".json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Snapshot: {destination}")
    print(f"Size: {metadata['size_bytes']:,} bytes")
    print(f"SHA256: {metadata['sha256']}")
    print(f"Metadata: {metadata_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Create a consistent read-only research snapshot of stock_history.db."
    )
    parser.add_argument(
        "destination",
        nargs="?",
        default="/tmp/torn-fren-stock-history-research.db",
    )
    args = parser.parse_args()
    create_snapshot(args.destination)


if __name__ == "__main__":
    main()
