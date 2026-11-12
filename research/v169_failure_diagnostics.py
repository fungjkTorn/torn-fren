"""V169 read-only postmortem: stocked arrivals succeed regardless of timer offset.

Input: existing per-item V169 replay JSON (not live collector). Output is
diagnostic only; it neither reruns/changes a model nor writes to production.
'Near' is a disclosed sensitivity threshold (default 15 min), not an asserted
game-engine definition of early. Physical event identities remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def classify_execution(entry, *, grace=10, near_seconds=900):
    if type(grace) is not int or grace<0 or type(near_seconds) is not int or near_seconds<=0:
        raise ValueError("invalid explicit stock-grace/near-window policy")
    status=entry.get("arrival_state")
    if status=="SUCCESS":
        return "STOCKED_ARRIVAL_SUCCESS"
    if status=="UNKNOWN":
        return "UNKNOWN_STOCK_AT_LANDING"
    if status not in ("FAILURE", "SUCCESS", "UNKNOWN"):
        return "UNSCORED_EXECUTION"
    arrival=entry.get("arrival_epoch")
    target=entry.get("actual_target_restock_epoch")
    if type(arrival) is not int:
        raise ValueError("failed scored execution has no arrival")
    if type(target) is int and arrival+grace<target:
        seconds=target-(arrival+grace)
        return ("EARLY_MISS_BEFORE_NEAR_RESTOCK" if seconds<=near_seconds
                else "BEFORE_TARGETED_RESTOCK_NOT_NEAR")
    if entry.get("actual_target_status")=="CURRENT_STOCK_ALREADY_GE30":
        return "CURRENT_STOCK_WINDOW_EXPIRED_BEFORE_LANDING"
    if type(target) is int:
        return "STOCK_MISS_AFTER_TARGETED_RESTOCK"
    return "OTHER_STOCK_MISS_NO_TARGET"


def analyze_folder(folder, *, near_seconds=900):
    root=Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("expected extracted V169 report folder")
    summary=json.loads((root/"summary.json").read_text(encoding="utf-8"))
    items={}
    totals=Counter()
    for key,record in sorted(summary["results"].items()):
        if record.get("status")!="COMPLETED":
            items[key]={"status":record.get("status"),"classified":False}
            continue
        name=key.replace(":","__").replace(" ","_")
        if not name.replace("_","").isalnum():
            raise ValueError("unsafe item identifier")
        p=root/(name+".json")
        data=json.loads(p.read_text(encoding="utf-8"))
        if data.get("item_key")!=key:
            raise ValueError("item JSON/summary mismatch")
        counts=Counter(classify_execution(e,near_seconds=near_seconds)
                       for e in data["actionable_executions"])
        observed=data.get("execution_counts",{})
        if sum(counts.values())!=observed.get("executions"):
            raise ValueError("execution count disagreement: "+key)
        if counts["STOCKED_ARRIVAL_SUCCESS"]!=observed.get("arrival_success",0):
            raise ValueError("success count disagreement: "+key)
        nknown=counts["STOCKED_ARRIVAL_SUCCESS"]+sum(v for k,v in counts.items()
            if k in ("EARLY_MISS_BEFORE_NEAR_RESTOCK",
                     "BEFORE_TARGETED_RESTOCK_NOT_NEAR",
                     "CURRENT_STOCK_WINDOW_EXPIRED_BEFORE_LANDING",
                     "STOCK_MISS_AFTER_TARGETED_RESTOCK",
                     "OTHER_STOCK_MISS_NO_TARGET"))
        if nknown!=observed.get("arrival_known",0):
            raise ValueError("scored execution count disagreement: "+key)
        items[key]={"status":"COMPLETED","classified":True,
                    "executions":len(data["actionable_executions"]),
                    "known_arrivals":nknown,
                    "arrival_success_fraction":round(
                        counts["STOCKED_ARRIVAL_SUCCESS"]/nknown,6) if nknown else None,
                    "outcomes":dict(counts)}
        totals.update(counts)
    return {"status":"V169_RESEARCH_POSTMORTEM_READ_ONLY",
            "near_restock_window_seconds":near_seconds,
            "arrival_grace_seconds":10,
            "success_overrides_predicted_restock_offset":True,
            "unknown_not_scored_as_failure":True,
            "restock_reference":"HISTORICAL_EARLIEST_REACHABLE_TARGET_NOT_EXACT_LIVE_RESTOCK_TIME",
            "completed_items":sum(x["classified"] for x in items.values()),
            "failed_items":[k for k,v in items.items() if not v["classified"]],
            "outcomes":dict(totals),"items":items,
            "production_modified":False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-folder",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--near-seconds",type=int,default=900)
    a=ap.parse_args()
    source=a.source_folder.expanduser().resolve(strict=True)
    output=a.output.expanduser().resolve()
    if not output.parent.is_dir() or output.is_symlink():
        raise ValueError("output must be independent existing research JSON destination")
    if output.suffix!=".json" or output==source/"summary.json":
        raise ValueError("do not overwrite original research summary")
    result=analyze_folder(source,near_seconds=a.near_seconds)
    output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in
        ("status","completed_items","failed_items","outcomes")},sort_keys=True))


if __name__=="__main__":
    main()
