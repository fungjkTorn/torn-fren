"""Research-only scanner for future-dependent tiny-restock labels.

This mirrors only the global leave-one-out PEAK comparison made by
history_service._build_validated_cycles. It intentionally does not claim to
recreate provider bounce cleaning, heartbeat coverage or complete model parity.
Reads SQLite strictly read-only; no API keys or writes to collector tables.
"""
from __future__ import annotations
import argparse, csv, json, sqlite3
from collections import defaultdict
from pathlib import Path


def completed_peaks(rows):
    out=[]; current=None
    for (previous_t,previous_q),(timestamp,qty) in zip(rows,rows[1:]):
        if previous_q==0 and qty>0:current=[int(timestamp),int(qty)]
        if current is not None and qty>current[1]:current[1]=int(qty)
        if previous_q>0 and qty==0 and current is not None:
            out.append((int(current[0]),int(timestamp),int(current[1])))
            current=None
    return out


def tiny_flags(cycles):
    peaks=[peak for _,_,peak in cycles]
    total=sum(peaks);n=len(peaks)
    return {
        start: bool(peak < ((total-peak)/(n-1))*0.10) if n>1 else False
        for start,_,peak in cycles
    }


def compare_one(rows,cutoff):
    cycles=completed_peaks(rows)
    before=[c for c in cycles if c[1]<=cutoff]
    full=tiny_flags(cycles)
    past=tiny_flags(before)
    mismatches=[int(c[0]) for c in before if full[c[0]]!=past[c[0]]]
    return {
       "all_completed_raw_cycles":len(cycles),
       "precutoff_raw_cycles":len(before),
       "future_peaks_change_tiny_flag_count":len(mismatches),
       "affected_cycle_start_timestamps":mismatches,
    }


def audit(db,cutoff):
    source=Path(db).resolve(strict=True)
    with sqlite3.connect(source.as_uri()+"?mode=ro",uri=True) as con:
        groups=defaultdict(list)
        for ts,country,item,qty in con.execute(
          "SELECT timestamp,country,item_name,quantity FROM stock_history "
          "ORDER BY country,item_name,timestamp"):
            groups[(str(country),str(item))].append((int(ts),int(qty)))
    results={}
    for (country,item),rows in sorted(groups.items()):
        results[country+":"+item]=compare_one(rows,int(cutoff))
    return {
        "schema":"torn-fren-future-dependent-tiny-cycle-audit-v29",
        "cutoff":int(cutoff),
        "warning":("RAW-CYCLE TRIAGE ONLY; original history_service uses "
                   "bounce suppression and collector coverage. "
                   "Zero flips does NOT prove causal engine parity."),
        "affected_keys":[key for key,v in results.items()
                          if v["future_peaks_change_tiny_flag_count"]>0],
        "results":results,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--cutoff",type=int,required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    data=audit(a.db,a.cutoff)
    output=Path(a.output)
    if output.exists():raise SystemExit("Refusing to overwrite an existing research audit")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    print("Catalog keys:",len(data["results"]),
          "future-dependent candidates:",len(data["affected_keys"]))
    print("Potentially affected keys:",", ".join(data["affected_keys"]) or "(none)")


if __name__=="__main__":
    main()
