"""V54 resumable OFFLINE Lion/Panda expert-label export.

Use ONLY against a frozen independent SQLite stock-history snapshot on a
development PC. The snapshot file's SHA256, explicit training as-of cutoff,
target and ordered anchor set are pinned into a separate local cache.
Progress is committed per anchor (including no-schedule abstentions) so jobs
can stop/restart without duplicating or overwriting previous evidence.

Exports source-derived resolved observations in a JSONL file via atomic
replace, ready for v53_pair_holdout_audit. Does not train/activate anything,
write stock-history, require API keys, or interact with production services.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

from research.plushie_champions.common import (
    ResearchContext,valid_starts,TRAVEL_SECONDS,MAX_WAIT,GRACE
)
from research.v49_lion_panda_pair_probe import TARGETS
from research.v50_pair_example_export import resolved_example

SCHEMA="v54-offline-dual-expert-resume-v1"
CACHE_TABLE="""CREATE TABLE IF NOT EXISTS v54_history(
  anchor_ts INTEGER PRIMARY KEY,
  status TEXT NOT NULL,
  record_json TEXT
)"""
META_TABLE="""CREATE TABLE IF NOT EXISTS v54_metadata(
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  schema TEXT NOT NULL,
  item_key TEXT NOT NULL,
  train_asof INTEGER NOT NULL,
  source_sha256 TEXT NOT NULL,
  anchor_set_sha256 TEXT NOT NULL,
  requested_starts INTEGER NOT NULL
)"""


def fingerprint(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def eligible_anchors(ctx,target,cutoff,last_starts):
    cfg=TARGETS[target]
    country,item=cfg["key"].split(":",1)
    anchors=[int(s) for s in valid_starts(ctx,country,item)
             if s+MAX_WAIT+TRAVEL_SECONDS[country]+GRACE<=cutoff]
    return anchors[-last_starts:]


def signature(db,target,cutoff,anchors,last_starts):
    h=hashlib.sha256(json.dumps(anchors,separators=(",",":")).encode()).hexdigest()
    return (SCHEMA,TARGETS[target]["key"],int(cutoff),
            fingerprint(db),h,int(last_starts))


def cache_open(filename,signature_values):
    path=Path(filename)
    path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=15)
    try:
        con.execute("PRAGMA busy_timeout=5000")
        con.execute(META_TABLE)
        con.execute(CACHE_TABLE)
        existing=con.execute("""SELECT schema,item_key,train_asof,source_sha256,
          anchor_set_sha256,requested_starts FROM v54_metadata WHERE singleton=1""").fetchone()
        if existing is not None and tuple(existing)!=tuple(signature_values):
            raise ValueError("OFFLINE_SOURCE_OR_CUTOFF_CHANGED_REQUIRES_NEW_CACHE")
        if existing is None:
            with con:
                con.execute("INSERT INTO v54_metadata VALUES(1,?,?,?,?,?,?)",
                            signature_values)
        return con
    except BaseException:
        con.close()
        raise


def write_export_atomic(con,output):
    path=Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    # For each checkpoint, rebuild the small JSONL from the committed cache.
    # Atomic replacement ensures failed writes never present truncated output.
    fd,name=tempfile.mkstemp(prefix=".v54.",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as out:
            rows=con.execute("""SELECT record_json FROM v54_history
                WHERE status='RESOLVED' ORDER BY anchor_ts""")
            n=0
            for (data,) in rows:
                if data is None:
                    raise ValueError("corrupt RESOLVED historical record")
                out.write(data+"\n")
                n+=1
            out.flush()
            os.fsync(out.fileno())
        os.replace(name,path)
        return n
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(db,cache,output,target,cutoff,*,last_starts=240,max_new=12,
        builder=ResearchContext.build,processor=resolved_example):
    if target not in TARGETS:
        raise ValueError("not an approved Lion/Panda target")
    if not 1<=last_starts<=5000 or not 1<=max_new<=50:
        raise ValueError("offline bounded batch limits required")
    db=Path(db).resolve(strict=True)
    cache_path=Path(cache).resolve(strict=False)
    output_path=Path(output).resolve(strict=False)
    if len({db,cache_path,output_path})!=3:
        raise ValueError("stock source, private cache and export paths must differ")
    if str(db).startswith(("/opt/torn-fren/","/var/lib/torn-fren/")):
        raise ValueError("refusing production collector DB for offline replay")
    # A live collector changes underneath this computation and invalidates
    # resolved labels; require a copied, frozen input by snapshot convention.
    if not db.is_file() or db.stat().st_size<4096:
        raise ValueError("not a frozen SQLite snapshot")
    cutoff=int(cutoff)
    ctx=builder(db,asof=cutoff,readonly=True)
    try:
        anchors=eligible_anchors(ctx,target,cutoff,last_starts)
        if not anchors:
            raise ValueError("no fully resolved replay anchors")
        ident=signature(db,target,cutoff,anchors,last_starts)
        con=cache_open(cache,ident)
        try:
            processed=con.execute("SELECT anchor_ts FROM v54_history").fetchall()
            done={int(row[0]) for row in processed}
            todo=[s for s in anchors if s not in done]
            batch=todo[:max_new]
            accepted=0
            for s in batch:
                record=processor(ctx,target,s,cutoff)
                if record is not None:
                    if (record.get("key")!=TARGETS[target]["key"] or
                        int(record.get("decision_ts",-1))!=s or
                        int(record.get("resolved_at",cutoff+1))>cutoff or
                        record.get("research_only") is not True):
                        raise ValueError("noncausal or mismatched export result")
                    payload=json.dumps(record,sort_keys=True,
                                       separators=(",",":"),allow_nan=False)
                    state="RESOLVED"
                    accepted+=1
                else:
                    payload=None
                    state="ABSTAINED"
                with con:
                    con.execute("INSERT INTO v54_history VALUES(?,?,?)",
                                (int(s),state,payload))
            if fingerprint(db)!=ident[3]:
                raise ValueError("source snapshot changed during offline replay")
            n=write_export_atomic(con,output)
            seen=len(done)+len(batch)
            return {
                "status":"OFFLINE_EXPORT_COMPLETE"
                    if seen==len(anchors) else "OFFLINE_EXPORT_BUILDING",
                "item_key":TARGETS[target]["key"],
                "source_sha256":ident[3],
                "anchor_set_sha256":ident[4],
                "resolved_examples_exported":n,
                "batch_decisions":len(batch),
                "batch_resolved":accepted,
                "processed_anchors":seen,
                "required_anchors":len(anchors),
                "remaining_anchors":len(anchors)-seen,
                "model_trained":False,
                "live_admission":False,
                "research_only":True,
            }
        finally:
            con.close()
    finally:
        ctx.con.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--cache",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--target",required=True,choices=tuple(TARGETS))
    p.add_argument("--train-asof",type=int,required=True)
    p.add_argument("--last-starts",type=int,default=240)
    p.add_argument("--max-new",type=int,default=12)
    a=p.parse_args()
    result=run(a.db,a.cache,a.output,a.target,a.train_asof,
               last_starts=a.last_starts,max_new=a.max_new)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
