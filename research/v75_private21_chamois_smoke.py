"""V75: opt-in private 21-model research candidate (Chamois + V72 original20).

No service installation. A SINGLE fresh read-only SQLite collector snapshot
is used for original Chamois first, then the unchanged V72 Monkey+19 scheduler.
All rows go to an isolated V75 sidecar, NOT the active V72 website database.
Source watermark/fingerprint/parity guards remain mandatory. Chamois cache
abstentions write explicit NULL departure; V72 still proceeds. No game action.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

from research import v65_private_mirror_shadow_tick as v65
from research import v72_private_mirror20_shadow_tick as v72
from research import v74_chamois_isolated_canary as chamois
from research.v38_prediction_store import open_writer, record
from research.v38_capacity_guard import inspect as capacity_guard
from research.v57_exception_fingerprint import fingerprint
from research.v60_private_snapshot_probe import approved_collector_source

ROOT=Path("/var/lib/torn-fren-v38")
SOURCE=v65.SOURCE
SNAPSHOT=ROOT/"v75_stock_snapshot.db"
SIDECAR=ROOT/"v75_private_predictions.db"
CACHE=chamois.CACHE
PROTECTED={ROOT/"private_predictions.db",ROOT/"v72_private_predictions.db"}
MAX_FRESH_SECONDS=180
SUCCESS="V75_PRIVATE21_RESEARCH_EXECUTED"


def safe(status,**fields):
    return {"status":status,"research_only":True,
            "collector_written":False,"public_routing_changed":False,
            "website_sidecar_written":False,"v65_sidecar_written":False,
            "v72_sidecar_written":False,"v48_cache_written":False,
            "model_21_scheduled":False,**fields}


def fail(stage,exc):
    return safe(f"V75_{stage}_ERROR",**fingerprint(exc))


def record_chamois_abstention(sidecar,heartbeat,*,clock=time.time):
    now=int(clock())
    c=open_writer(sidecar)
    try:
        return record(c,key=chamois.KEY,family=chamois.FAMILY,
                      config=chamois.CONFIG,
                      output={"status":"CHAMOIS_CACHE_OR_SOURCE_ABSTENTION"},
                      now=now,stock_as_of=heartbeat,executed=True,
                      next_due=now+300)
    finally:
        c.close()


def tick(*,source=SOURCE,snapshot=SNAPSHOT,sidecar=SIDECAR,cache=CACHE,
         snapshotter=v65.snapshot_with_retry,
         chamois_runner=chamois.canary,baseline_runner=v72.tick,
         capacity_probe=capacity_guard,clock=time.time,
         abstain_writer=record_chamois_abstention):
    src=Path(source).resolve(strict=True)
    dst=Path(snapshot).resolve(strict=False)
    ledger=Path(sidecar).resolve(strict=False)
    evidence=Path(cache).resolve(strict=True)
    prohibited={p.resolve(strict=False) for p in PROTECTED}
    if len({src,dst,ledger,evidence})!=4 or ledger in prohibited:
        raise ValueError("V75 requires isolated private source/snapshot/cache/sidecar")
    cap=capacity_probe()
    if not cap.get("allowed"):
        return safe("V75_DEFERRED_CPU_PRESSURE")
    try:
        snap=snapshotter(src,dst)
    except Exception as exc:
        return fail("SNAPSHOT",exc)
    if snap.get("status")!="PRIVATE_SNAPSHOT_READY" or not snap.get("published"):
        return safe("V75_SNAPSHOT_NOT_READY",snapshot_status=snap.get("status"))
    try:
        hb=v72.snapshot_heartbeat(dst)
    except Exception as exc:
        return fail("SNAPSHOT_HEARTBEAT",exc)
    now=int(clock())
    if hb is None or not 0<=now-hb<=MAX_FRESH_SECONDS:
        return safe("V75_SOURCE_STALE",source_age_seconds=None if hb is None else now-hb)

    try:
        result=chamois_runner(
            source=src,snapshot=dst,cache=evidence,sidecar=ledger,
            snapshotter=lambda a,b:snap,clock=clock)
        if not isinstance(result,dict):
            raise TypeError("Chamois result should be dict")
    except Exception as exc:
        result=chamois.no_write_result("V75_CHAMOIS_EXCEPTION",
                                      **fingerprint(exc))
    accepted=result.get("status")==chamois.SUCCESS
    if not accepted:
        try:
            abstain_writer(ledger,hb,clock=clock)
        except Exception as exc:
            return fail("CHAMOIS_ABSTENTION",exc)

    # V72 is unchanged, including Monkey-first source validation, exact 19
    # routing, max_jobs=19, original worker_seconds=30 and 220s wall budget.
    try:
        base=baseline_runner(
            source=src,snapshot=dst,sidecar=ledger,cache=evidence,
            snapshotter=lambda a,b:snap,clock=clock,
            capacity_probe=lambda:{"allowed":True})
    except Exception as exc:
        return fail("V72_BASELINE",exc)
    if not isinstance(base,dict):
        return safe("V75_BASELINE_NOT_READY",baseline_status="NOT_AN_OBJECT")
    base_status=base.get("status","UNKNOWN")
    source_fresh=base.get("snapshot_fresh_after_cycle") is True
    success=base_status=="V72_EXECUTED_RESEARCH_ONLY" and source_fresh
    return safe(
        SUCCESS if success else "V75_BASELINE_NOT_READY",
        v72_baseline_status=base_status,
        v72_original_19_proposals=base.get("original_19_proposal_count",0),
        v72_monkey_proposals=base.get("monkey_proposal_count",0),
        v72_original_19_errors=base.get("original_19_error_count"),
        v72_original_19_stale=base.get("original_19_stale_count"),
        chamois_proposals=int(accepted),
        chamois_status=result.get("status"),
        chamois_validator=result.get("chamois_validator_status"),
        chamois_cached_decisions=result.get("cached_decisions"),
        chamois_missing_decisions=result.get("missing_decisions"),
        chamois_expert_index=result.get("chosen_expert_index"),
        chamois_source_parity=result.get("source_parity_one_slot"),
        total_proposals=(base.get("proposal_count",0)+int(accepted)),
        model_roster_size=21,
        source_fresh_after_cycle=source_fresh,
        end_source_age_seconds=base.get("end_heartbeat_age_seconds"),
        snapshot_heartbeat=hb,
    )


def preflight():
    if not approved_collector_source(SOURCE):
        raise ValueError("V75 collector must be pinned")
    if not ROOT.is_dir() or not ROOT.resolve(strict=True).is_dir():
        raise ValueError("missing private root")
    if not CACHE.is_file() or CACHE.is_symlink():
        raise ValueError("missing/unsafe V48 cache")
    for p in (SNAPSHOT,SIDECAR):
        if p.is_symlink() or p.parent.resolve(strict=True)!=ROOT.resolve(strict=True):
            raise ValueError("unsafe V75 output")
    if SIDECAR.resolve(strict=False) in {p.resolve(strict=False) for p in PROTECTED}:
        raise ValueError("existing sidecar protected")


def main():
    try:
        preflight()
        result=tick()
    except Exception as exc:
        result=fail("PREFLIGHT",exc)
    print(json.dumps(result,sort_keys=True))
    if result["status"].endswith("_ERROR") or result["status"] in (
        "V75_BASELINE_NOT_READY","V75_SNAPSHOT_NOT_READY","V75_SOURCE_STALE"):
        raise SystemExit(1)


if __name__=="__main__":
    main()
