"""V69 one-off FULL 20-specialist research smoke, no scheduler activation.

Runs the existing frozen 19 original champions via V63, then the validated
Monkey via V68 against ONE immutable private DELETE-mode stock snapshot.
Uses ONE isolated prediction ledger for all 20. Never mutates the existing
V65 19-model sidecar, public routing or V48 expert resolution cache.

Fail closed if any of the 19 baseline champions abstain/error, Monkey's
historical 24-expert bank/parity is incomplete, or snapshot ages >180s.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from research import v63_full_mirror_smoke as original
from research import v68_monkey_isolated_canary as monkey
from research.v60_private_snapshot_probe import approved_collector_source, snapshot_once
from research.v38_capacity_guard import inspect as capacity_status
from research.v57_exception_fingerprint import fingerprint

SOURCE=Path("/opt/torn-fren/data/stock_history.db")
ROOT=Path("/var/lib/torn-fren-v38")
SNAPSHOT=ROOT/"v69_full20_stock_snapshot.db"
SIDECAR=ROOT/"v69_full20_private_canary.db"
CACHE=Path("/var/lib/torn-fren-v47/online_expert_cache.db")
PRIVATE_LIVE=ROOT/"private_predictions.db"
MONKEY=monkey.KEY
EXPECTED=20
MAX_AGE=180


def safe(status, **data):
    return {
        "status":status,"research_only":True,"public_routing_changed":False,
        "collector_written":False,"v48_cache_written":False,
        "live_sidecar_written":False,"model_20_admitted":False,**data,
    }


def verify_rows(sidecar,expected_keys,clock=time.time):
    """Re-read actually PERSISTED isolated sidecar, not just log lines."""
    p=Path(sidecar).resolve(strict=True)
    with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=5) as db:
        rows=db.execute("""SELECT item_key,status,model_family,model_config,
                                  computed_at,stock_as_of,departure,arrival
                             FROM latest_predictions""").fetchall()
    keys={r[0] for r in rows}
    now=int(clock())
    bad=[
        r[0] for r in rows
        if r[1]!="RESEARCH_PROPOSAL_ONLY" or
           not 0<=now-int(r[4])<=MAX_AGE or
           not 0<=int(r[4])-int(r[5])<=MAX_AGE or
           r[6] is None or r[7] is None or int(r[7])<=int(r[6])
    ]
    monkey_rows=[r for r in rows if r[0]==MONKEY]
    return {
        "persisted_count":len(rows),
        "persisted_keys_exact":keys==set(expected_keys) and len(rows)==len(keys),
        "persisted_invalid_keys":sorted(bad),
        "monkey_family_exact":len(monkey_rows)==1 and
             monkey_rows[0][2]==monkey.FAMILY and
             monkey_rows[0][3]==monkey.CONFIG,
    }


def run(*,source=SOURCE,snapshot=SNAPSHOT,sidecar=SIDECAR,cache=CACHE,
        original_runner=original.smoke,monkey_runner=monkey.canary,
        snapshotter=snapshot_once,capacity_probe=capacity_status,clock=time.time):
    src=Path(source).resolve(strict=True)
    dst=Path(snapshot).resolve(strict=False)
    side=Path(sidecar).resolve(strict=False)
    cache=Path(cache).resolve(strict=True)
    if len({src,dst,side,cache})!=4 or side==PRIVATE_LIVE.resolve(strict=False):
        raise ValueError("V69 inputs/outputs must be isolated")
    keys=original.exact_roster()
    if len(keys)!=19 or MONKEY in keys:
        raise ValueError("original nineteen no longer source pinned")

    cap=capacity_probe()
    if not cap.get("allowed"):
        return safe("V69_DEFERRED_CPU_PRESSURE",baseline_count=0)

    start=time.monotonic()
    result19=original_runner(
        source=src,snapshot=dst,sidecar=side,
        snapshotter=snapshotter,clock=clock,
    )
    rows=result19.get("results",[])
    baseline={
        "baseline_status":result19.get("status"),
        "baseline_count":len(rows),
        "baseline_proposals":result19.get("proposal_count",0),
        "baseline_native_errors":result19.get("native_error_count",0),
        "baseline_snapshot_age":result19.get("end_heartbeat_age_seconds"),
    }
    # Not enough to have 19 labels in a fake journal: verify all original
    # frozen routes had a successful research candidate this ONE cycle.
    if (result19.get("status")!="V63_FULL_MIRROR_EXECUTED" or
        len(rows)!=19 or
        {r.get("item_key") for r in rows}!=set(keys) or
        any(r.get("status")!="RESEARCH_PROPOSAL_ONLY" for r in rows) or
        not isinstance(baseline["baseline_snapshot_age"],int) or
        not 0<=baseline["baseline_snapshot_age"]<=MAX_AGE):
        return safe("V69_BASELINE_NOT_READY",**baseline)

    # The V63 helper already produced and verified this immutable snapshot.
    # Reuse that verified copy instead of making a second collector backup.
    snap=result19["snapshot"]
    result20=monkey_runner(
        source=src,snapshot=dst,sidecar=side,cache=cache,
        snapshotter=lambda a,b: snap,clock=clock,
    )
    evidence={
        "monkey_status":result20.get("status"),
        "monkey_validator_status":result20.get("monkey_validator_status"),
        "monkey_cached_decisions":result20.get("cached_decisions"),
        "monkey_missing_decisions":result20.get("missing_decisions"),
        "monkey_expert_index":result20.get("chosen_expert_index"),
        "monkey_source_parity":result20.get("source_parity_one_slot"),
    }
    if result20.get("status")!=monkey.SUCCESS:
        return safe("V69_MONKEY_NOT_READY",**baseline,**evidence)
    try:
        committed=verify_rows(side,set(keys)|{MONKEY},clock=clock)
    except Exception as exc:
        return safe("V69_SIDECAR_VERIFICATION_ERROR",
                    error_type=type(exc).__name__,
                    **fingerprint(exc),**baseline,**evidence)
    if (committed["persisted_count"]!=EXPECTED or
        not committed["persisted_keys_exact"] or
        committed["persisted_invalid_keys"] or
        not committed["monkey_family_exact"]):
        return safe("V69_SIDECAR_MISMATCH",**baseline,**evidence,**committed)
    return safe("V69_FULL20_ISOLATED_SMOKE_PASSED",
                expected_models=EXPECTED,
                proposal_count=EXPECTED,
                elapsed_seconds=round(time.monotonic()-start,2),
                **baseline,**evidence,**committed)


def main():
    try:
        if not approved_collector_source(SOURCE):
            raise ValueError("collector identity mismatch")
        if not ROOT.is_dir() or not CACHE.is_file() or CACHE.is_symlink():
            raise ValueError("required private inputs missing")
        for path in (SNAPSHOT,SIDECAR):
            if path.parent.resolve(strict=True)!=ROOT.resolve(strict=True) or path.is_symlink():
                raise ValueError("private output path invalid")
        output=run()
    except Exception as exc:
        output=safe("V69_PREFLIGHT_ERROR",**fingerprint(exc))
    print(json.dumps(output,sort_keys=True))
    if output["status"].endswith("_ERROR"):
        raise SystemExit(1)


if __name__=="__main__":
    main()
