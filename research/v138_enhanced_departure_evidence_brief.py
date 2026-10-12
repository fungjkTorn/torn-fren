"""V138: enhanced one-pass departure brief including direct original V2 stock truth.

V135 already combines:
  * original V2 archived restock-window / target-cycle metrics (V134),
  * older V75 direct >=30 arrival proxy versus leave-now (V131),
  * new V128 direct >=30 arrival proxy plus timing/reconfirmation (V129/V132).

V138 keeps those definitions intact and adds V137, which evaluates the frozen
original V2 recommended arrival and reconstructed earliest displayed departure
against the SAME V88 >=30 poll-state proxy used for V75/V128.

No model is rebuilt and no forecast is backfilled. All inputs are existing
read-only collector/sidecar history. No services, website, timers, gameplay,
API calls, or databases are changed.
"""
from __future__ import annotations

import argparse
import json
import time

from research.v135_morning_departure_brief import (
    assemble as v135_assemble,
    short_summary as v135_short_summary,
)
from research.v137_original_v2_stock_at_arrival_audit import (
    audit as original_v2_direct_audit,
)


def assemble(*, now=None, old_v75_days=3, new_days=2, old_graph_days=30,
             base_brief=v135_assemble, direct_v2=original_v2_direct_audit):
    asof = int(time.time() if now is None else now)
    base = base_brief(
        now=asof,
        old_v75_days=old_v75_days,
        new_days=new_days,
        old_graph_days=old_graph_days,
    )
    direct = direct_v2(asof=asof, days=old_graph_days)
    if base.get("collector_and_sidecars_read_only") is not True:
        raise ValueError("base brief lost read-only contract")
    return {
        "status": "V138_ENHANCED_DEPARTURE_EVIDENCE_BRIEF",
        "asof_epoch": asof,
        "collector_and_sidecars_read_only": True,
        "base_v135": base,
        "original_graph_v2_direct_stock_at_arrival": {
            "status": direct["status"],
            "historical_window_days": old_graph_days,
            "overall": direct.get("overall"),
            "per_item": direct.get("per_item"),
            "selection_exclusions": direct.get("selection_exclusions"),
            "stock_proxy_reason_counts": direct.get("stock_proxy_reason_counts"),
            "method_notes": direct.get("method_notes"),
            "recent_examples": direct.get("recent_examples"),
        },
        "comparison_contract": {
            "threshold_stock": 30,
            "current_departure_horizon_hours": 8,
            "same_poll_state_proxy_for_original_v2_v75_v128": True,
            "original_v2_exact_latest_browser_bound_reconstructible": False,
            "reason": (
                "Old V2 audit rows did not persist target depletion/lifetime; "
                "V137 reconstructs the lower/earliest displayed departure edge."
            ),
        },
        "limitations": {
            **(base.get("limitations") or {}),
            "original_v2_direct_arrival_is_poll_state_proxy_not_gameplay": True,
            "original_v2_latest_safe_leave_not_exactly_reconstructed": True,
        },
    }


def _direct_compact(overall):
    if not overall:
        return None
    keys = (
        "first_item_UTC_hourly_starts",
        "valid_original_active_targets_under_8h_contract",
        "no_active_target_or_invalid_current_contract",
        "original_active_target_outside_current_8h_contract",
        "stored_recommended_arrival_scorable",
        "stored_recommended_arrival_stock_at_least_30",
        "ui_earliest_action_scorable",
        "ui_earliest_action_stock_at_least_30",
        "ui_earliest_action_stock_below_30",
        "leave_now_scorable",
        "leave_now_stock_at_least_30",
        "leave_now_stock_below_30",
        "matched_ui_vs_leave_now",
        "matched_only_ui_stocked",
        "matched_only_leave_now_stocked",
        "matched_ui_stocked_fraction",
        "matched_leave_now_stocked_fraction",
        "ui_minus_leave_now_only_known_pairs",
        "ui_wait_minutes",
    )
    return {k: overall.get(k) for k in keys}


def short_summary(report):
    base = report["base_v135"]
    direct = report["original_graph_v2_direct_stock_at_arrival"]
    lines = [
        v135_short_summary(base),
        "===== V138 ORIGINAL V2 DIRECT >=30 ARRIVAL BENCHMARK =====",
        "Status: " + str(direct["status"]),
        "Original V2 earliest displayed departure versus leave-now: " +
        json.dumps(_direct_compact(direct.get("overall")), sort_keys=True),
    ]

    by_item = direct.get("per_item") or {}
    active = []
    for key, row in sorted(by_item.items()):
        if not row.get("first_item_UTC_hourly_starts"):
            continue
        active.append(key + " " + json.dumps({
            "starts": row.get("first_item_UTC_hourly_starts"),
            "valid_under_8h": row.get(
                "valid_original_active_targets_under_8h_contract"),
            "matched": row.get("matched_ui_vs_leave_now"),
            "ui_stocked": row.get("ui_earliest_action_stock_at_least_30"),
            "now_stocked": row.get("leave_now_stock_at_least_30"),
            "ui_only_minus_now_only": row.get(
                "ui_minus_leave_now_only_known_pairs"),
            "wait_minutes": row.get("ui_wait_minutes"),
        }, sort_keys=True))
    if active:
        lines.append("===== ORIGINAL V2 DIRECT ARRIVAL BY ITEM =====")
        lines.extend(active)

    lines.extend([
        "===== V138 CAUTION =====",
        json.dumps(report["limitations"], sort_keys=True),
        "No real flight/purchase certification. No production, timer, or DB writes.",
    ])
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old-days", type=int, default=3)
    p.add_argument("--graph-days", type=int, default=30)
    p.add_argument("--v128-days", type=int, default=2)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    result = assemble(
        old_v75_days=a.old_days,
        new_days=a.v128_days,
        old_graph_days=a.graph_days,
    )
    print(json.dumps(result, sort_keys=True)
          if a.json else short_summary(result))


if __name__ == "__main__":
    main()
