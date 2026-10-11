"""V86 read-only as-issued Japan Xanax V84/V85 research evidence report.

Outcomes from 180s stock observations are PROXIES, not certified +10s stock
truth, independent restocks, or executed player journeys. No writes.
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
from research.v84_japan_forward_canary import LEDGER, COLLECTOR, MAX_INFERENCE_AGE
from research.v60_private_snapshot_probe import approved_collector_source

DAY = 86400
CAP = 20000
TRAVEL = 8940
GRACE = 10
HORIZON = 28800
STEP = 300


def readonly(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("invalid or symlinked report database")
    conn = sqlite3.connect(p.resolve(strict=True).as_uri() + "?mode=ro",
                           uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def valid(row):
    return (row["status"] == "FORWARD_CANDIDATE_ONLY"
        and all(type(row[k]) is int for k in (
            "slot", "queried_at", "issued_at", "source_heartbeat",
            "departure", "arrival"))
        and row["slot"] == row["queried_at"] // STEP * STEP
        and 0 <= row["issued_at"] - row["queried_at"] <= MAX_INFERENCE_AGE
        and 0 <= row["issued_at"] - row["source_heartbeat"] <= 180
        and row["queried_at"] <= row["issued_at"]
        and row["issued_at"] <= row["departure"]
        and row["departure"] <= row["queried_at"] + HORIZON
        and row["arrival"] - row["departure"] == TRAVEL
        and row["quantity_threshold"] == 30
        and row["grace_seconds"] == GRACE
        and row["actual_player_departure"] == 0
        and row["source_model"] == "v8_regime_candidate_checkpoint_parity_pending"
        and row["experiment"] == "v84_japan_private_canary")


def report(ledger, stock, *, now=None, days=7, limit=CAP):
    if not 1 <= days <= 14 or not 1 <= limit <= CAP:
        raise ValueError("invalid Japan report window")
    end = int(time.time() if now is None else now)
    if Path(ledger).resolve(strict=True) == Path(stock).resolve(strict=True):
        raise ValueError("ledger and stock must be distinct")
    with closing(readonly(ledger)) as con:
        rows = con.execute(
            """SELECT slot,queried_at,issued_at,source_heartbeat,status,
               model_config,departure,arrival,quantity_threshold,grace_seconds,
               actual_player_departure,source_model,experiment
               FROM japan_forward_decisions
               WHERE issued_at BETWEEN ? AND ?
               ORDER BY slot LIMIT ?""",
            (end - days * DAY, end, limit + 1),
        ).fetchall()
    if len(rows) > limit:
        raise ValueError("too many Japan records, narrow --days")
    tally = Counter()
    by_model = defaultdict(Counter)
    targets = {}
    for row in rows:
        status = str(row["status"])
        model = str(row["model_config"] or "UNSPECIFIED")
        tally["issued_rows"] += 1
        by_model[model]["issued_rows"] += 1
        if status != "FORWARD_CANDIDATE_ONLY":
            tally["abstentions"] += 1
            tally["abstention_" + status] += 1
            by_model[model]["abstentions"] += 1
            continue
        if not valid(row):
            tally["invalid_candidates"] += 1
            by_model[model]["invalid_candidates"] += 1
            continue
        tally["valid_candidates"] += 1
        by_model[model]["valid_candidates"] += 1
        arr = row["arrival"]
        if arr in targets:
            tally["duplicate_arrival_targets"] += 1
            by_model[model]["duplicate_arrival_targets"] += 1
        else:
            targets[arr] = model
    with closing(readonly(stock)) as con:
        for arr, model in targets.items():
            by_model[model]["unique_arrivals"] += 1
            tally["unique_arrivals"] += 1
            if end < arr + GRACE + 180:
                tally["pending"] += 1
                by_model[model]["pending"] += 1
                continue
            sample = strict_samples(con, "jap", "Xanax", arr)
            by_model[model]["strict_" + sample] += 1
            tally["strict_" + sample] += 1
            proxy, _ = arrival_truth(con, "jap", "Xanax", arr, end)
            code = ("proxy_success" if proxy == "SUCCESS" else
                    "proxy_miss" if proxy == "MISS" else "unscorable_" + proxy)
            tally[code] += 1
            by_model[model][code] += 1
    def totals(v):
        denom = v["proxy_success"] + v["proxy_miss"]
        return {**dict(sorted(v.items())),
                "proxy_scorable": denom,
                "proxy_success_fraction": round(v["proxy_success"] / denom, 4)
                   if denom else None}
    return {
        "status": "V86_JAPAN_FORWARD_RESEARCH_REPORT",
        "research_only": True,
        "approved_for_website": False,
        "actual_player_departure_observed": False,
        "independent_restock_certified": False,
        "exact_10_second_accuracy_certified": False,
        "read_only": True,
        "collector_written": False,
        "ledger_written": False,
        "caution": "Repeated arrivals can be correlated even after identical timestamps are deduplicated. Proxy uses up to 180-second brackets; a direct sample in +10s is not proof of exact stock state throughout the interval.",
        "asof": end, "days": days,
        "totals": totals(tally),
        "by_model_config": {k: totals(v) for k, v in sorted(by_model.items())},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=7)
    a = p.parse_args()
    if not approved_collector_source(COLLECTOR):
        raise SystemExit("STOP: invalid collector identity")
    if not LEDGER.is_file() or LEDGER.is_symlink():
        print(json.dumps({"status": "V86_JAPAN_LEDGER_ABSENT"}))
        return
    print(json.dumps(report(LEDGER, COLLECTOR, days=a.days), sort_keys=True))


if __name__ == "__main__":
    main()
