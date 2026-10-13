"""V160 opt-in, prospective 24-item private V151 research issuance.

Captures independent and directly paired V151 *before* an actual flight can
arrive; no retrospective retrofitting of old hours. The default is preview,
with NO files written. Recording requires explicit --record, to a separate
private research sidecar. Collector is mode=ro and query_only; current
incumbent roster metadata is NOT a verified incumbent forecast.
No gameplay, Torn API calls, worker/website/collector changes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from research.v128_full24_earliest_shadow import (
    COLLECTOR, PRIVATE_ROOT, _read_item, exact_roster, GLOBAL_HEARTBEAT_LIMIT,
    MAX_VALID_ISSUE_LATENCY
)
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v151_stable_earliest_departure import stable_earliest_departure
from research.v60_private_snapshot_probe import read_heartbeat, approved_collector_source

DESTINATION = PRIVATE_ROOT / "v160_v151_prospective24.db"
POLICY = "v160_v151_independent_paired_asissued_20261013"
MODEL_VARIANTS = ("independent", "paired_complete")
MAX_RUNTIME_SECONDS = 105
SCENARIOS = 48
MAX_GAPS = 15000


def _source(source, destination, *, canonical):
    src=Path(source).resolve(strict=True)
    dst=Path(destination)
    if not src.is_file() or dst.is_symlink() or not dst.name.endswith(".db"):
        raise ValueError("invalid source or sidecar")
    if src==dst.resolve(strict=False):
        raise ValueError("collector and sidecar must differ")
    if canonical:
        if (not approved_collector_source(src) or
            dst.resolve(strict=False)!=DESTINATION):
            raise ValueError("nonapproved production source/private destination")
    elif src.resolve(strict=True)==dst.resolve(strict=False):
        raise ValueError("test collector cannot be destination")
    if not dst.parent.is_dir():
        raise ValueError("sidecar parent missing")
    return src,dst


def _abstain(key, issued, reason, meta=None):
    return {
        "item_key":key,"issued_epoch":issued,"policy_id":POLICY,
        "decision_status":reason,"phase":None,"phase_onset":None,
        "source_last_epoch":None,"source_last_qty":None,
        "source_last_provider":None,"incumbent_model_family":(
            meta or {}).get("incumbent_model_family"),
        "incumbent_forecast_evaluated":False,
        "country_provider_freshness_verified":False,
        "research_only":True,"published_to_website":False,
        "models":{
            variant:{"status":reason,"departure_epoch":None,
                     "arrival_epoch":None,"wait_seconds":None,
                     "scenario_fraction":None}
            for variant in MODEL_VARIANTS
        },
    }


def _freeze_forecast(out):
    choice=out.get("first_reachable")
    status=out.get("status")
    if choice is None:
        return {"status":status,"departure_epoch":None,"arrival_epoch":None,
                "wait_seconds":None,"scenario_fraction":None}
    return {"status":status,"departure_epoch":choice["departure_epoch"],
            "arrival_epoch":choice["arrival_epoch"],
            "wait_seconds":choice["wait_seconds"],
            "scenario_fraction":choice["scenario_stock_fraction"]}


def capture_once(*,source=COLLECTOR,destination=DESTINATION,
                 roster=None,now_fn=time.time,mono_fn=time.monotonic,
                 record=False,canonical=True,scenarios=SCENARIOS,
                 max_seconds=MAX_RUNTIME_SECONDS,issued_epoch=None):
    """One 24-item snapshot, using a single read transaction and known issue time.

    No prediction is assigned to a tick after its issue-time freshness
    window expires. Source heartbeat and phase state are pinned to one
    collector transaction. Every item is recorded even on abstention.
    """
    if (type(scenarios) is not int or not 8<=scenarios<=96 or
        not 1<=max_seconds<=MAX_RUNTIME_SECONDS):
        raise ValueError("unbounded forward shadow resource request")
    src,dst=_source(source,destination,canonical=canonical)
    roster=exact_roster() if roster is None else roster
    if len(roster)!=24 or any(":" not in k for k in roster):
        raise ValueError("forward shadow must have exactly 24 items")
    issued=int(now_fn() if issued_epoch is None else issued_epoch)
    if issued<=0 or (issued_epoch is not None and abs(int(now_fn())-issued)>5):
        raise ValueError("an issuance cannot be backdated or future-dated")
    start=mono_fn()
    predictions={}
    hb=None
    with closing(sqlite3.connect(src.as_uri()+"?mode=ro",uri=True,timeout=12)) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        try:
            hb=read_heartbeat(con)
            age=issued-hb if hb is not None else None
            fresh=age is not None and 0<=age<=GLOBAL_HEARTBEAT_LIMIT
            gaps=[]
            if fresh:
                gaps=con.execute(
                    """SELECT start_timestamp,end_timestamp FROM collection_gaps
                       WHERE start_timestamp<=? ORDER BY start_timestamp
                       LIMIT ?""",(issued,MAX_GAPS+1)).fetchall()
                if len(gaps)>MAX_GAPS:
                    fresh=False
            for key,meta in sorted(roster.items()):
                if not fresh:
                    predictions[key]=_abstain(key,issued,"ABSTAIN_STALE_HEARTBEAT_OR_GAPS",meta)
                    continue
                if mono_fn()-start>=max_seconds:
                    predictions[key]=_abstain(key,issued,"ABSTAIN_CPU_BUDGET",meta)
                    continue
                obs,error=_read_item(con,key,issued)
                if error or not obs:
                    predictions[key]=_abstain(
                        key,issued,"ABSTAIN_"+(error or "NO_STOCK_HISTORY"),meta)
                    continue
                periods=provider_continuous_phases(
                    obs,asof=issued,gaps=gaps)
                last=periods["last_observation"]
                independent=stable_earliest_departure(
                    key,periods,asof=issued,scenarios=scenarios,
                    cycle_sampling="independent")
                paired=stable_earliest_departure(
                    key,periods,asof=issued,scenarios=scenarios,
                    cycle_sampling="paired_complete")
                predictions[key]={
                    "item_key":key,"issued_epoch":issued,"policy_id":POLICY,
                    "decision_status":"RESEARCH_ONLY",
                    "phase":periods["phase"],
                    "phase_onset":periods["phase_onset"],
                    "source_last_epoch":last.epoch if last else None,
                    "source_last_qty":last.quantity if last else None,
                    "source_last_provider":last.source if last else None,
                    "completed_high_periods":len(periods["stocked_durations"]),
                    "completed_low_periods":len(periods["depleted_durations"]),
                    "incumbent_model_family":meta.get("incumbent_model_family"),
                    "incumbent_forecast_evaluated":False,
                    "country_provider_freshness_verified":False,
                    "research_only":True,"published_to_website":False,
                    "models":{
                        "independent":_freeze_forecast(independent),
                        "paired_complete":_freeze_forecast(paired),
                    },
                }
        finally:
            con.execute("ROLLBACK")
    captured=int(now_fn())
    latency=captured-issued
    if latency<0 or latency>MAX_VALID_ISSUE_LATENCY:
        for key,meta in sorted(roster.items()):
            predictions[key]=_abstain(key,issued,"ABSTAIN_OVERDUE_CAPTURE",meta)
    if set(predictions)!=set(roster):
        raise AssertionError("incomplete 24-item capture")
    out={
        "policy_id":POLICY,
        "issued_epoch":issued,"captured_epoch":captured,
        "source_heartbeat_epoch":hb,
        "source_heartbeat_age_seconds":issued-hb if hb is not None else None,
        "latency_seconds":latency,
        "scenarios_per_model":scenarios,
        "roster_count":len(predictions),
        "research_only":True,"collector_written":False,
        "incumbent_forecasts_verified":False,
        "website_modified":False,
        "actual_player_flights_verified":False,
        "private_sidecar_written":bool(record),
        "predictions":predictions,
    }
    if record:
        write_private_sidecar(dst,out)
    return out


def write_private_sidecar(dst, result):
    """Append immutable private issue rows, no writes to collector/V128/V75."""
    if dst.is_symlink() or dst.name!="v160_v151_prospective24.db":
        raise ValueError("unapproved private sidecar")
    if len(result["predictions"])!=24:
        raise ValueError("incomplete prospectively issued batch")
    with closing(sqlite3.connect(dst,timeout=12)) as con:
        con.execute("PRAGMA busy_timeout=12000")
        con.execute("""CREATE TABLE IF NOT EXISTS v160_ticks(
            issued_epoch INTEGER PRIMARY KEY,
            captured_epoch INTEGER NOT NULL,
            source_heartbeat_epoch INTEGER,
            policy_id TEXT NOT NULL,
            roster_count INTEGER NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS v160_issued(
            item_key TEXT NOT NULL,
            issued_epoch INTEGER NOT NULL,
            policy_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(item_key,issued_epoch,policy_id)
        )""")
        issued=result["issued_epoch"]
        # Never silently replace a preexisting issue's historical forecast.
        exists=con.execute("SELECT 1 FROM v160_ticks WHERE issued_epoch=?",
                           (issued,)).fetchone()
        if exists:
            raise ValueError("duplicate issue epoch: immutable forward issuance")
        con.execute("INSERT INTO v160_ticks VALUES(?,?,?,?,?)",(
            issued,result["captured_epoch"],result["source_heartbeat_epoch"],
            POLICY,24))
        con.executemany("INSERT INTO v160_issued VALUES(?,?,?,?)",[
            (key,issued,POLICY,json.dumps(result["predictions"][key],sort_keys=True))
            for key in sorted(result["predictions"])
        ])
        con.commit()
    os.chmod(dst,0o600)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument("--preview",action="store_true")
    mode.add_argument("--record",action="store_true")
    a=p.parse_args()
    result=capture_once(record=a.record)
    # Keep the default 24 rows available to inspect in preview, compact in record mode.
    if a.record:
        result={k:v for k,v in result.items() if k!="predictions"}
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
