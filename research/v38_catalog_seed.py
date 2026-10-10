"""Seed all 236 catalog prediction statuses without running a single model.

Frozen champion configs are read from the committed research registry.
An unsourced provisional candidate is NEVER presented as a live prediction.
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path

from research.v38_prediction_store import open_writer
from research.v38_readonly_resource_probe import ALL as ROUTED

ROOT=Path(__file__).resolve().parent


def status_for(key, candidate, roster):
    if key in ROUTED:
        return "BENCHMARK_GATED_ADAPTER",300
    if key in roster:
        return "SPECIALIST_NOT_INTEGRATED",3600
    family=(candidate or {}).get("model_family","")
    return {
        "quantity_below_30":("NOT_ACTIONABLE_QUANTITY",21600),
        "quantity_requalified_needs_new_tournament":("NEEDS_NEW_TOURNAMENT",21600),
        "best_effort_sparse":("INSUFFICIENT_HISTORY_WATCH_ONLY",21600),
        "depart_now_baseline":("V2_FALLBACK_ONLY",3600),
    }.get(family,("PROVISIONAL_FAMILY_NOT_INTEGRATED",3600))


def build_registry():
    full=json.loads((ROOT/"all_236_champions_v26.json").read_text())
    roster=json.loads((ROOT/"v38_roster.json").read_text())["items"]
    output={}
    for key,value in full["items"].items():
        candidate=value.get("current_provisional_candidate") or {}
        status,watch_seconds=status_for(key,candidate,roster)
        output[key]={
            "family":candidate.get("model_family") or "NONE",
            "config":candidate.get("config_name"),
            "status":status,"watch_seconds":watch_seconds,
            "live_adapter":key in ROUTED,
        }
    return output


def seed(sidecar_path, *, execute=False, now=None):
    roster=build_registry()
    if len(roster)!=236:
        raise ValueError("frozen 236-item roster no longer matches source")
    counts={}
    for item in roster.values():
        counts[item["status"]]=counts.get(item["status"],0)+1
    if not execute:
        return {"mode":"PLAN_ONLY","items":len(roster),"status_counts":counts}
    now=int(time.time() if now is None else now)
    con=open_writer(sidecar_path)
    try:
        with con:
            for key,item in roster.items():
                con.execute("""
                    INSERT OR IGNORE INTO latest_predictions
                    (item_key,model_family,model_config,status,computed_at,
                     stock_as_of,valid_until,next_due_at,departure,arrival,executed)
                    VALUES(?,?,?,?,?,?,?,?,?,?,0)
                """,(key,item["family"],item["config"],item["status"],now,
                      None,now+item["watch_seconds"],
                      now+item["watch_seconds"],None,None))
    finally:
        con.close()
    return {"mode":"SEEDED_FALLBACKS_ONLY","items":len(roster),
            "status_counts":counts,"collector_written":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sidecar",required=True)
    p.add_argument("--execute",action="store_true")
    a=p.parse_args()
    print(json.dumps(seed(a.sidecar,execute=a.execute),sort_keys=True,indent=2))


if __name__=="__main__":
    main()
