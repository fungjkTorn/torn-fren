#!/usr/bin/env python3
"""Export a minimal, research-only SQLite view of foreign-item stock history.

Run AS the collector owner, with output group assigned to an isolated research
runner. Never copies player keys, API keys, account details, prices, internal
tables or other game data. Reads the collector in SQLite query-only mode,
uses a consistent transaction, and atomically replaces a separate output DB.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import tempfile
import time
from contextlib import closing
from pathlib import Path

BASE_EXTRAS=frozenset(("can:Xanax","uni:Xanax"))
MAX_DAYS=120
MIN_DAYS=14
MAX_ROWS_PER_ITEM=200000
MAX_TOTAL_ROWS=1800000
MAX_COUNTRY_ROWS=4000000

DDL="""
CREATE TABLE stock_history(
    id INTEGER PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    source TEXT NOT NULL,
    country TEXT NOT NULL,
    item_name TEXT NOT NULL
);
CREATE INDEX idx_stock_country_name_time
    ON stock_history(country,lower(item_name),timestamp,id);
CREATE TABLE collection_gaps(
    start_timestamp INTEGER NOT NULL,
    end_timestamp INTEGER
);
CREATE INDEX idx_gap_start ON collection_gaps(start_timestamp);
CREATE TABLE poll_heartbeats(
    id INTEGER PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    mode TEXT NOT NULL,
    success INTEGER NOT NULL,
    source TEXT
);
CREATE INDEX idx_poll_time ON poll_heartbeats(timestamp);
CREATE TABLE research_metadata(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE country_stock_observations(
    id INTEGER PRIMARY KEY,
    received_epoch INTEGER NOT NULL,
    country TEXT NOT NULL,
    source TEXT NOT NULL,
    country_update_epoch INTEGER,
    export_epoch INTEGER,
    clock_status TEXT NOT NULL,
    export_clock_status TEXT NOT NULL,
    item_count INTEGER NOT NULL
);
CREATE INDEX idx_country_observation_time
    ON country_stock_observations(country,received_epoch,id);
"""


def read_roster(path:Path):
    roster=json.loads(path.read_text(encoding="utf8"))
    base=roster.get("items")
    if not isinstance(base,dict) or len(base)!=22:
        raise ValueError("expected exactly 22 canonical research items")
    keys=set(base)|BASE_EXTRAS
    if len(keys)!=24 or set(base)&BASE_EXTRAS or any(
        type(key) is not str or key.count(":")!=1 for key in keys):
        raise ValueError("24 item research roster drift")
    return sorted(keys)


def safe_real_file(path):
    original=Path(path)
    if original.is_symlink():
        raise ValueError("symlink source/roster not allowed")
    real=original.resolve(strict=True)
    if not real.is_file():
        raise ValueError("source/roster is not a regular file")
    return real


def export(source,roster,output,*,asof=None,days=45,
           max_rows=MAX_ROWS_PER_ITEM,max_total=MAX_TOTAL_ROWS):
    if (type(days) is not int or not MIN_DAYS<=days<=MAX_DAYS or
        type(max_rows) is not int or not 100<=max_rows<=MAX_ROWS_PER_ITEM or
        type(max_total) is not int or not 2400<=max_total<=MAX_TOTAL_ROWS):
        raise ValueError("invalid bounded export policy")
    clock=int(time.time()) if asof is None else asof
    if type(clock) is not int or clock<=0:
        raise ValueError("invalid export cutoff")
    start=clock-86400*days
    src=safe_real_file(source)
    catalog=read_roster(safe_real_file(roster))
    out=Path(output)
    if out.is_symlink() or out == src or out.resolve()==src:
        raise ValueError("output cannot be source or symlink")
    parent=out.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("output parent unavailable")
    # Only an installer-managed, private output folder may be used. Do not
    # permit exported research DBs in the public repository or web tree.
    if stat.S_IMODE(parent.stat().st_mode)&0o007:
        raise ValueError("export directory exposes permissions to other users")
    fd,tmp=tempfile.mkstemp(prefix=".stock-export-",suffix=".db",dir=parent)
    os.close(fd)
    temp=Path(tmp)
    os.chmod(temp,0o640)
    count=0
    row_counts={}
    try:
        with closing(sqlite3.connect(src.as_uri()+"?mode=ro",uri=True,timeout=15)) as reader:
            reader.execute("PRAGMA query_only=ON")
            # ORDER BY on collector history can need a SQLite temporary
            # b-tree. Keep it in bounded RAM rather than attempting to open
            # a temp DB inside the systemd service's restricted mount view.
            reader.execute("PRAGMA temp_store=MEMORY")
            reader.execute("BEGIN")
            with closing(sqlite3.connect(temp,timeout=15)) as dest:
                dest.executescript(DDL)
                for key in catalog:
                    country,item=key.split(":",1)
                    # Include last observation before the export horizon so
                    # transitions just after the cutoff remain interpretable.
                    prior=reader.execute(
                        """SELECT timestamp,quantity,source,country,item_name
                           FROM stock_history
                           WHERE country=? AND lower(item_name)=lower(?)
                             AND timestamp<?
                           ORDER BY timestamp DESC,id DESC LIMIT 1""",
                        (country,item,start)).fetchone()
                    cursor=reader.execute(
                        """SELECT timestamp,quantity,source,country,item_name
                           FROM stock_history
                           WHERE country=? AND lower(item_name)=lower(?)
                             AND timestamp BETWEEN ? AND ?
                           ORDER BY timestamp,id""",
                        (country,item,start,clock))
                    local_count=0
                    def insert(row):
                        nonlocal count,local_count
                        t,q,provider,c,name=row
                        if (type(t) is not int or type(q) is not int or
                            not 0<=q or not isinstance(provider,str)
                            or not provider or c!=country or
                            name.casefold()!=item.casefold()):
                            raise ValueError("invalid stock row for "+key)
                        count+=1
                        local_count+=1
                        if count>max_total or local_count>max_rows:
                            raise ValueError("bounded dataset size exceeded")
                        dest.execute(
                            """INSERT INTO stock_history
                              (timestamp,quantity,source,country,item_name)
                              VALUES(?,?,?,?,?)""",
                            (t,q,provider,c,name))
                    if prior:
                        insert(prior)
                    for row in cursor:
                        insert(row)
                    row_counts[key]=local_count
                # Only observed gaps; no foreign URLs or credentials.
                dest.executemany(
                    "INSERT INTO collection_gaps VALUES(?,?)",
                    reader.execute(
                        """SELECT start_timestamp,end_timestamp FROM collection_gaps
                           WHERE start_timestamp<=?
                             AND COALESCE(end_timestamp,9223372036854775807)>=?
                           ORDER BY start_timestamp""",(clock,start))
                )
                # Preserve provider identifiers when present so an independent
                # post-issue physical-zero scorer can verify source continuity.
                # This is a provider LABEL only, never an API key or player ID.
                # If an older collector lacks heartbeat.source, leave it NULL;
                # the scorer must report UNKNOWN rather than fabricate provider
                # continuity from item history.
                heartbeat_columns={col[1] for col in
                    reader.execute("PRAGMA table_info(poll_heartbeats)")}
                has_heartbeat_source="source" in heartbeat_columns
                heartbeat_source_column=("source" if has_heartbeat_source
                                         else "NULL AS source")
                dest.executemany(
                    "INSERT INTO poll_heartbeats(timestamp,mode,success,source) VALUES(?,?,?,?)",
                    reader.execute(
                        "SELECT timestamp,mode,success,"+heartbeat_source_column+
                        """ FROM poll_heartbeats
                            WHERE timestamp BETWEEN ? AND ?
                              AND mode='poll-cycle' AND success=1
                            ORDER BY timestamp""",(start,clock))
                )
                has_clocks=reader.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='country_stock_observations'").fetchone() is not None
                country_rows=0
                if has_clocks:
                    # Explicit columns only. Never SELECT * from production.
                    allowed={key.split(':',1)[0] for key in catalog}
                    cursor=reader.execute('''SELECT received_epoch,country,source,
                        country_update_epoch,export_epoch,clock_status,export_clock_status,item_count
                        FROM country_stock_observations WHERE received_epoch BETWEEN ? AND ?
                        ORDER BY received_epoch,id LIMIT ?''',(start,clock,MAX_COUNTRY_ROWS+1))
                    statuses={'MISSING','INVALID','FUTURE','REPORTED'}
                    for scanned,row in enumerate(cursor,1):
                        if scanned>MAX_COUNTRY_ROWS:raise ValueError('country observation cap exceeded')
                        receipt,country,provider,update,export_clock,status,export_status,n=row
                        if country not in allowed:continue
                        if (type(receipt) is not int or provider not in ('yata','prometheus','unknown')
                            or any(v is not None and (type(v) is not int or not 0<v<=9999999999) for v in (update,export_clock))
                            or type(status) is not str or status.removeprefix('EMPTY_PAYLOAD_') not in statuses
                            or export_status not in statuses
                            or type(n) is not int or not 0<=n<=10000):
                            raise ValueError('invalid country observation')
                        country_rows+=1
                        if country_rows>MAX_COUNTRY_ROWS:raise ValueError('country observation cap exceeded')
                        dest.execute('''INSERT INTO country_stock_observations
                            (received_epoch,country,source,country_update_epoch,export_epoch,
                             clock_status,export_clock_status,item_count) VALUES(?,?,?,?,?,?,?,?)''',row)
                metadata={
                    "schema":"torn-fren-research-stock-v1",
                    "source_cutoff_epoch":str(clock),
                    "history_days":str(days),
                    "roster_size":str(len(catalog)),
                    "row_count":str(count),
                    "contains_game_api_keys":"false",
                    "sanitized_stock_only":"true",
                    "country_clock_schema_available":str(has_clocks).lower(),
                    "country_clock_rows":str(country_rows),
                    "heartbeat_provider_field_present":str(has_heartbeat_source).lower(),
                }
                dest.executemany(
                    "INSERT INTO research_metadata(key,value) VALUES(?,?)",
                    metadata.items())
                dest.commit()
                if dest.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                    raise ValueError("snapshot SQLite integrity check failed")
            reader.execute("ROLLBACK")
        os.chmod(temp,0o640)
        os.replace(temp,out)
        return {"status":"RESEARCH_SNAPSHOT_READY","asof_epoch":clock,
                "items":len(catalog),"stock_rows":count,
                "days":days,"private_output":str(out)}
    finally:
        if temp.exists():
            temp.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",required=True)
    parser.add_argument("--roster",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--days",type=int,default=45)
    args=parser.parse_args()
    print(json.dumps(export(args.source,args.roster,args.output,days=args.days),
                     sort_keys=True))


if __name__=="__main__":
    main()
