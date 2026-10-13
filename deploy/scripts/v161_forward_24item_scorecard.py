#!/usr/bin/env python3
"""Render V161 genuinely issued 24-item poll-backed forward scorecard.

Consumes one V161 report JSON from stdin; NEVER reads or edits production
collector, research ledger, websites, or player accounts.
"""
from __future__ import annotations

import json
import sys


def pct(hits,misses):
    n=hits+misses
    return "n/a" if n==0 else f"{100*hits/n:.1f}% ({hits}/{n})"


def scorecard(report):
    if (report.get("status")!="V161_TRUE_PROSPECTIVE_V151_24_ITEM_SHADOW_REPORT"
        or report.get("roster_size")!=24 or
        not isinstance(report.get("items"),dict) or len(report["items"])!=24 or
        report.get("historically_reconstructed_issues") is not False):
        raise ValueError("not the actual prospective 24-item V161 report")
    items=report["items"]
    rows=[]
    for key in sorted(items):
        item=items[key]
        independent=(item["independent_hit"],item["independent_miss"])
        paired=(item["paired_complete_hit"],item["paired_complete_miss"])
        if any(type(v) is not int or v<0 for v in (*independent,*paired,
               item["independent_pending"],item["paired_complete_pending"],
               item["independent_unknown"],item["paired_complete_unknown"],
               item["issued_item_hours"],item["unique_issued_stock_phases"],
               item["independent_abstain"],item["paired_complete_abstain"])):
            raise ValueError("invalid V161 item count")
        rows.append({
            "item":key,"hours":item["issued_item_hours"],
            "independent_rate":pct(*independent),
            "paired_rate":pct(*paired),
            "independent_evaluated":sum(independent),
            "paired_evaluated":sum(paired),
            "independent_pending":item["independent_pending"],
            "paired_pending":item["paired_complete_pending"],
            "independent_abstain":item["independent_abstain"],
            "paired_abstain":item["paired_complete_abstain"],
            "unique_phases":item["unique_issued_stock_phases"],
        })
    totals=report["totals"]
    head=[
        f"V161 FORWARD STOCK-AT-ARRIVAL PROXY — 24 ITEMS",
        f"First-issued item/hour cohorts: {report['issued_item_hours']}  |  "
        f"Five-minute item records: {report['recorded_five_minute_item_rows']}",
        f"INDEPENDENT: {pct(totals.get('independent_hit',0), totals.get('independent_miss',0))}; "
        f"pending={totals.get('independent_pending',0)}, "
        f"unknown={totals.get('independent_unknown',0)}, "
        f"abstain={sum(v['independent_abstain'] for v in items.values())}",
        f"PAIRED:      {pct(totals.get('paired_complete_hit',0), totals.get('paired_complete_miss',0))}; "
        f"pending={totals.get('paired_complete_pending',0)}, "
        f"unknown={totals.get('paired_complete_unknown',0)}, "
        f"abstain={sum(v['paired_complete_abstain'] for v in items.values())}",
        "Each item's percentage is conditional on SCOREABLE issued proposals, "
        "not a guarantee or an all-hours success rate.",
        "A dash means no matured scoreable predictions for that item; "
        "small samples and repeated phases are not independent evidence.",
        "",
        f"{'ITEM':<37} {'INDEPENDENT':>17} {'PAIRED':>17} {'HRS':>3} {'PENDING I/P':>11} {'PHASES':>6}",
        "-"*103,
    ]
    for row in rows:
        head.append(
            f"{row['item'][:37]:<37} {row['independent_rate']:>17} "
            f"{row['paired_rate']:>17} {row['hours']:>3} "
            f"{str(row['independent_pending'])+'/'+str(row['paired_pending']):>11} "
            f"{row['unique_phases']:>6}"
        )
    head+=["","SOURCE: as-issued V160 ledger matched to V88 successful poll brackets; "
           "NOT human flights, NOT historical reconstruction.",
           "Note: A successful repeated poll with unchanged zero is meaningful. "
           "stock_history stores changes only."]
    return "\n".join(head)


def main():
    try:
        report=json.load(sys.stdin)
        print(scorecard(report))
    except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        print("Unable to score: "+str(exc),file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
