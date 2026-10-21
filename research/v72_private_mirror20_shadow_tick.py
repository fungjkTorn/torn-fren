"""V72 research-only 20-specialist PRIVATE scheduled candidate.

Runs Monkey's original 24-expert, 2-day resolved bank against one fresh
immutable private snapshot FIRST, then the source-pinned V65 original 19
under their unchanged 19-job/220-second/30-second per-worker budget.
Separate sidecar preserves V65's private_predictions.db rollback untouched.

Monkey's V66 causal/source guard is never bypassed. If Monkey abstains, an
explicit NULL-departure abstention is recorded and the original 19 proceed.
No automatic travel, website routing or production database writes.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from research import v65_private_mirror_shadow_tick as v65
from research import v68_monkey_isolated_canary as monkey
from research.v38_budgeted_runner import run_tick
from research.v38_capacity_guard import inspect as capacity_guard
from research.v38_prediction_store import open_writer,record
from research.v57_exception_fingerprint import fingerprint
from research.v60_private_snapshot_probe import approved_collector_source,read_heartbeat
from research.v63_full_mirror_smoke import exact_roster,source_age

SOURCE=v65.SOURCE
ROOT=v65.ROOT
SNAPSHOT=ROOT/"v72_stock_snapshot.db"
SIDECAR=ROOT/"v72_private_predictions.db"
MONKEY_CACHE=monkey.CACHE
V65_SIDECAR=v65.SIDECAR
STEP=300
FAILURE_STATUSES={"V72_PREFLIGHT_ERROR","V72_SNAPSHOT_ERROR",
                  "V72_RUNNER_ERROR","V72_FINAL_FRESHNESS_ERROR"}


def safe(status,**values):
    return {"status":status,"research_only":True,
            "collector_written":False,"public_routing_changed":False,
            "v65_sidecar_written":False,"v48_cache_written":False,
            "published_to_website":False,
            "actual_player_departure":False,**values}


def error(stage,exc):
    return safe(f"V72_{stage}_ERROR",**fingerprint(exc))


def snapshot_heartbeat(path):
    p=Path(path).resolve(strict=True)
    with sqlite3.connect(p.as_uri()+"?mode=ro&immutable=1",uri=True,timeout=5) as c:
        c.execute("PRAGMA query_only=ON")
        return read_heartbeat(c)


def record_monkey_abstention(sidecar,heartbeat,monkey_status,*,now):
    # V48 can fall behind, or a source revision can invalidate cache. These
    # are legitimate research abstentions, never synthetic recommendations.
    status="MONKEY_CACHE_OR_SOURCE_ABSTENTION"
    connection=open_writer(sidecar)
    try:
        return record(connection,key=monkey.KEY,family=monkey.FAMILY,
                      config=monkey.CONFIG,output={"status":status},
                      now=now,stock_as_of=heartbeat,executed=True,
                      next_due=now+STEP,elapsed_ms=0)
    finally:
        connection.close()


def tick(*,source=SOURCE,snapshot=SNAPSHOT,sidecar=SIDECAR,
         cache=MONKEY_CACHE,snapshotter=v65.snapshot_with_retry,
         monkey_runner=monkey.canary,infer=run_tick,
         capacity_probe=capacity_guard,clock=time.time,
         abstain_writer=record_monkey_abstention):
    src=Path(source).resolve(strict=True)
    dst=Path(snapshot).resolve(strict=False)
    ledger=Path(sidecar).resolve(strict=False)
    evidence=Path(cache).resolve(strict=True)
    if len({src,dst,ledger,evidence})!=4 or ledger==V65_SIDECAR.resolve(strict=False):
        raise ValueError("research inputs/outputs must be isolated from V65")
    keys=exact_roster()
    if len(keys)!=19 or monkey.KEY in keys:
        raise ValueError("original 19 or Monkey identity changed")

    cap=capacity_probe()
    if not cap.get("allowed"):
        return safe("V72_DEFERRED_CPU_PRESSURE",executed_count=0)

    try:
        snap=snapshotter(src,dst)
    except Exception as exc:
        return error("SNAPSHOT",exc)
    if snap.get("status")!="PRIVATE_SNAPSHOT_READY" or not snap.get("published"):
        return safe("V72_NO_FRESH_SNAPSHOT",snapshot_status=snap.get("status"),executed_count=0)

    try:
        hb=snapshot_heartbeat(dst)
    except Exception as exc:
        return error("HEARTBEAT",exc)
    now=int(clock())
    if hb is None or not 0<=now-hb<=180:
        return safe("V72_SOURCE_STALE",executed_count=0,
                    source_heartbeat_age_seconds=None if hb is None else now-hb)

    # Monkey must execute BEFORE the long original-19 loop to avoid V48
    # source watermark advancing beyond this frozen snapshot as in V69.
    try:
        result20=monkey_runner(
            source=src,snapshot=dst,cache=evidence,sidecar=ledger,
            snapshotter=lambda a,b:snap,clock=clock,
        )
        if not isinstance(result20,dict):
            raise TypeError("Monkey result must be an object")
    except Exception as exc:
        result20=monkey.no_write_result("V72_MONKEY_RUNNER_EXCEPTION",
                                       **fingerprint(exc))

    monkey_ok=result20.get("status")==monkey.SUCCESS
    monkey_info={
        "monkey_status":result20.get("status"),
        "monkey_validator_status":result20.get("monkey_validator_status"),
        "monkey_cached_decisions":result20.get("cached_decisions"),
        "monkey_missing_decisions":result20.get("missing_decisions"),
        "monkey_expert_index":result20.get("chosen_expert_index"),
        "monkey_source_parity":result20.get("source_parity_one_slot"),
        "monkey_proposal_count":int(monkey_ok),
    }
    if not monkey_ok:
        try:
            # Do not carry forward the old valid Monkey row when current
            # causal evidence fails; explicit abstention updates the latest.
            abstain_writer(ledger,hb,result20.get("status"),now=int(clock()))
        except Exception as exc:
            return error("MONKEY_ABSTENTION_RECORD",exc)

    # Existing V65 scheduler algorithm, exact same 19 routing, caps, and
    # five-minute due cadence; only private sidecar/snapshot paths change.
    try:
        baseline=infer(
            stock_db=dst,sidecar_db=ledger,execute=True,
            with_xanax=True,with_redfox=True,
            approved_keys=keys,
            max_jobs=19,worker_seconds=30,budget_seconds=220,
            max_rows=10000,
        )
    except Exception as exc:
        return error("RUNNER",exc)
    rows=baseline.get("executed",[])
    try:
        age=source_age(dst,clock=clock)
    except Exception as exc:
        return error("FINAL_FRESHNESS",exc)

    original_proposals=sum(r.get("status")=="RESEARCH_PROPOSAL_ONLY" for r in rows)
    error_count=sum(str(r.get("status","")).endswith("_ERROR") for r in rows)
    stale_count=sum(r.get("status")=="COLLECTOR_STALE_OR_NO_HEARTBEAT" for r in rows)
    mode=baseline.get("mode","UNKNOWN")
    freshness_ok=isinstance(age,int) and 0<=age<=180
    status=("V72_EXECUTED_RESEARCH_ONLY" if freshness_ok else
            "V72_SNAPSHOT_EXPIRED_POST_CYCLE")
    if mode!="EXECUTED_RESEARCH_ONLY":
        status="V72_DEFERRED_"+str(mode)[:40]
    return safe(
        status,
        runner_mode=mode,
        expected_roster_size=20,
        snapshot=snap,
        end_heartbeat_age_seconds=age,
        snapshot_fresh_after_cycle=freshness_ok,
        original_19_executed_count=len(rows),
        original_19_proposal_count=original_proposals,
        executed_count=len(rows)+int(monkey_ok),
        proposal_count=original_proposals+int(monkey_ok),
        original_19_error_count=error_count,
        original_19_stale_count=stale_count,
        **monkey_info,
    )


def preflight():
    if not approved_collector_source(SOURCE):
        raise ValueError("collector must be source-pinned")
    if not ROOT.resolve(strict=True).is_dir():
        raise ValueError("private research directory missing")
    if not MONKEY_CACHE.is_file() or MONKEY_CACHE.is_symlink():
        raise ValueError("V48 cache absent or unsafe")
    for p in (SNAPSHOT,SIDECAR):
        if p.parent.resolve(strict=True)!=ROOT.resolve(strict=True) or p.is_symlink():
            raise ValueError("output path outside private research directory")
    if SIDECAR.resolve(strict=False)==V65_SIDECAR.resolve(strict=False):
        raise ValueError("V65 rollback sidecar protected")
    exact_roster()


def main():
    try:
        preflight()
        out=tick()
    except Exception as exc:
        out=error("PREFLIGHT",exc)
    print(json.dumps(out,sort_keys=True))
    if out["status"] in FAILURE_STATUSES or out["status"].endswith("_ERROR"):
        raise SystemExit(1)


if __name__=="__main__":
    main()
