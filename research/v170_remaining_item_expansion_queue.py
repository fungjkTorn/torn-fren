"""Build an evidence-aware expansion queue from the 236-item champion registry.

The queue is planning only. Historical development rates were consulted during
model selection and are not unbiased live confidence estimates. Strong legacy
entries are therefore marked REVALIDATE, never auto-promoted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.v167_event_candidate_scoring import CHAMPION_KIND


def classify(entry):
    cur=entry.get("current_provisional_candidate") or {}
    old=entry.get("original_all_item_selection") or {}
    family=str(cur.get("model_family") or old.get("model_family") or "unknown").lower()
    rate=old.get("development_arrival_success_rate")
    starts=old.get("development_starts") or 0

    if "quantity_requalified" in family:
        tier="NEW_TOURNAMENT_REQUIRED"
    elif family=="quantity_below_30":
        tier="QUANTITY_LIMITED_OLD_SNAPSHOT"
    elif family=="depart_now_baseline":
        tier="BASELINE_ONLY"
    elif "specialist" in family:
        tier="SPECIALIST_REVIEW"
    elif family in {"v19","v20","v21"}:
        if rate is not None and starts>=30 and rate>=.90:
            tier="STRONG_REVALIDATE"
        elif rate is not None and starts>=30 and rate>=.75:
            tier="MODERATE_REVALIDATE"
        elif rate is not None and starts>=30:
            tier="WEAK_NEEDS_RESEARCH"
        else:
            tier="INSUFFICIENT_EVIDENCE"
    else:
        tier="INSUFFICIENT_EVIDENCE"
    return tier,family,rate,starts


def build(registry):
    data=json.loads(Path(registry).read_text(encoding="utf-8"))
    items=data.get("items",data)
    current=set(CHAMPION_KIND)
    rows=[]
    for key,entry in sorted(items.items()):
        if not isinstance(entry,dict) or ":" not in key or key in current:
            continue
        tier,family,rate,starts=classify(entry)
        cur=entry.get("current_provisional_candidate") or {}
        old=entry.get("original_all_item_selection") or {}
        rows.append({
            "item_key":key,
            "category":entry.get("category"),
            "tier":tier,
            "model_family":family,
            "config_name":cur.get("config_name",old.get("config_name")),
            "old_development_arrival_success_rate":rate,
            "old_development_hits":old.get("development_hits"),
            "old_development_starts":starts,
            "promotion_status":"RESEARCH_ONLY_BLOCKED",
        })
    order={
        "STRONG_REVALIDATE":0,"MODERATE_REVALIDATE":1,
        "SPECIALIST_REVIEW":2,"WEAK_NEEDS_RESEARCH":3,
        "NEW_TOURNAMENT_REQUIRED":4,"BASELINE_ONLY":5,
        "QUANTITY_LIMITED_OLD_SNAPSHOT":6,"INSUFFICIENT_EVIDENCE":7,
    }
    rows.sort(key=lambda x:(
        order.get(x["tier"],99),
        -(x["old_development_arrival_success_rate"] or -1),
        -(x["old_development_starts"] or 0),
        x["item_key"],
    ))
    counts={}
    for r in rows:counts[r["tier"]]=counts.get(r["tier"],0)+1
    return {
        "schema":"torn-fren-remaining-item-expansion-queue-v1",
        "current_research_roster_size":len(current),
        "remaining_registry_items":len(rows),
        "counts":dict(sorted(counts.items())),
        "warning":(
            "Legacy development rates were used during prior model selection. "
            "They rank revalidation priority only and are not unbiased live confidence."
        ),
        "queue":rows,
        "production_modified":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--registry",
        default="research/all_236_champions_v26.json",
        type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--top",type=int,default=30)
    a=p.parse_args()
    report=build(a.registry)
    out=a.output or Path("research/v170_remaining_item_expansion_queue.json")
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "counts":report["counts"],
        "top":[{
            "item":r["item_key"],"tier":r["tier"],
            "model":r["model_family"],"config":r["config_name"],
            "old_rate":r["old_development_arrival_success_rate"],
            "n":r["old_development_starts"],
        } for r in report["queue"][:a.top]],
        "output":str(out),
    },indent=2,sort_keys=True))


if __name__=="__main__":
    main()
