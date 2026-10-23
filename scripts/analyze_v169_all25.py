"""Analyze a completed V169 all-25 live-policy replay.

Produces machine-readable JSON plus a concise Markdown review containing:
- portfolio metrics
- per-item decision and execution metrics
- earliest-reachable-event correctness
- departure/restock timing error
- replan stability
- lifecycle telemetry carried forward from V2
- evidence-aware readiness flags

No model promotion is performed.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


TARGET_ARRIVAL=.90
TARGET_EARLIEST=.90
MIN_EXECUTIONS_FOR_STRONG=8
MIN_KNOWN_FOR_STRONG=25


def pct(x):
    return None if x is None else round(100*x,2)


def mins(x):
    return None if x is None else round(x/60.0,2)


def _load_items(folder):
    rows=[]
    for p in sorted(folder.glob("*.json")):
        if p.name in {"summary.json","manifest.json","analysis.json"}:
            continue
        try:
            d=json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d,dict) or "item_key" not in d:
            continue
        rows.append((p,d))
    return rows


def _stability(d):
    c=d.get("counts") or {}
    issues=c.get("issues",0) or 0
    stable=c.get("stable_replans",0) or 0
    return stable/max(1,issues-1) if issues>1 else None


def _later_event_rate(d):
    records=d.get("records") or []
    scored=[r for r in records if r.get("recommended_departure_epoch") is not None]
    if not scored:return None
    later=sum(1 for r in scored if (r.get("selected_reachable_rank") or 1)>1)
    return later/len(scored)


def _unknown_reasons(d):
    out={}
    for r in d.get("records") or []:
        st=r.get("arrival_state")
        if st in ("SUCCESS","FAILURE",None):
            continue
        out[st]=out.get(st,0)+1
    return dict(sorted(out.items(),key=lambda kv:(-kv[1],kv[0])))


def readiness(d):
    c=d.get("counts") or {}
    ec=d.get("execution_counts") or {}
    arrival=d.get("execution_arrival_success_fraction")
    if arrival is None:
        arrival=d.get("arrival_success_fraction")
    earliest=d.get("execution_earliest_target_hit_fraction")
    if earliest is None:
        earliest=d.get("earliest_target_hit_fraction")
    exec_known=ec.get("arrival_known",0) or 0
    known=c.get("arrival_known",0) or 0
    coverage=d.get("proposal_coverage")
    if arrival is not None and arrival<TARGET_ARRIVAL:
        return "NEEDS_MODEL_WORK"
    if earliest is not None and earliest<TARGET_EARLIEST:
        return "NEEDS_EVENT_WORK"
    if coverage is not None and coverage<.50:
        return "LOW_COVERAGE"
    if exec_known>=MIN_EXECUTIONS_FOR_STRONG and known>=MIN_KNOWN_FOR_STRONG:
        return "STRONG_EVIDENCE"
    if known>=MIN_KNOWN_FOR_STRONG:
        return "PROMISING_NEEDS_EXECUTIONS"
    return "INSUFFICIENT_EVIDENCE"


def summarize_item(path,d):
    c=d.get("counts") or {}
    ec=d.get("execution_counts") or {}
    life=d.get("latest_lifecycle_telemetry") or {}
    return {
        "item_key":d["item_key"],
        "champion_kind":(d.get("route") or {}).get("champion_kind"),
        "file":path.name,
        "readiness":readiness(d),
        "issues":c.get("issues",0),
        "proposals":c.get("proposals",0),
        "coverage":d.get("proposal_coverage"),
        "arrival_known":c.get("arrival_known",0),
        "arrival_success":d.get("arrival_success_fraction"),
        "earliest_scored":c.get("earliest_target_scored",0),
        "earliest_success":d.get("earliest_target_hit_fraction"),
        "executions":ec.get("executions",0),
        "execution_known":ec.get("arrival_known",0),
        "execution_arrival_success":d.get("execution_arrival_success_fraction"),
        "execution_earliest_success":d.get("execution_earliest_target_hit_fraction"),
        "median_departure_minus_oracle_minutes":mins(
            d.get("median_departure_minus_oracle_seconds")),
        "median_predicted_minus_actual_restock_minutes":mins(
            d.get("median_predicted_minus_actual_restock_seconds")),
        "replan_stability":_stability(d),
        "later_reachable_event_rate":_later_event_rate(d),
        "unknown_arrival_states":_unknown_reasons(d),
        "lifecycle":{
            "current_phase":life.get("current_phase"),
            "current_phase_age_minutes":mins(life.get("current_phase_age_seconds")),
            "avg_stocked_lifetime_minutes":mins(life.get("avg_stocked_lifetime_seconds")),
            "median_stocked_lifetime_minutes":mins(life.get("median_stocked_lifetime_seconds")),
            "avg_zero_to_restock_minutes":mins(life.get("avg_zero_to_restock_seconds")),
            "median_zero_to_restock_minutes":mins(life.get("median_zero_to_restock_seconds")),
            "avg_restock_interval_minutes":mins(life.get("avg_restock_interval_seconds")),
            "median_restock_interval_minutes":mins(life.get("median_restock_interval_seconds")),
            "avg_batch_size":life.get("avg_batch_size"),
            "median_batch_size":life.get("median_batch_size"),
            "valid_cycles":life.get("valid_cycles"),
            "excluded_cycles":life.get("excluded_cycles"),
        },
    }


def weighted(items,num_key,den_key):
    n=d=0
    for x in items:
        den=x.get(den_key) or 0
        val=x.get(num_key)
        if val is None or den<=0:continue
        n+=val*den;d+=den
    return n/d if d else None


def markdown(report):
    lines=[
        "# V169 All-25 Overnight Replay Review","",
        "## Portfolio","",
        f"- Items: **{report['items_complete']} / {report['items_expected']}**",
        f"- Decision arrival success: **{pct(report['portfolio']['arrival_success'])}%**",
        f"- Earliest-event hit: **{pct(report['portfolio']['earliest_success'])}%**",
        f"- Proposal coverage: **{pct(report['portfolio']['coverage'])}%**",
        f"- Actionable execution arrival success: **{pct(report['portfolio']['execution_arrival_success'])}%**",
        f"- Actionable execution earliest-event hit: **{pct(report['portfolio']['execution_earliest_success'])}%**",
        "",
        "## Per item","",
        "| Item | Route | Readiness | Coverage | Arrival | Earliest | Exec | Exec arrival | Median restock error | Replan stable |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for x in report["items"]:
        lines.append(
            f"| {x['item_key']} | {x.get('champion_kind') or '-'} | {x['readiness']} | "
            f"{pct(x['coverage']) if x['coverage'] is not None else '-'}% | "
            f"{pct(x['arrival_success']) if x['arrival_success'] is not None else '-'}% | "
            f"{pct(x['earliest_success']) if x['earliest_success'] is not None else '-'}% | "
            f"{x['executions']} | "
            f"{pct(x['execution_arrival_success']) if x['execution_arrival_success'] is not None else '-'}% | "
            f"{x['median_predicted_minus_actual_restock_minutes'] if x['median_predicted_minus_actual_restock_minutes'] is not None else '-'}m | "
            f"{pct(x['replan_stability']) if x['replan_stability'] is not None else '-'}% |"
        )
    lines+=["","## Attention queue",""]
    for x in report["attention_queue"]:
        lines.append(
            f"- **{x['item_key']} — {x['readiness']}**: "
            f"arrival={pct(x['arrival_success'])}%, earliest={pct(x['earliest_success'])}%, "
            f"coverage={pct(x['coverage'])}%, executions={x['executions']}."
        )
    return "\n".join(lines)+"\n"


def analyze(folder,expected=25):
    pairs=_load_items(folder)
    items=[summarize_item(p,d) for p,d in pairs]
    items.sort(key=lambda x:x["item_key"])
    attention=[x for x in items if x["readiness"] not in (
        "STRONG_EVIDENCE","PROMISING_NEEDS_EXECUTIONS")]
    severity={
        "NEEDS_MODEL_WORK":0,"NEEDS_EVENT_WORK":1,"LOW_COVERAGE":2,
        "INSUFFICIENT_EVIDENCE":3,"PROMISING_NEEDS_EXECUTIONS":4,
        "STRONG_EVIDENCE":5,
    }
    attention.sort(key=lambda x:(severity.get(x["readiness"],9),x["item_key"]))
    total_issues=sum(x["issues"] for x in items)
    total_props=sum(x["proposals"] for x in items)
    report={
        "schema":"v169-all25-analysis-v1",
        "items_expected":expected,
        "items_complete":len(items),
        "portfolio":{
            "coverage":total_props/total_issues if total_issues else None,
            "arrival_success":weighted(items,"arrival_success","arrival_known"),
            "earliest_success":weighted(items,"earliest_success","earliest_scored"),
            "execution_arrival_success":weighted(
                items,"execution_arrival_success","execution_known"),
            "execution_earliest_success":weighted(
                items,"execution_earliest_success","execution_known"),
        },
        "readiness_counts":{
            k:sum(1 for x in items if x["readiness"]==k)
            for k in sorted({x["readiness"] for x in items})
        },
        "items":items,
        "attention_queue":attention,
        "production_modified":False,
    }
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--json-output",type=Path)
    p.add_argument("--markdown-output",type=Path)
    a=p.parse_args()
    folder=a.input.expanduser().resolve(strict=True)
    report=analyze(folder)
    jout=(a.json_output or folder/"analysis.json").expanduser().resolve()
    mout=(a.markdown_output or folder/"analysis.md").expanduser().resolve()
    jout.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    mout.write_text(markdown(report),encoding="utf-8")
    print(json.dumps({
        "items":report["items_complete"],
        "portfolio":report["portfolio"],
        "attention":len(report["attention_queue"]),
        "json":str(jout),"markdown":str(mout)
    },sort_keys=True))


if __name__=="__main__":
    main()
