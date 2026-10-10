"""V63 one-shot full 19-model mirror smoke. Does NOT switch private timers.

Exactly the currently enabled 16 source-pinned adapters, two generic
Canada/UK Xanax specialists, and Red Fox, using a single DELETE-mode private
SQLite snapshot and a SEPARATE sidecar. Five missing specialists stay absent.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from research.v60_private_snapshot_probe import approved_collector_source, snapshot_once
from research.v38_budgeted_runner import run_tick
from research.v38_readonly_resource_probe import ALL as PINNED
from research.v42_xanax_candidate_tick import ALLOWED as XANAX
from research.v38_budgeted_runner import RED_FOX_KEY

SOURCE=Path("/opt/torn-fren/data/stock_history.db")
ROOT=Path("/var/lib/torn-fren-v38")
SNAPSHOT=ROOT/"v63_stock_snapshot.db"
SIDECAR=ROOT/"v63_mirror_smoke.db"
LIVE_SIDECAR=ROOT/"private_predictions.db"
MAX_JOBS=19
WALL_BUDGET=220
WORKER_SECONDS=30
HEARTBEAT_MAX_AGE=180


def exact_roster():
    # Refuse silently altered/replaced champion mappings.
    keys=tuple(sorted(set(PINN)|set(XANAX)|{RED_FOX_KEY}))
    if len(PINN)!=16 or len(XANAX)!=2 or len(keys)!=19:
        raise ValueError("unexpected research roster size")
    if RED_FOX_KEY in PINN or RED_FOX_KEY in XANAX or set(PINN)&set(XANAX):
        raise ValueError("overlapping research model keys")
    return keys


def source_age(snapshot:Path,*,clock=time.time):
    # Snapshot is immutable, so its own heartbeat is the correct TTL proof.
    with sqlite3.connect(snapshot.as_uri()+"?mode=ro&immutable=1",uri=True) as db:
        hb=db.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
                         WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
    return None if hb is None else int(clock())-int(hb)


def smoke(*,source=SOURCE,snapshot=SNAPSHOT,sidecar=SIDECAR,
          snapshotter=snapshot_once, infer=run_tick, clock=time.time):
    source=Path(source).resolve(strict=True)
    snapshot=Path(snapshot).resolve(strict=False)
    sidecar=Path(sidecar).resolve(strict=False)
    if source==snapshot or snapshot==sidecar or sidecar in (source,LIVE_SIDECAR.resolve()):
        raise ValueError("research smoke cannot write collector or active sidecar")
    keys=exact_roster()
    snapshot_result=snapshotter(source,snapshot)
    if not snapshot_result.get("published") or snapshot_result.get("status")!="PRIVATE_SNAPSHOT_READY":
        return {"status":"V63_SNAPSHOT_NOT_READY","research_only":True,
                "snapshot":snapshot_result,"executed_count":0}
    if not snapshot.is_file():
        raise RuntimeError("published snapshot missing")
    # This is intentionally a live-clock test: later workers must abstain
    # if the snapshot heartbeat has aged outside the normal 180-second gate.
    result=infer(stock_db=snapshot,sidecar_db=sidecar,execute=True,
                 with_xanax=True,with_redfox=True,
                 approved_keys=keys,active=keys,
                 max_jobs=MAX_JOBS,worker_seconds=WORKER_SECONDS,
                 budget_seconds=WALL_BUDGET,max_rows=10000)
    rows=result.get("executed",[])
    tested={r["item_key"] for r in rows if r.get("item_key")}
    return {
        "status": ("V63_FULL_MIRROR_EXECUTED" if result.get("mode")==
                   "EXECUTED_RESEARCH_ONLY" else "V63_FULL_MIRROR_DEFERRED"),
        "mode":result.get("mode"),
        "research_only":True,
        "collector_written":False,
        "public_routing_changed":False,
        "snapshot":snapshot_result,
        "end_heartbeat_age_seconds":source_age(snapshot,clock=clock),
        "expected_models":len(keys),
        "executed_count":len(rows),
        "missing_model_keys":sorted(set(keys)-tested),
        "proposal_count":sum(r.get("status")=="RESEARCH_PROPOSAL_ONLY" for r in rows),
        "native_error_count":sum(str(r.get("status","")).endswith("_ERROR") for r in rows),
        "timeout_count":sum(r.get("status")=="WORKER_TIMEOUT" for r in rows),
        "stale_count":sum(r.get("status")=="COLLECTOR_STALE_OR_NO_HEARTBEAT" for r in rows),
        "deferred_budget_count":sum(r.get("status")=="DEFERRED_BUDGET" for r in rows),
        "results":rows,
    }


def main():
    # Strict fixed source/destination: no arbitrary CLI path overrides.
    if not approved_collector_source(SOURCE) or not ROOT.is_dir():
        raise SystemExit("STOP: production source/private output preflight failed")
    for path in (SNAPSHOT,SIDECAR):
        if path.parent.resolve(strict=True)!=ROOT.resolve(strict=True):
            raise SystemExit("STOP: private output escapes research directory")
        if path.is_symlink():
            raise SystemExit("STOP: private output cannot be symlink")
    try:
        output=smoke()
    except Exception as exc:
        output={"status":"V63_SMOKE_ERROR","research_only":True,
                "error_type":type(exc).__name__}
    print(json.dumps(output,sort_keys=True))


if __name__=="__main__":
    main()
