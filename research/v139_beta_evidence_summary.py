"""Read-only parser for V139 operator output and conservative beta evidence gates.

Accepts the TEXT already produced by the read-only V139 script. Does not
connect to SQLite, invoke models, or read any in-game credentials. Metrics are
historical poll-state proxies on different cohorts, not certified gameplay
success or an apples-to-apples ranking of V2/V75/V128.

Usage:
  python -m research.v139_beta_evidence_summary /path/to/v139-audit.txt
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MAX_TEXT_BYTES = 2_000_000
MIN_INDEPENDENT_CYCLES_FOR_PROMOTION = 30
LABELS = {
    "graph": "Original graph restock/cycle accuracy: ",
    "v75": "V75 versus leave now, first-item-UTC-hour: ",
    "v128": "V128 observed arrival stock and matched leave-now: ",
    "v128_timing": "V128 latest time-to-leave coverage/forecast shifts: ",
    "v2_direct": "Original V2 earliest displayed departure versus leave-now: ",
}
ITEM = re.compile(r"^([a-z]{3}:.+?) (\{.*\})$")
HEADERS = {
    "===== ITEM-BY-ITEM CHECKPOINT =====": "v128_per_item",
    "===== ORIGINAL V2 DIRECT ARRIVAL BY ITEM =====": "v2_per_item",
}


def _proportion(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def _paired(name, *, total, both, model_only, now_only, neither):
    if min(total, both, model_only, now_only, neither) < 0:
        raise ValueError(f"negative matched outcomes: {name}")
    if both + model_only + now_only + neither != total:
        raise ValueError(f"inconsistent matched pair totals: {name}")
    return {
        "cohort": name,
        "matched": total,
        "model_successes": both + model_only,
        "leave_now_successes": both + now_only,
        "model_success_fraction": _proportion(both + model_only, total),
        "leave_now_success_fraction": _proportion(both + now_only, total),
        "matched_difference_fraction": _proportion(model_only - now_only, total),
        "model_only_hit": model_only,
        "leave_now_only_hit": now_only,
        "net_win_count": model_only - now_only,
        "different_cohorts_not_directly_comparable": True,
        "actual_gameplay_success_unverified": True,
    }


def summarize(text):
    if type(text) is not str or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("V139 output missing or too large")
    sections = {}
    per_item = {"v128_per_item": {}, "v2_per_item": {}}
    active = None
    finish = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in HEADERS:
            active = HEADERS[stripped]
            continue
        if stripped.startswith("====="):
            active = None
            if stripped == "===== AUDIT DONE, NO MODEL OR DATABASE CHANGES =====":
                finish = True
            continue
        if active:
            m = ITEM.match(stripped)
            if m:
                name, payload = m.groups()
                if name in per_item[active]:
                    raise ValueError(f"duplicate {active} {name}")
                per_item[active][name] = json.loads(payload)
                continue
        for key, prefix in LABELS.items():
            if stripped.startswith(prefix):
                if key in sections:
                    raise ValueError(f"duplicate audit section {key}")
                sections[key] = json.loads(stripped[len(prefix):])
                break
    if not finish:
        raise ValueError("incomplete V139 audit: no successful completion marker")
    if set(sections) != set(LABELS) or (
        len(per_item["v128_per_item"]) != 24
        or len(per_item["v2_per_item"]) < 20
    ):
        raise ValueError("V139 audit incomplete or missing item breakdown")
    a, b, c = sections["v75"], sections["v128"], sections["v2_direct"]
    assert isinstance(a, dict) and isinstance(b, dict) and isinstance(c, dict)
    v75 = _paired("V75_first_item_UTC_hour",
                  total=a["matched_flight_outcomes"],
                  both=a["matched_both_stocked"],
                  model_only=a["matched_only_old_model_stocked"],
                  now_only=a["matched_only_leave_now_stocked"],
                  neither=a["matched_both_below_30"])
    bp = b["matched_pair"]
    v128 = _paired("V128_first_item_UTC_hour",
                   total=bp["both_scorable"], both=bp["both_hit"],
                   model_only=bp["model_only_hit"],
                   now_only=bp["now_only_hit"], neither=bp["both_miss"])
    # V137's aggregate only exposes differences and fractions; do not invent
    # its both-hit/both-miss counts to make a synthetic matched contingency.
    v2 = {
        "cohort": "V2_recorded_first_item_UTC_hour",
        "matched": c["matched_ui_vs_leave_now"],
        "model_success_fraction": c["matched_ui_stocked_fraction"],
        "leave_now_success_fraction": c["matched_leave_now_stocked_fraction"],
        "model_only_hit": c["matched_only_ui_stocked"],
        "leave_now_only_hit": c["matched_only_leave_now_stocked"],
        "net_win_count": c["ui_minus_leave_now_only_known_pairs"],
        "matched_difference_fraction": _proportion(
            c["ui_minus_leave_now_only_known_pairs"],
            c["matched_ui_vs_leave_now"]),
        "different_cohorts_not_directly_comparable": True,
        "actual_gameplay_success_unverified": True,
    }
    if v2["net_win_count"] != v2["model_only_hit"]-v2["leave_now_only_hit"]:
        raise ValueError("inconsistent original V2 matched difference")

    if (a["valid_departure_proposals"] +
            a["no_valid_departure_or_abstention"] !=
            a["first_item_UTC_hourly_starts"]
        or b["proposed_departure_hours"] + b["abstained_hours"] !=
            b["first_issue_UTC_item_hours"]
        or b["model_proxy_success"] + b["model_proxy_miss"] +
            b["model_proxy_unknown"] != b["proposed_departure_hours"]):
        raise ValueError("coverage/score totals not reconciled")
    rows = []
    for key, evidence in sorted(per_item["v128_per_item"].items()):
        successes = evidence["v128_model_stocked"]
        failures = evidence["v128_model_below30"]
        known = evidence["v128_mature_stock_proxies"]
        if known != successes + failures:
            raise ValueError(f"V128 per-item outcomes don't balance: {key}")
        v75_pair = evidence["v75_matched_flights"]
        if known == 0:
            concern = "NO_V128_MATURED_ARRIVALS"
        elif known >= 10 and successes / known < .6:
            concern = "V128_HIGH_OBSERVED_MISS_FRACTION"
        elif known < 10:
            concern = "V128_LOW_SAMPLE_SIZE"
        else:
            concern = "V128_PROVISIONAL_MORE_INDEPENDENT_EVIDENCE"
        # The 30-cycle gate is intentionally NOT based on 30 adjacent
        # five-minute ticks or correlated item-hour snapshots.
        rows.append({
            "item_key": key,
            "v128_known_arrivals": known,
            "v128_proxy_hits": successes,
            "v128_proxy_misses": failures,
            "v128_success_given_scorable": _proportion(successes, known),
            "v128_future_watches": evidence["v128_future_watches"],
            "v128_reconfirmed_watches": evidence["v128_watch_reconfirmed"],
            "v75_matched_pairs": v75_pair,
            "v75_model_only_minus_leave_now_only": (
                evidence["v75_model_only_vs_leave_now_only_net"]),
            "v2_restock_window_hit_fraction": (
                evidence["old_v2_restock_window_hit_fraction"]),
            "v2_valid_target_cycles": (
                evidence["old_v2_valid_restock_cycles"]),
            "v2_ui_matched_outcomes": (
                per_item["v2_per_item"].get(key, {}).get("matched")),
            "v2_ui_model_only_minus_leave_now_only": (
                per_item["v2_per_item"].get(key, {}).get(
                    "ui_only_minus_now_only")),
            "first_diagnostic": concern,
            "ready_for_promotion": False,
            "why_not_ready": (
                f"Only {known} scored item-hour arrival proxies, no "
                f"demonstration of {MIN_INDEPENDENT_CYCLES_FOR_PROMOTION} "
                "independent future restock cycles, no country feed or "
                "real gameplay landing certification"),
        })
    if (sum(x["v128_known_arrivals"] for x in rows) !=
        b["model_proxy_success"] + b["model_proxy_miss"]):
        raise ValueError("V128 per-item successes do not reconcile to global")
    return {
        "status": "HISTORICAL_PROXY_EVIDENCE_NOT_BETA_CERTIFICATION",
        "complete_24_roster": True,
        "original_v2": {
            "matched": v2,
            "restock_mean_absolute_error_minutes": (
                sections["graph"]["mean_absolute_restock_error_minutes"]),
            "restock_window_hit_fraction": (
                sections["graph"]["observed_restock_window_hit_rate"]),
            "target_stocked_interval_hit_fraction": (
                sections["graph"]["arrival_inside_target_cycle_rate"]),
        },
        "v75": {
            "matched": v75,
            "first_item_UTC_hours": a["first_item_UTC_hourly_starts"],
            "proposals": a["valid_departure_proposals"],
            "proposal_fraction": _proportion(
                a["valid_departure_proposals"],
                a["first_item_UTC_hourly_starts"]),
            "scored_model_success": a["old_model_arrival_stock_at_least_30"],
            "scored_model_miss": a["old_model_arrival_stock_below_30"],
            "model_unknown_or_pending": (
                a["old_model_arrival_unknown_or_pending"]),
        },
        "v128": {
            "matched": v128,
            "first_item_UTC_hours": b["first_issue_UTC_item_hours"],
            "proposals": b["proposed_departure_hours"],
            "abstentions": b["abstained_hours"],
            "proposal_fraction": _proportion(
                b["proposed_departure_hours"],
                b["first_issue_UTC_item_hours"]),
            "scored_model_success": b["model_proxy_success"],
            "scored_model_miss": b["model_proxy_miss"],
            "model_unknown_or_pending": b["model_proxy_unknown"],
            "lower_bound_hit_fraction_per_start": (
                b["lower_bound_hits_per_start"]),
            "five_minute_issued_ticks": (
                sections["v128_timing"]["issued_five_minute_snapshots"]),
            "unchanged_stock_two_proposal_pairs": (
                sections["v128_timing"][
                    "unchanged_collector_state_pairs_with_two_departures"]),
            "unchanged_stock_departure_shift_gt_15min": (
                sections["v128_timing"][
                    "same_observed_state_absolute_departure_shift_gt_15min"]),
        },
        "items": rows,
        "unverified": {
            "same_three_way_issue_cohort": True,
            "independent_cycles": True,
            "per_country_provider_freshness": True,
            "actual_stock_purchased_by_player": True,
        },
        "action": (
            "Preserve existing 21 V75 incumbent rows + 3 unvalidated previews; "
            "do not promote V128. Fix V2 restock/lifetime error and perform "
            "controlled matched cohort comparison before deployment."),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report",type=Path)
    args=ap.parse_args(argv)
    if args.report.stat().st_size > MAX_TEXT_BYTES:
        ap.error("report exceeds maximum safe size")
    result=summarize(args.report.read_text(encoding="utf8-sig"))
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
