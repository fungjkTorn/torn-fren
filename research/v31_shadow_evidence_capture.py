"""V31 prospective *capture-only* ledger for private V2-vs-challenger shadow.

Run manually after collecting the PRIVATE V29 API JSON response. No network,
gameplay, API keys, automatic scheduling, or writes to the stock collector DB.

The CLI records actual wall-clock capture time (not backdated starts).
Decisions with no challenger proposal still count in future coverage analyses.
No result in this ledger is scored as success before the arrival resolves.
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import time
from pathlib import Path

SCHEMA="torn-fren-private-research-shadow-v29"
EXPERIMENT_PATTERN=re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SOURCE_SCHEMA="torn-fren-v31-shadow-evidence-capture-v1"

CREATE_TABLE="""
CREATE TABLE IF NOT EXISTS shadow_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    item_key TEXT NOT NULL,
    tick_epoch INTEGER NOT NULL,
    recorded_at INTEGER NOT NULL,
    source_schema TEXT NOT NULL,
    candidate_model_family TEXT,
    candidate_config TEXT,
    challenger_status TEXT NOT NULL,
    challenger_executed INTEGER NOT NULL,
    challenger_departure INTEGER,
    challenger_arrival INTEGER,
    v2_status TEXT,
    v2_departure INTEGER,
    v2_arrival INTEGER,
    source_is_private INTEGER NOT NULL CHECK(source_is_private=1),
    live_routing_unchanged INTEGER NOT NULL CHECK(live_routing_unchanged=1),
    resolution_status TEXT NOT NULL DEFAULT 'PENDING',
    UNIQUE(experiment_id,item_key,tick_epoch)
)
"""


def _timestamp(value):
    return int(value) if type(value) is int and value>0 else None


def validate(snapshot,experiment_id):
    if not EXPERIMENT_PATTERN.fullmatch(experiment_id):
        raise ValueError("invalid experiment_id")
    if not isinstance(snapshot,dict) or snapshot.get("schema")!=SCHEMA:
        raise ValueError("expected only the V29 private research response")
    if (snapshot.get("mode")!="READ_ONLY_DIAGNOSTIC" or
        snapshot.get("default_live_routing")!="UNCHANGED" or
        snapshot.get("candidate_promoted") is not False or
        snapshot.get("chance_calibrated") is not False):
        raise ValueError("not a safe frozen research response")
    key=snapshot.get("key")
    if not isinstance(key,str) or not re.fullmatch(r"[a-z]{3}:[^:]{1,120}",key):
        raise ValueError("invalid item key")
    if not isinstance(snapshot.get("baseline"),dict):
        raise ValueError("missing V2 baseline")
    if not isinstance(snapshot.get("challenger"),dict):
        raise ValueError("missing explicit challenger outcome")
    return key


def record_private_decision(
    db_path:str|Path,
    snapshot:dict,
    experiment_id:str,
    *,
    now:int|None=None,
) -> dict:
    key=validate(snapshot,experiment_id)
    ts=int(time.time()) if now is None else int(now)
    if ts<=0:
        raise ValueError("invalid capture time")
    baseline=snapshot["baseline"]
    challenger=snapshot["challenger"]
    executed=(challenger.get("status")=="RESEARCH_PROPOSAL_ONLY" and
              challenger.get("champion_executed") is True and
              snapshot.get("champion_executed") is True)
    if snapshot.get("champion_executed") is True and not executed:
        raise ValueError("inconsistent challenger outcome")
    row=(experiment_id,key,(ts//300)*300,ts,SOURCE_SCHEMA,
         str(snapshot.get("candidate_model_family") or ""),
         str(snapshot.get("candidate_config") or ""),
         str(challenger.get("status") or "UNKNOWN"),
         int(executed),
         _timestamp(challenger.get("recommended_departure_timestamp")) if executed else None,
         _timestamp(challenger.get("recommended_arrival_timestamp")) if executed else None,
         str(baseline.get("status") or "unavailable"),
         _timestamp(baseline.get("recommended_leave_by_timestamp")),
         _timestamp(baseline.get("recommended_arrival_timestamp")),
         1,1)
    target=Path(db_path)
    if target.is_file():
        # Never append evidence tables to the actual stock collector database,
        # even if an operator supplies a differently named archive filename.
        with sqlite3.connect(target.resolve().as_uri()+"?mode=ro",uri=True) as probe:
            old=probe.execute("""SELECT name FROM sqlite_master WHERE type='table'
                                 AND name IN ('stock_history','collection_gaps')
                                 LIMIT 1""").fetchone()
        if old is not None:
            raise ValueError("refusing to alter a stock collector database")
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(target,timeout=15) as con:
        con.execute(CREATE_TABLE)
        cur=con.execute("""
        INSERT OR IGNORE INTO shadow_decisions
        (experiment_id,item_key,tick_epoch,recorded_at,source_schema,
         candidate_model_family,candidate_config,challenger_status,
         challenger_executed,challenger_departure,challenger_arrival,
         v2_status,v2_departure,v2_arrival,source_is_private,
         live_routing_unchanged) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,row)
        inserted=cur.rowcount==1
        old=con.execute("""SELECT id,recorded_at FROM shadow_decisions
                           WHERE experiment_id=? AND item_key=? AND tick_epoch=?""",
                        (experiment_id,key,(ts//300)*300)).fetchone()
    return {"status":"RECORDED" if inserted else "DUPLICATE_TICK_IGNORED",
            "id":old[0],"tick_epoch":(ts//300)*300,
            "source":SOURCE_SCHEMA,"challenger_executed":executed}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot",required=True,
                   help="Local JSON file from the private research endpoint")
    p.add_argument("--evidence-db",required=True,
                   help="Separate research SQLite, NEVER stock_history.db")
    p.add_argument("--experiment-id",required=True)
    a=p.parse_args()
    target=Path(a.evidence_db).resolve()
    raw=Path(a.snapshot).resolve(strict=True)
    if target==raw or target.name in ("stock_history.db","torn-fren-stock-history-fresh.db"):
        p.error("evidence must not overwrite original stock history/database")
    snapshot=json.loads(raw.read_text(encoding="utf-8"))
    result=record_private_decision(target,snapshot,a.experiment_id)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
