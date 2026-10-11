"""V83 read-only forward audit of V81/V82 Lion/Panda research variants.

Candidate-as-issued only. Outcome labels use 180s observed-stock bracketing
as a PROXY, not strict 10-second ground truth or real player travel.
Different target arrival timestamps are NOT guaranteed independent cycles.
No collector, website, or research-ledger writes.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from research.v34_prospective_ops_audit import arrival_truth
from research.v76_forward_research_report import strict_samples
from research.v81_pair_forward_comparison import SIDECAR, VARIANTS
from research.plushie_champions.common import TRAVEL_SECONDS
from services.frozen_candidate_worker_v31 import inspect_live_source
from research.v60_private_snapshot_probe import approved_collector_source

COLLECTOR = Path("/opt/torn-fren/data/stock_history.db")
MAX_ROWS = 50000
DAY = 86400
HORIZON = 28800
STEP = 300
GRACE = 10
QTY = 30


def readonly(db):
    p = Path(db).resolve(strict=True)
    if p.is_symlink() or not p.is_file():
        raise ValueError("not regular research input")
    con = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def valid(row):
    try:
        country, item = row["item_key"].split(":", 1)
        issued = row["issued_at"]
        planned = row["planned_at"]
        hb = row["stock_as_of"]
        dep = row["departure"]
        arr = row["arrival"]
        expiry = row["valid_until"]
        return (country in TRAVEL_SECONDS and bool(item)
            and row["variant"] in VARIANTS
            and row["status"] == "FORWARD_CANDIDATE_ONLY"
            and all(type(x) is int for x in (issued, planned, hb, dep, arr, expiry))
            and row["min_quantity"] == QTY
            and row["grace_seconds"] == GRACE
            and row["actual_player_departure"] == 0
            and planned % STEP == 0
            and 0 <= issued - hb <= 180
            and 0 <= issued - planned <= STEP
            and expiry == issued + STEP
            and issued <= dep <= issued + HORIZON
            and arr - dep == TRAVEL_SECONDS[country])
    except (TypeError, ValueError, KeyError, AttributeError):
        return False


def audit(ledger, stock, *, now=None, days=7, max_rows=MAX_ROWS):
    if not 1 <= days <= 14 or not 1 <= max_rows <= MAX_ROWS:
        raise ValueError("unsupported reporting window or row cap")
    asof = int(time.time() if now is None else now)
    since = asof - days * DAY
    if Path(ledger).resolve(strict=True) == Path(stock).resolve(strict=True):
        raise ValueError("ledger cannot be the stock collector")
    columns = ("item_key", "variant", "issued_at", "planned_at", "stock_as_of",
               "valid_until", "status", "departure", "arrival",
               "min_quantity", "grace_seconds", "actual_player_departure")
    sql = ("SELECT " + ",".join(columns) +
           " FROM pair_issued_decisions WHERE issued_at BETWEEN ? AND ?"
           " ORDER BY issued_at ASC, id ASC LIMIT ?")
    with closing(readonly(ledger)) as con:
        records = con.execute(sql, (since, asof, max_rows + 1)).fetchall()
    if len(records) > max_rows:
        raise ValueError("too many issued records; decrease --days")
    by_group = defaultdict(Counter)
    valid_arrivals = {}
    invalid = 0
    for row in records:
        key = (row["item_key"], row["variant"])
        stats = by_group[key]
        stats["raw_issued_rows"] += 1
        if not valid(row):
            if row["status"] == "FORWARD_CANDIDATE_ONLY":
                stats["invalid_proposals"] += 1
                invalid += 1
            else:
                stats["abstentions_or_no_candidate"] += 1
            continue
        stats["valid_issued_rows"] += 1
        # Collapse repeat replans to an arrival-target diagnostic; does NOT
        # establish independence of distinct restocks or player behavior.
        unique = (row["item_key"], row["variant"], row["arrival"])
        if unique not in valid_arrivals:
            valid_arrivals[unique] = (row["item_key"], row["variant"], row["arrival"])
        else:
            stats["duplicate_arrival_target"] += 1
    with closing(readonly(stock)) as observations:
        for (item, variant, arr) in valid_arrivals.values():
            country, name = item.split(":", 1)
            counts = by_group[(item, variant)]
            counts["unique_arrival_targets"] += 1
            if asof < arr + GRACE + 180:
                counts["pending"] += 1
                continue
            sample = strict_samples(observations, country, name, arr)
            counts["strict_" + sample] += 1
            proxy, _ = arrival_truth(observations, country, name, arr, asof)
            if proxy == "SUCCESS":
                counts["proxy_success"] += 1
            elif proxy == "MISS":
                counts["proxy_miss"] += 1
            else:
                counts["unscorable_" + proxy] += 1
    output = {}
    for (item, variant), counts in sorted(by_group.items()):
        done = counts["proxy_success"] + counts["proxy_miss"]
        output.setdefault(item, {})[variant] = {
            **dict(sorted(counts.items())),
            "proxy_scorable": done,
            "proxy_success_fraction": round(counts["proxy_success"] / done, 4)
                if done else None,
        }
    return {
        "status": "V83_FORWARD_COMPARISON_RESEARCH_REPORT",
        "research_only": True,
        "actual_player_departure_observed": False,
        "approved_for_live": False,
        "collector_written": False,
        "ledger_written": False,
        "accuracy_exact_at_10_seconds": False,
        "independent_cycle_accuracy_claim": False,
        "event_basis": "FIRST_AS_ISSUED_ITEM_VARIANT_ARRIVAL_TARGET",
        "caution": "Nearby arrival targets can belong to the same restock cycle; 180-second bracketing is only a proxy. Sparse polling cannot establish exact +10-second accuracy.",
        "asof": asof,
        "issued_window_days": days,
        "raw_issued_rows": len(records),
        "unique_arrival_targets": len(valid_arrivals),
        "invalid_candidate_rows": invalid,
        "per_item_variant": output,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    if not approved_collector_source(COLLECTOR):
        raise SystemExit("STOP: unapproved stock source")
    if not SIDECAR.is_file() or SIDECAR.is_symlink():
        print(json.dumps({"status": "V83_NO_PAIR_LEDGER"}))
        return
    result = audit(SIDECAR, COLLECTOR, days=args.days)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
