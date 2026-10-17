"""V137: read-only original Prediction V2 stock-at-arrival benchmark.

Purpose
-------
V134 audits the original graph's persisted restock-window and target-cycle
labels. Those labels do NOT directly answer the current product question:
"if I follow the departure guidance, do I arrive with at least 30 stock?"

V137 therefore reuses the frozen, AS-ISSUED original Prediction V2 audit
snapshots and scores their arrivals with the same V88 successful-poll stock
proxy used by the V75/V128 research reports.

For each item and UTC hour we freeze the FIRST recorded V2 run before looking
at later stock. We evaluate three timestamps:
  * stored recommended arrival (the model's persisted arrival target);
  * reconstructed earliest UI action: the first departure time at which the
    browser's lower arrival bound would open, or issue-time if already open;
  * matched leave-now baseline from that same issue timestamp.

The browser lower bound is reproducible from frozen fields:
    earliest_arrival = max(recommended_arrival, window_end)
with estimate_timestamp as a fallback, then subtract the pinned country flight
duration. The exact browser *latest* departure bound is not reconstructible
from the old audit row because target_depletion_timestamp / lifetime were not
persisted. Therefore V137 does NOT claim to reproduce every client-side target
roll; it benchmarks the earliest actionable side of the old displayed window.

Current research policy limits departures to 8 hours after issue. Original V2
could forecast farther, so such rows are reported and excluded from the matched
current-contract comparison rather than silently reinterpreted.

Evidence remains a collector poll-state proxy, not verified gameplay stock or
purchase success. All SQLite access is read-only. No model, collector, website,
service, API, or gameplay writes are performed.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v60_private_snapshot_probe import approved_collector_source
from research.v88_poll_state_forward_report import observation
from research.v128_full24_earliest_shadow import COLLECTOR, exact_roster

MAX_DAYS = 90
MAX_ROWS = 60000
MAX_WAIT = 8 * 3600
SHOW_EVENTS = 12


def ro(path):
    p = Path(path).resolve(strict=True)
    if not p.is_file():
        raise ValueError("not a regular collector file")
    db = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=15)
    db.execute("PRAGMA query_only=ON")
    db.row_factory = sqlite3.Row
    return db


def epoch_utc(value):
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _record(counter, prefix, status, hit):
    counter[prefix + "_scored"] += int(hit is not None)
    counter[prefix + "_hit"] += int(hit is True)
    counter[prefix + "_miss"] += int(hit is False)
    counter[prefix + "_unknown"] += int(hit is None)
    counter[prefix + "_pending"] += int(status == "PENDING")


def _summary(c):
    starts = c["starts"]
    paired = c["ui_now_paired"]
    waits = c.get("_waits", [])
    return {
        "first_item_UTC_hourly_starts": starts,
        "valid_original_active_targets_under_8h_contract": c["valid"],
        "no_active_target_or_invalid_current_contract": c["invalid"],
        "original_active_target_outside_current_8h_contract": c["over_8h"],
        "stored_recommended_arrival_scorable": c["stored_scored"],
        "stored_recommended_arrival_stock_at_least_30": c["stored_hit"],
        "stored_recommended_arrival_stock_below_30": c["stored_miss"],
        "stored_recommended_arrival_unknown_or_pending": c["stored_unknown"],
        "ui_earliest_action_scorable": c["ui_scored"],
        "ui_earliest_action_stock_at_least_30": c["ui_hit"],
        "ui_earliest_action_stock_below_30": c["ui_miss"],
        "ui_earliest_action_unknown_or_pending": c["ui_unknown"],
        "leave_now_scorable": c["now_scored"],
        "leave_now_stock_at_least_30": c["now_hit"],
        "leave_now_stock_below_30": c["now_miss"],
        "leave_now_unknown_or_pending": c["now_unknown"],
        "matched_ui_vs_leave_now": paired,
        "matched_both_stocked": c["both_hit"],
        "matched_only_ui_stocked": c["ui_only"],
        "matched_only_leave_now_stocked": c["now_only"],
        "matched_both_below_30": c["both_miss"],
        "matched_ui_stocked_fraction": (
            round((c["both_hit"] + c["ui_only"]) / paired, 4)
            if paired else None
        ),
        "matched_leave_now_stocked_fraction": (
            round((c["both_hit"] + c["now_only"]) / paired, 4)
            if paired else None
        ),
        "ui_minus_leave_now_only_known_pairs": c["ui_only"] - c["now_only"],
        "ui_wait_minutes": {
            "mean": round(statistics.mean(waits), 2) if waits else None,
            "median": round(statistics.median(waits), 2) if waits else None,
            "max": round(max(waits), 2) if waits else None,
        },
        "all_starts_observed_ui_stocked_lower_bound": (
            round(c["ui_hit"] / starts, 4) if starts else None
        ),
    }


def audit(*, collector=COLLECTOR, asof=None, days=30, limit=MAX_ROWS,
          scorer=observation):
    if not 1 <= days <= MAX_DAYS or not 1 <= limit <= MAX_ROWS:
        raise ValueError("invalid V137 bound")
    asof = int(time.time() if asof is None else asof)
    if Path(collector) == Path(COLLECTOR) and not approved_collector_source(collector):
        raise ValueError("unapproved collector source")

    allowed = set(exact_roster())
    start = asof - days * 86400

    with closing(ro(collector)) as db:
        tables = {
            str(r[0])
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        needed = {"forecast_audit_runs", "forecast_audit_points"}
        if not needed.issubset(tables):
            return {
                "status": "ORIGINAL_V2_FORECAST_AUDIT_TABLES_NOT_PRESENT",
                "missing_tables": sorted(needed - tables),
                "read_only": True,
                "no_accuracy_claim_without_stored_forecasts": True,
            }

        raw_count = int(db.execute(
            """SELECT COUNT(*)
               FROM forecast_audit_runs
               WHERE created_at BETWEEN ? AND ?""",
            (start, asof),
        ).fetchone()[0])
        if raw_count > limit:
            raise ValueError("too many archived original V2 runs; narrow days")

        rows = db.execute(
            """SELECT
                   r.id AS run_id,
                   r.country,
                   r.item_name,
                   r.created_at,
                   r.source,
                   r.status AS run_status,
                   r.active_prediction_number,
                   p.prediction_number,
                   p.estimate_timestamp,
                   p.window_end_timestamp,
                   p.recommended_arrival_timestamp,
                   p.recommended_leave_by_timestamp,
                   p.projected,
                   p.travel_reliability,
                   p.model_name,
                   p.projection_depth
               FROM forecast_audit_runs AS r
               LEFT JOIN forecast_audit_points AS p
                 ON p.run_id = r.id
                AND p.prediction_number = r.active_prediction_number
               WHERE r.created_at BETWEEN ? AND ?
               ORDER BY r.created_at, r.id""",
            (start, asof),
        ).fetchall()
        if len(rows) != raw_count:
            raise ValueError("nonrepeatable original V2 run selection")

        # Freeze the first original run per item per UTC hour before reading
        # any future stock outcomes.
        first = {}
        excluded = Counter()
        for row in rows:
            key = f"{str(row['country']).lower()}:{row['item_name']}"
            if key not in allowed:
                excluded["OUTSIDE_CURRENT_EXACT_24_ROSTER"] += 1
                continue
            bucket = (key, int(row["created_at"]) // 3600)
            first.setdefault(bucket, row)

        all_counts = Counter()
        per_item = defaultdict(Counter)
        statuses = Counter()
        evidence = Counter()
        examples = []

        for (_bucket, row) in first.items():
            key = f"{str(row['country']).lower()}:{row['item_name']}"
            country, item = key.split(":", 1)
            issue = int(row["created_at"])
            statuses[str(row["run_status"])] += 1

            counters = (all_counts, per_item[key])
            for c in counters:
                c["starts"] += 1
                c.setdefault("_waits", [])

            active = row["active_prediction_number"]
            if active is None or row["prediction_number"] is None:
                for c in counters:
                    c["invalid"] += 1
                excluded["NO_AS_ISSUED_ACTIVE_TARGET"] += 1
                continue

            estimate = row["estimate_timestamp"]
            recommended = row["recommended_arrival_timestamp"]
            window_end = row["window_end_timestamp"]
            candidates = [
                int(v) for v in (recommended, estimate)
                if v is not None
            ]
            late_candidates = [
                int(v) for v in (window_end, estimate)
                if v is not None
            ]
            if not candidates or not late_candidates:
                for c in counters:
                    c["invalid"] += 1
                excluded["ACTIVE_TARGET_MISSING_ARRIVAL_FIELDS"] += 1
                continue

            # Exact lower edge used by the original browser's
            # departureWindowForPrediction().
            earliest_arrival_bound = max(
                int(recommended if recommended is not None else estimate),
                int(window_end if window_end is not None else estimate),
            )
            flight = int(TRAVEL_SECONDS[country])
            earliest_leave = earliest_arrival_bound - flight
            departure = max(issue, earliest_leave)
            wait = departure - issue

            if wait > MAX_WAIT:
                for c in counters:
                    c["invalid"] += 1
                    c["over_8h"] += 1
                excluded["ORIGINAL_ACTIVE_TARGET_OUTSIDE_CURRENT_8H_CONTRACT"] += 1
                continue

            action_arrival = departure + flight
            now_arrival = issue + flight

            for c in counters:
                c["valid"] += 1
                c["_waits"].append(wait / 60.0)

            # Stored model target is useful as a diagnostic distinct from the
            # browser's lower-bound action policy.
            stored_status = stored_hit = None
            stored_meta = {}
            if recommended is not None:
                stored_status, stored_hit, stored_meta = scorer(
                    db, country, item, int(recommended), asof
                )
                for c in counters:
                    _record(c, "stored", stored_status, stored_hit)
                evidence["STORED_" + stored_status] += 1
            else:
                for c in counters:
                    c["stored_unknown"] += 1
                evidence["STORED_NO_RECOMMENDED_ARRIVAL"] += 1

            ui_status, ui_hit, ui_meta = scorer(
                db, country, item, int(action_arrival), asof
            )
            now_status, now_hit, now_meta = scorer(
                db, country, item, int(now_arrival), asof
            )
            for c in counters:
                _record(c, "ui", ui_status, ui_hit)
                _record(c, "now", now_status, now_hit)
                if ui_hit is not None and now_hit is not None:
                    c["ui_now_paired"] += 1
                    if ui_hit and now_hit:
                        c["both_hit"] += 1
                    elif ui_hit:
                        c["ui_only"] += 1
                    elif now_hit:
                        c["now_only"] += 1
                    else:
                        c["both_miss"] += 1

            evidence["UI_" + ui_status] += 1
            evidence["LEAVE_NOW_" + now_status] += 1

            examples.append({
                "item_key": key,
                "issued_utc": epoch_utc(issue),
                "source": row["source"],
                "run_status": row["run_status"],
                "prediction_number": int(active),
                "projection_depth": row["projection_depth"],
                "model_name": row["model_name"],
                "travel_reliability": row["travel_reliability"],
                "stored_recommended_arrival_utc": epoch_utc(recommended),
                "ui_earliest_arrival_bound_utc": epoch_utc(earliest_arrival_bound),
                "ui_action_departure_utc": epoch_utc(departure),
                "ui_action_arrival_utc": epoch_utc(action_arrival),
                "ui_wait_minutes": round(wait / 60.0, 2),
                "ui_arrival_stock_proxy": ui_status,
                "ui_bracketing_quantities": (
                    [ui_meta["pre_quantity"], ui_meta["post_quantity"]]
                    if "pre_quantity" in ui_meta and "post_quantity" in ui_meta
                    else None
                ),
                "leave_now_arrival_utc": epoch_utc(now_arrival),
                "leave_now_stock_proxy": now_status,
                "stored_target_stock_proxy": stored_status,
                "country_update_freshness_verified": False,
            })

    examples.sort(key=lambda x: x["issued_utc"], reverse=True)
    return {
        "status": "V137_ORIGINAL_V2_STOCK_AT_ARRIVAL_BENCHMARK",
        "read_only": True,
        "analysis_UTC": epoch_utc(asof),
        "lookback_days": days,
        "raw_original_runs_in_scope": raw_count,
        "first_issued_item_UTC_hourly_starts": len(first),
        "current_roster_count": len(allowed),
        "current_contract_max_wait_hours": MAX_WAIT // 3600,
        "overall": _summary(all_counts),
        "per_item": {
            key: _summary(per_item[key])
            for key in sorted(allowed)
        },
        "original_run_status_counts": dict(sorted(statuses.items())),
        "selection_exclusions": dict(sorted(excluded.items())),
        "stock_proxy_reason_counts": dict(sorted(evidence.items())),
        "recent_examples": examples[:SHOW_EVENTS],
        "method_notes": {
            "stored_target": (
                "Persisted recommended_arrival_timestamp from the original V2 model."
            ),
            "ui_earliest_action": (
                "Reconstructs the original browser lower departure bound using "
                "max(recommended_arrival, window_end) minus country flight time; "
                "if that window was already open at issue, departure is issue-time."
            ),
            "latest_browser_departure_not_reconstructed": (
                "Old audit rows did not persist target_depletion_timestamp / "
                "expected_stock_lifetime_seconds, so client-side latest-safe-leave "
                "rolls cannot be reproduced exactly."
            ),
        },
        "same_v88_poll_state_proxy_as_v75_v128": True,
        "stock_at_least_30_threshold": 30,
        "actual_gameplay_flights_or_purchases_verified": False,
        "country_provider_freshness_verified": False,
        "correlated_hourly_snapshots_are_not_independent_restock_cycles": True,
        "no_future_stock_used_to_select_issue_or_departure": True,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = audit(days=args.days)
    if args.json:
        print(json.dumps(result, sort_keys=True))
        return
    print("===== ORIGINAL V2 >=30 STOCK-AT-ARRIVAL BENCHMARK =====")
    print("Status:", result["status"])
    if "overall" in result:
        print("Overall:", json.dumps(result["overall"], sort_keys=True))
        print("Exclusions:", json.dumps(result["selection_exclusions"], sort_keys=True))
        print("Evidence:", json.dumps(result["stock_proxy_reason_counts"], sort_keys=True))
        for key, value in result["per_item"].items():
            if value["first_item_UTC_hourly_starts"]:
                print(key, json.dumps(value, sort_keys=True))
        print("Recent:", json.dumps(result["recent_examples"], sort_keys=True))
    print("CAUTION: collector >=30 proxy, not verified gameplay stock/purchase success.")
    print("READ ONLY: no production or collector writes.")


if __name__ == "__main__":
    main()
