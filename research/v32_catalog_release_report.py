"""Evaluate all 236 frozen candidates against research evidence without promotion.

No model switching or deployment. Missing prospective evidence is NOT zero
success; it is 'not measured'. Every catalog item gets an explicit status.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

SCHEMA="torn-fren-v32-catalog-readiness-report-v1"
SOURCE="torn-fren-v32-prospective-single-tick-audit-v1"


def audit_catalog(catalog:dict,prospective:dict|None) -> dict:
    items=catalog.get("items") or {}
    if len(items)!=236 or catalog.get("all_live_promotions_prohibited") is not True:
        raise ValueError("only the frozen 236-item research catalog is supported")
    measured=(prospective or {}).get("items") or {}
    if prospective is not None and prospective.get("schema")!=SOURCE:
        raise ValueError("wrong prospective report schema")
    table=[]
    for key,entry in sorted(items.items()):
        selected=entry.get("current_provisional_candidate") or {}
        evidence=measured.get(key) or {}
        n=int(evidence.get("resolved_eligible_sessions") or 0)
        wins=int(evidence.get("successful_arrivals") or 0)
        coverage=evidence.get("coverage")
        rate=evidence.get("all_start_success")
        independent=evidence.get("qualified_independent_windows")
        flags=[]
        if not selected.get("model_family"):
            flags.append("NO_COMPLETE_FROZEN_MODEL")
        if n==0:
            flags.append("NO_PROSPECTIVE_OBSERVATIONS")
        elif n<30:
            flags.append("FEWER_THAN_30_PROSPECTIVE_STARTS")
        if independent is None or int(independent)<8:
            flags.append("INDEPENDENT_WINDOWS_NOT_CERTIFIED")
        if coverage is None or float(coverage)<.95:
            flags.append("COVERAGE_NOT_CERTIFIED")
        floor=.75 if key in ("arg:Monkey Plushie","swi:Chamois Plushie","uae:Camel Plushie") else .90
        if rate is None or float(rate)<floor:
            flags.append("ARRIVAL_TARGET_NOT_CERTIFIED")
        # No implicit promotion. External native parity and tested rollout
        # evidence cannot be inferred from this historical/prospective table.
        flags.append("NATIVE_PARITY_AND_ROLLBACK_RELEASE_GATE_PENDING")
        table.append({
            "item_key":key,"category":entry.get("category"),
            "candidate":selected.get("model_family","not assigned"),
            "configuration":selected.get("config_name"),
            "prospective_successes":wins if n else None,
            "prospective_starts":n if n else None,
            "prospective_all_start_rate":rate if n else None,
            "prospective_coverage":coverage if n else None,
            "independent_windows":int(independent) if independent is not None else None,
            "live_status":"RESEARCH_ONLY_BLOCKED",
            "blockers":flags,
        })
    return {"schema":SCHEMA,"item_count":236,"publicly_promoted":0,
       "has_prospective_evidence":sum(x["prospective_starts"] is not None for x in table),
       "all_public_promotions_prohibited":True,"rows":table}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",required=True)
    p.add_argument("--prospective-report",help="Only a verified V32 prospective JSON")
    p.add_argument("--output-json",required=True)
    p.add_argument("--output-csv",required=True)
    a=p.parse_args()
    data=json.loads(Path(a.registry).read_text())
    prospective=(json.loads(Path(a.prospective_report).read_text())
                 if a.prospective_report else None)
    outcome=audit_catalog(data,prospective)
    json_path=Path(a.output_json);csv_path=Path(a.output_csv)
    if json_path.exists() or csv_path.exists():
        raise SystemExit("Refusing to overwrite the prior release evidence")
    json_path.parent.mkdir(parents=True,exist_ok=True)
    csv_path.parent.mkdir(parents=True,exist_ok=True)
    json_path.write_text(json.dumps(outcome,indent=2)+"\n")
    fields=["item_key","category","candidate","configuration",
       "prospective_successes","prospective_starts","prospective_all_start_rate",
       "prospective_coverage","independent_windows","live_status","blockers"]
    with csv_path.open("w",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        for entry in outcome["rows"]:
            writer.writerow({**entry,"blockers":"; ".join(entry["blockers"])})
    print("items:",len(outcome["rows"]),"certified:",outcome["publicly_promoted"])


if __name__=="__main__":
    main()
