"""Inspect whether a historical research SQLite can support sou:Xanax replay.

Read-only, aggregate row counts only; no collector access, no credentials,
no stock history exported, no production changes.
"""
from __future__ import annotations
import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

KEY="sou:Xanax"

def inspect(source):
    p=Path(source).expanduser().resolve(strict=True)
    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=15)) as db:
        db.execute("PRAGMA query_only=ON")
        got=db.execute(
            """SELECT COUNT(*),MIN(timestamp),MAX(timestamp) FROM stock_history
               WHERE country='sou' AND lower(item_name)='xanax'""").fetchone()
        polls=db.execute(
            """SELECT MAX(timestamp) FROM poll_heartbeats
               WHERE mode='poll-cycle' AND success=1""").fetchone()
        metadata=dict(db.execute("SELECT key,value FROM research_metadata"))
    return {"status":("SOUTH_AFRICA_HISTORY_PRESENT" if got[0]>0
                      else "MISSING_SOUTH_AFRICA_XANAX_HISTORY"),
            "item_key":KEY,"stock_change_rows":got[0],
            "first_stock_observation_epoch":got[1],
            "last_stock_observation_epoch":got[2],
            "last_successful_poll_epoch":polls[0],
            "sanitized_stock_only":metadata.get("sanitized_stock_only"),
            "source_roster_size":metadata.get("roster_size"),
            "historical_source_read_only":True,
            "production_modified":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    a=p.parse_args()
    print(json.dumps(inspect(a.source),sort_keys=True))


if __name__=="__main__":
    main()
