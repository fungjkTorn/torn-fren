#!/usr/bin/env python3
"""Pinned, read-only, ON-DEMAND single-item V151 recheck.

This script never writes private V160 prospective issues and never updates the
collector. One user-requested item at the current time, both baseline variants.
Never treat its previews as mature independent forward-validation evidence.
"""
from __future__ import annotations
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

WORK=Path("/home/ubuntu/torn-fren-v38-probe")
STAGE=Path("/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research")
COLLECTOR=Path("/opt/torn-fren/data/stock_history.db")
BASE_ROSTER=STAGE/"v38_roster.json"
EXTRA=frozenset(("can:Xanax","uni:Xanax"))
MAX_GAPS=15000
SOURCE_AGE_LIMIT=180
SAMPLE_COUNT=48
MAX_LATENCY=90


def pinned_modules(*,stage=STAGE,work=WORK):
    """Never fall back to the mutable worktree for missing research modules."""
    stage=Path(stage).resolve(strict=True)
    sys.path.insert(0,str(Path(work).resolve(strict=True)))
    import research
    research.__path__=[str(stage)]
    from research.plushie_champions.common import TRAVEL_SECONDS
    from research.v128_full24_earliest_shadow import _read_item
    from research.v60_private_snapshot_probe import read_heartbeat
    from research.v145_provider_continuous_phases import provider_continuous_phases
    from research.v151_stable_earliest_departure import stable_earliest_departure
    for name,m in tuple(sys.modules.items()):
        if (name.startswith("research.") and getattr(m,"__file__",None)
            and not Path(m.__file__).resolve().is_relative_to(stage)):
            raise RuntimeError("unverified transitive recheck import: "+name)
    return TRAVEL_SECONDS,_read_item,read_heartbeat,provider_continuous_phases,stable_earliest_departure


def recheck(item_key,*,now_fn=time.time,mono_fn=time.monotonic,
            source=COLLECTOR,roster=BASE_ROSTER,modules=None):
    """One current causal item recheck, with strict heartbeat/issue limits."""
    issued=int(now_fn())
    entries=json.loads(Path(roster).read_text(encoding="utf8"))["items"]
    if (len(entries)!=22 or set(entries)&EXTRA or
        not isinstance(item_key,str) or item_key not in set(entries)|EXTRA):
        raise ValueError("unknown item key / unexpected research roster")
    travel,read_item,read_heartbeat,continuous,model=modules or pinned_modules()
    country,name=item_key.split(":",1)
    if country not in travel:
        raise ValueError("unapproved travel country")
    src=Path(source).resolve(strict=True)
    if not src.is_file():
        raise ValueError("read-only collector source unavailable")
    start=mono_fn()
    with closing(sqlite3.connect(src.as_uri()+"?mode=ro",uri=True,timeout=10)) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        try:
            hb=read_heartbeat(con)
            hb_age=issued-hb if type(hb) is int else None
            if hb_age is None or not 0<=hb_age<=SOURCE_AGE_LIMIT:
                raise ValueError("stale or missing global collector heartbeat")
            gaps=con.execute(
                """SELECT start_timestamp,end_timestamp FROM collection_gaps
                   WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?""",
                (issued,MAX_GAPS+1)
            ).fetchall()
            if len(gaps)>MAX_GAPS:
                raise ValueError("unbounded gaps in current collector history")
            obs,error=read_item(con,item_key,issued)
            if error or not obs:
                raise ValueError("missing or invalid item stock history")
            phases=continuous(obs,asof=issued,gaps=gaps)
            last=phases["last_observation"]
            variants={}
            for variant in ("independent","paired_complete"):
                res=model(item_key,phases,asof=issued,scenarios=SAMPLE_COUNT,
                          cycle_sampling=variant)
                picked=res.get("first_reachable")
                variants[variant]={
                    "status":res.get("status"),
                    "departure_epoch":picked.get("departure_epoch") if picked else None,
                    "arrival_epoch":picked.get("arrival_epoch") if picked else None,
                    "scenario_stock_fraction":picked.get("scenario_stock_fraction") if picked else None,
                    "sustained_five_minute_support":(
                        picked.get("two_adjacent_5min_bins") if picked else None),
                    "needs_reconfirmation":picked.get("needs_reconfirmation") if picked else None,
                }
        finally:
            con.execute("ROLLBACK")
    latency=int(now_fn())-issued
    if latency<0 or latency>MAX_LATENCY:
        raise ValueError("recheck expired during calculation")
    for variant in variants.values():
        dep,arr=variant["departure_epoch"],variant["arrival_epoch"]
        if dep is not None and (type(dep) is not int or type(arr) is not int
            or dep<issued or dep>issued+28800 or arr!=dep+travel[country]):
            raise ValueError("invalid newly issued flight geometry")
    return {
        "status":"CURRENT_ITEM_RECHECK_RESEARCH_ONLY",
        "item_key":item_key,"issued_epoch":issued,"checked_at_epoch":int(now_fn()),
        "source_heartbeat_age_seconds":hb_age,
        "source_last_epoch":last.epoch if last else None,
        "source_last_quantity":last.quantity if last else None,
        "source_provider":last.source if last else None,
        "flight_seconds":travel[country],
        "models":variants,
        "min_arrival_stock":30,"arrival_grace_seconds":10,
        "research_only":True,"private_ledger_written":False,
        "collector_written":False,"forecast_not_prospectively_recorded":True,
        "country_source_freshness_verified":False,
        "real_player_arrival_verified":False,
        "scenario_fraction_is_calibrated":False,
    }


def main():
    if len(sys.argv)!=2:
        raise SystemExit("Usage: recheck.py exact-item-key")
    try:
        print(json.dumps(recheck(sys.argv[1]),sort_keys=True))
    except (ValueError,RuntimeError,sqlite3.Error,OSError) as exc:
        print(json.dumps({"status":"RECHECK_UNAVAILABLE",
             "research_only":True,
             "note":"Live collector or model issue unavailable; no departure supported"}))
        raise SystemExit(2) from None


if __name__=="__main__":
    main()
