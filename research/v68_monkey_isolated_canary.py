"""V68 opt-in, one-shot Monkey original-selector canary, isolated from V65.

Never changes the scheduled 19-model roster, production stock DB, V48 cache,
the existing private prediction sidecar, or public website. Fail closed.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from research.v38_prediction_store import open_writer, record
from research.v47_online_expert_cache import EXPERTS
from research.v60_private_snapshot_probe import (
    approved_collector_source, snapshot_once, read_heartbeat,
)
from research.v66_monkey_readonly_selector_probe import audit
from research.plushie_champions.common import TRAVEL_SECONDS, STEP, MAX_WAIT
from research.v57_exception_fingerprint import fingerprint

SOURCE=Path("/opt/torn-fren/data/stock_history.db")
ROOT=Path("/var/lib/torn-fren-v38")
SNAPSHOT=ROOT/"v68_monkey_snapshot.db"
SIDECAR=ROOT/"v68_monkey_canary.db"
CACHE=Path("/var/lib/torn-fren-v47/online_expert_cache.db")
ACTIVE=ROOT/"private_predictions.db"
KEY="arg:Monkey Plushie"
FAMILY="online_template_expert"
CONFIG="original_24_experts_2d_resolved_selector"
SUCCESS="V68_MONKEY_ISOLATED_RECORD_READY"


def no_write_result(status,**extra):
    return {"status":status,"research_only":True,"collector_written":False,
            "live_prediction_sidecar_written":False,
            "v48_cache_written":False,"published_to_website":False,
            "model_20_admitted":False,**extra}


def safe_error(stage,exc):
    return no_write_result(f"V68_{stage}_ERROR",**fingerprint(exc))


def snapshot_heartbeat(snapshot):
    conn=sqlite3.connect(Path(snapshot).as_uri()+"?mode=ro&immutable=1",
                         uri=True,timeout=5)
    try:
        return read_heartbeat(conn)
    finally:
        conn.close()


def canary(*,source=SOURCE,snapshot=SNAPSHOT,cache=CACHE,sidecar=SIDECAR,
           snapshotter=snapshot_once,validator=audit,clock=time.time,
           writer=open_writer):
    src=Path(source).resolve(strict=True)
    dst=Path(snapshot).resolve(strict=False)
    evidence=Path(cache).resolve(strict=True)
    isolated=Path(sidecar).resolve(strict=False)
    paths={src,dst,evidence,isolated}
    if len(paths)!=4 or isolated==ACTIVE.resolve(strict=False):
        raise ValueError("canary source, mirror, evidence, and sidecar must differ")
    began=time.monotonic()
    try:
        snap=snapshotter(src,dst)
    except Exception as exc:
        return safe_error("SNAPSHOT",exc)
    if snap.get("status")!="PRIVATE_SNAPSHOT_READY" or not snap.get("published"):
        return no_write_result("V68_NO_FRESH_SNAPSHOT",snapshot=snap)
    try:
        heartbeat=snapshot_heartbeat(dst)
        if heartbeat is None or not 0<=int(clock())-heartbeat<=180:
            return no_write_result("V68_STALE_SNAPSHOT_BEFORE_VALIDATION")
        proof=validator(dst,evidence,clock=clock)
    except Exception as exc:
        return safe_error("VALIDATION",exc)
    status=proof.get("status")
    evidence_fields={
        "monkey_validator_status":status,
        "cached_decisions":proof.get("cached_decisions"),
        "missing_decisions":proof.get("missing_decisions"),
        "chosen_expert_index":proof.get("chosen_expert_index"),
        "source_parity_one_slot":proof.get("source_parity_one_slot"),
        "elapsed_seconds":round(time.monotonic()-began,2),
    }
    if status!="V66_MONKEY_SELECTOR_VALIDATED":
        return no_write_result("V68_MONKEY_ABSTAIN",**evidence_fields)
    if (proof.get("item_key")!=KEY or proof.get("missing_decisions")!=0 or
        proof.get("invalid_rows")!=0 or proof.get("source_parity_one_slot") is not True or
        not isinstance(proof.get("chosen_expert_index"),int) or
        not 0<=proof["chosen_expert_index"]<len(EXPERTS)):
        return no_write_result("V68_REJECTED_INCOMPLETE_PROOF",**evidence_fields)
    departure=proof.get("recommended_departure_timestamp")
    current=int(clock())
    if (type(departure) is not int or
        not current<=departure<=current+MAX_WAIT or
        not 0<=current-int(heartbeat)<=180):
        return no_write_result("V68_STALE_OR_PASSED_DEPARTURE",**evidence_fields)

    # This is a private CANARY row only, not a production prediction. Apply
    # the unchanged 5-minute/8-hour/30-quantity/+10-second contract.
    output={
        "status":"RESEARCH_PROPOSAL_ONLY",
        "recommended_departure_timestamp":departure,
        "recommended_arrival_timestamp":departure+TRAVEL_SECONDS["arg"],
        "quantity_threshold":30,"grace_seconds":10,
        "replan_step_seconds":STEP,"probability_calibrated":False,
        "research_only":True,"gameplay_automated":False,
    }
    try:
        con=writer(isolated)
        try:
            saved=record(con,key=KEY,family=FAMILY,config=CONFIG,
                         output=output,now=current,stock_as_of=int(heartbeat),
                         executed=True,next_due=current+STEP,
                         elapsed_ms=round((time.monotonic()-began)*1000))
        finally:
            con.close()
    except Exception as exc:
        return safe_error("ISOLATED_RECORD",exc)
    if saved!="RESEARCH_PROPOSAL_ONLY":
        return no_write_result("V68_RECORD_ABSTAINED",saved_status=saved,
                               **evidence_fields)
    return no_write_result(SUCCESS,
        isolated_canary_row_written=True,
        private_snapshot_age_seconds=current-int(heartbeat),
        **evidence_fields)


def main():
    try:
        if not approved_collector_source(SOURCE):
            raise ValueError("source must equal approved collector")
        if not ROOT.is_dir():
            raise ValueError("private research directory missing")
        for p in (SNAPSHOT,SIDECAR):
            if p.parent.resolve(strict=True)!=ROOT.resolve(strict=True) or p.is_symlink():
                raise ValueError("unsafe research output")
        if not CACHE.is_file() or CACHE.is_symlink():
            raise ValueError("V48 research cache missing")
        result=canary()
    except Exception as exc:
        result=safe_error("PREFLIGHT",exc)
    print(json.dumps(result,sort_keys=True))
    if result["status"].endswith("_ERROR"):
        raise SystemExit(1)


if __name__=="__main__":
    main()
