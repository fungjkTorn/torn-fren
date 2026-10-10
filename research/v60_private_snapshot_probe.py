"""V60: opt-in, one-shot, transactionally consistent PRIVATE research snapshot.

Never switches live research routing, invokes the poller, or writes stock history.
Do not use this as a production feed until an independent freshness-gated
private research-only deployment has been validated.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path


def read_heartbeat(con: sqlite3.Connection) -> int | None:
    row = con.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
                         WHERE mode='poll-cycle' AND success=1""").fetchone()
    return int(row[0]) if row and row[0] is not None else None


def snapshot_once(source: str | Path, destination: str | Path,
                  *, now_fn=time.time, max_heartbeat_age=180) -> dict:
    """Back up from mode=ro source to isolated temp; publish with atomic rename.

    Source SQLite WAL coordination may touch its transient -shm index, but
    opens the database file read-only and never makes logical source writes.
    Fail closed on missing/stale heartbeats and on backup/validation failures.
    """
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve(strict=False)
    if source == destination:
        raise ValueError("source and destination must be different")
    if source in destination.parents or destination in source.parents:
        raise ValueError("destination must be an isolated directory")
    if not 1 <= int(max_heartbeat_age) <= 180:
        raise ValueError("heartbeat age outside allowed bound")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Only a private temp filename may be overwritten. Never touch source.
    tmp = destination.with_name(destination.name + ".v60-unpublished-tmp")
    if tmp.exists() or any(Path(str(tmp) + ext).exists() for ext in ("-wal", "-shm", "-journal")):
        raise FileExistsError("unpublished snapshot temp already exists")
    began = time.monotonic()
    src = dst = None
    try:
        src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)
        src.execute("PRAGMA query_only=ON")
        heartbeat = read_heartbeat(src)
        age = None if heartbeat is None else int(now_fn()) - heartbeat
        if age is None or not 0 <= age <= max_heartbeat_age:
            return {"status": "SOURCE_HEARTBEAT_STALE", "published": False,
                    "source_heartbeat_age_seconds": age}
        dst = sqlite3.connect(tmp,timeout=5)
        src.backup(dst,pages=512,sleep=0.05)
        # Online backup preserves the source's WAL journal mode in the DB
        # header. A private mirror must use rollback-journal DELETE mode,
        # otherwise it inherits the very WAL/SHM dependency we are avoiding.
        journal = dst.execute("PRAGMA journal_mode=DELETE").fetchone()
        if journal != ("delete",):
            raise RuntimeError("private backup did not convert to DELETE mode")
        # Validation uses snapshot, never the mutable source.
        check = dst.execute("PRAGMA quick_check").fetchone()
        if check != ("ok",):
            raise RuntimeError("private backup integrity check failed")
        mirror_heartbeat = read_heartbeat(dst)
        if mirror_heartbeat != heartbeat:
            # The collector advanced during the SQLite backup: a later
            # heartbeat is still valid evidence; older would be suspicious.
            if mirror_heartbeat is None or mirror_heartbeat < heartbeat:
                raise RuntimeError("private backup heartbeat regressed")
        backup_age = int(now_fn()) - mirror_heartbeat
        if not 0 <= backup_age <= max_heartbeat_age:
            return {"status":"SNAPSHOT_HEARTBEAT_STALE","published":False,
                    "source_heartbeat_age_seconds":backup_age}
        dst.commit()
        dst.close()
        dst = None
        src.close()
        src = None
        os.replace(tmp, destination)
        return {"status": "PRIVATE_SNAPSHOT_READY", "published": True,
                "snapshot_bytes": destination.stat().st_size,
                "source_heartbeat_age_seconds": backup_age,
                "elapsed_seconds": round(time.monotonic()-began,2),
                "research_only": True}
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()
        if tmp.exists():
            tmp.unlink()
        for suffix in ("-wal", "-shm", "-journal"):
            p=Path(str(tmp)+suffix)
            if p.exists():
                p.unlink()


def approved_collector_source(requested: str | Path, *, approved: str | Path =
                              "/opt/torn-fren/data/stock_history.db") -> bool:
    """Compare canonical filesystem identities, not an alias against a literal.

    The approved production path can itself be a symbolic link. Resolve both
    sides strictly; this never authorizes an unrelated database file.
    """
    return Path(requested).resolve(strict=True) == Path(approved).resolve(strict=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True)
    p.add_argument("--snapshot", required=True)
    args=p.parse_args()
    # CLI restricts writes to private research-owned directory only.
    source=Path(args.db).resolve(strict=True)
    if not approved_collector_source(source):
        raise SystemExit("STOP: source must be collector stock history")
    dst=Path(args.snapshot).resolve(strict=False)
    private=Path("/var/lib/torn-fren-v38").resolve(strict=True)
    if private not in dst.parents or dst.name != "v60_stock_snapshot.db":
        raise SystemExit("STOP: snapshot must be approved private research filename")
    try:
        out=snapshot_once(source,dst)
    except (OSError,sqlite3.Error,RuntimeError) as exc:
        # Never leak path/SQL internals or claim a valid snapshot on error.
        out={"status":"PRIVATE_SNAPSHOT_ERROR","published":False,
             "error_type":type(exc).__name__}
    print(json.dumps(out,sort_keys=True))

if __name__=="__main__":
    main()
