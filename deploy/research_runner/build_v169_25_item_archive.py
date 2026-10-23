#!/usr/bin/env python3
"""One-time, research-only 25-item sanitized archive; never alter live data.

Combine the EXISTING 24-item sanitized stock/poll archive with ONLY historical
sou:Xanax stock rows from the collector. The collector is opened mode=ro,
query_only; existing 24-item archive and ongoing forward timer stay untouched.

Requires execution as the authorized collector owner (ubuntu) when run on VM.
The new archive is a distinct file in the same private research directory,
not a website or a production file. Never copies keys, prices or player info.
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import stat
import tempfile
from contextlib import closing
from pathlib import Path

ITEM="sou:Xanax"
OUT_NAME="stock_history_research25_south_africa.db"
MAX_SOUTH_ROWS=250000

def safe_input(path):
    p=Path(path)
    if p.is_symlink():raise ValueError("source symlink not allowed")
    real=p.resolve(strict=True)
    if not real.is_file():raise ValueError("expected SQLite file")
    return real

def open_ro(path):
    con=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=30)
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA temp_store=MEMORY")
    return con

def build(base,source,output):
    base=safe_input(base)
    source=safe_input(source)
    target=Path(output)
    if target.name!=OUT_NAME or target.is_symlink():
        raise ValueError("output must be approved independent 25-item research archive")
    parent=target.parent.resolve(strict=True)
    if parent!=base.parent or target.resolve() in (source,base):
        raise ValueError("output must be alongside the existing private 24-item archive")
    if stat.S_IMODE(parent.stat().st_mode)&0o007:
        raise ValueError("research directory exposes permissions to others")
    if target.exists():raise FileExistsError("research archive already exists; never overwrite")
    fd,temp_name=tempfile.mkstemp(prefix=".v169-sou-xanax-",suffix=".db",dir=parent)
    os.close(fd)
    tmp=Path(temp_name)
    try:
        os.chmod(tmp,0o600)
        with closing(open_ro(base)) as previous,closing(open_ro(source)) as collector:
            metadata=dict(previous.execute("SELECT key,value FROM research_metadata"))
            if (metadata.get("sanitized_stock_only")!="true" or
                metadata.get("roster_size")!="24" or
                metadata.get("contains_game_api_keys")!="false"):
                raise ValueError("base is not an approved 24-item sanitized stock archive")
            if previous.execute("SELECT COUNT(*) FROM stock_history WHERE country='sou' AND lower(item_name)='xanax'").fetchone()[0]:
                raise ValueError("25th item already in base; do not duplicate")
            cutoff=int(metadata["source_cutoff_epoch"])
            days=int(metadata["history_days"])
            if not 14<=days<=120:raise ValueError("invalid bounded archive horizon")
            start=cutoff-days*86400
            latest=collector.execute(
                "SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1"
            ).fetchone()[0]
            if latest is None or int(latest)<cutoff-3600:
                raise ValueError("collector too stale relative to sanitized source cutoff")
            collector.execute("BEGIN")
            with closing(sqlite3.connect(tmp,timeout=30)) as dest:
                previous.backup(dest,pages=512,sleep=.02)
                dest.execute("PRAGMA journal_mode=DELETE")
                prior=collector.execute(
                    """SELECT timestamp,quantity,source,country,item_name
                       FROM stock_history
                       WHERE country='sou' AND lower(item_name)='xanax'
                         AND timestamp<? ORDER BY timestamp DESC,id DESC LIMIT 1""",
                    (start,)).fetchone()
                cursor=collector.execute(
                    """SELECT timestamp,quantity,source,country,item_name
                       FROM stock_history
                       WHERE country='sou' AND lower(item_name)='xanax'
                         AND timestamp>=? AND timestamp<=?
                       ORDER BY timestamp,id""",(start,cutoff))
                def validated_rows():
                    if prior is not None:yield prior
                    yield from cursor
                count=0
                for r in validated_rows():
                    ts,q,provider,c,name=r
                    if (type(ts) is not int or ts>cutoff or type(q) is not int
                        or q<0 or type(provider) is not str or not provider
                        or c!="sou" or name.casefold()!="xanax"):
                        raise ValueError("untrusted historical South Africa Xanax row")
                    count+=1
                    if count>MAX_SOUTH_ROWS:
                        raise ValueError("unbounded South Africa history")
                    dest.execute(
                        """INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                           VALUES(?,?,?,?,?)""",r)
                if count==0:raise ValueError("NO_SOUTH_AFRICA_XANAX_ROWS_IN_COLLECTOR")
                extra={
                    "roster_size":"25",
                    "row_count":str(int(metadata["row_count"])+count),
                    "research_added_item":ITEM,
                    "research_only_extension":"true",
                }
                dest.executemany(
                    "UPDATE research_metadata SET value=? WHERE key=?",
                    ((v,k) for k,v in extra.items() if k in ("roster_size","row_count")))
                dest.executemany(
                    "INSERT INTO research_metadata(key,value) VALUES(?,?)",
                    ((k,v) for k,v in extra.items() if k not in ("roster_size","row_count")))
                dest.commit()
                if dest.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise ValueError("new research archive failed integrity check")
                added=dest.execute(
                    "SELECT COUNT(*) FROM stock_history WHERE country='sou' AND lower(item_name)='xanax'"
                ).fetchone()[0]
                if added!=count:raise ValueError("source-history copy mismatch")
        os.replace(tmp,target)
        os.chmod(target,0o600)
        return {
            "status":"RESEARCH_25_ITEM_SANITIZED_ARCHIVE_READY",
            "output":str(target),"new_item":ITEM,"added_rows":count,
            "historical_source_cutoff_epoch":cutoff,
            "production_modified":False,
            "original_24_item_archive_modified":False,
            "live_collector_modified":False,
        }
    finally:
        if tmp.exists():tmp.unlink()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",required=True)
    p.add_argument("--collector",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    print(json.dumps(build(a.base,a.collector,a.output),sort_keys=True))

if __name__=="__main__":
    main()
