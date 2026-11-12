"""V70 Monkey-first FULL 20-specialist one-shot research smoke.

The V69 baseline-first test let V48's live cache advance 115 seconds beyond
its frozen SQLite snapshot; the V66 source revision guard correctly refused
that mismatch. V70 freezes source ONCE, validates Monkey immediately, then
runs V63's original 19 using that SAME immutable snapshot. No timer/website/
production routing changes. Never weaken the V66 source revision check.
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
SNAPSHOT=ROOT/"v70_full20_stock_snapshot.db"
SIDECAR=ROOT/"v70_full20_private_canary.db"
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
           r[6] is None or r[7] is None or int(r[7])<=int(r[6]) or
           int(r[6])<now
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


def revision_evidence(snapshot,cache):
    """Report numeric source/cache watermarks only, never weakening the gate.

    A cache watermark above the frozen source max is consistent with V48
    racing ahead during V69's long baseline. It is not proof the underlying
    cache is safe or that no genuine source reset occurred.
    """
    source=sqlite3.connect(Path(snapshot).as_uri()+"?mode=ro&immutable=1",
                           uri=True,timeout=5)
    ledger=None
    try:
        max_id=int(source.execute(
            "SELECT COALESCE(MAX(id),0) FROM stock_history").fetchone()[0])
        ledger=sqlite3.connect(Path(cache).as_uri()+"?mode=ro",
                               uri=True,timeout=5)
        state=ledger.execute(
            "SELECT source_max_id FROM expert_source_state WHERE item_key=?",
            (MONKEY,)).fetchone()
        seen=int(state[0]) if state else None
        return {"snapshot_max_stock_id":max_id,
                "cache_source_max_stock_id":seen,
                "cache_ahead_by_rows":max(0,seen-max_id) if seen is not None else None}
    finally:
        if ledger is not None:
            ledger.close()
        source.close()


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
        return safe("V70_DEFERRED_CPU_PRESSURE",baseline_count=0)

    # Refuse reusing prior canary evidence. The production V65 sidecar is
    # separate and untouched. An abandoned previous V70 attempt should never
    # silently fill the missing 20th row on a later attempt.
    if side.exists() or any(Path(str(side)+suffix).exists()
                            for suffix in ("-wal","-shm","-journal")):
        return safe("V70_SIDECAR_ALREADY_EXISTS",baseline_count=0)

    start=time.monotonic()
    try:
        snap=snapshotter(src,dst)
    except Exception as exc:
        return safe("V70_SNAPSHOT_ERROR",**fingerprint(exc))
    if snap.get("status")!="PRIVATE_SNAPSHOT_READY" or not snap.get("published"):
        return safe("V70_SNAPSHOT_NOT_READY",snapshot_status=snap.get("status"))

    # V48 may advance its live cache while 19 other models run. Validate
    # Monkey first against the newest one-time immutable snapshot.
    result20=monkey_runner(
        source=src,snapshot=dst,sidecar=side,cache=cache,
        snapshotter=lambda a,b:snap,clock=clock,
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
        if evidence["monkey_validator_status"]=="V66_CACHE_SOURCE_RESET_OR_MISMATCH":
            try:
                evidence.update(revision_evidence(dst,cache))
            except (OSError,sqlite3.Error,ValueError):
                evidence["revision_watermarks_unavailable"]=True
        return safe("V70_MONKEY_NOT_READY",**evidence)

    # Force the 19 previously approved specialists to use exactly the
    # same frozen snapshot; V63's helper does not take another backup.
    result19=original_runner(
        source=src,snapshot=dst,sidecar=side,
        snapshotter=lambda a,b:snap,clock=clock,
    )
    rows=result19.get("results",[])
    baseline={
        "baseline_status":result19.get("status"),
        "baseline_count":len(rows),
        "baseline_proposals":result19.get("proposal_count",0),
        "baseline_native_errors":result19.get("native_error_count",0),
        "baseline_snapshot_age":result19.get("end_heartbeat_age_seconds"),
    }
    if (result19.get("status")!="V63_FULL_MIRROR_EXECUTED" or
        len(rows)!=19 or
        {r.get("item_key") for r in rows}!=set(keys) or
        any(r.get("status")!="RESEARCH_PROPOSAL_ONLY" for r in rows) or
        not isinstance(baseline["baseline_snapshot_age"],int) or
        not 0<=baseline["baseline_snapshot_age"]<=MAX_AGE):
        return safe("V70_BASELINE_NOT_READY",**baseline,**evidence)
    try:
        committed=verify_rows(side,set(keys)|{MONKEY},clock=clock)
    except Exception as exc:
        return safe("V70_SIDECAR_VERIFICATION_ERROR",
                    **fingerprint(exc),**baseline,**evidence)
    if (committed["persisted_count"]!=EXPECTED or
        not committed["persisted_keys_exact"] or
        committed["persisted_invalid_keys"] or
        not committed["monkey_family_exact"]):
        return safe("V70_SIDECAR_MISMATCH",**baseline,**evidence,**committed)
    return safe("V70_FULL20_ISOLATED_SMOKE_PASSED",
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
        output=safe("V70_PREFLIGHT_ERROR",**fingerprint(exc))
    print(json.dumps(output,sort_keys=True))
    # A canary which does not verify all 20 is not a completed smoke even
    # if abstention is an expected safety outcome.
    if output["status"] not in (
        "V70_FULL20_ISOLATED_SMOKE_PASSED","V70_DEFERRED_CPU_PRESSURE"
    ):
        raise SystemExit(1)


if __name__=="__main__":
    main()
