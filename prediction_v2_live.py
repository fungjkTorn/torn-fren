import argparse
import json
from datetime import datetime

from services.prediction_v2_live import build_live_prediction_v2


def fmt_ts(ts):
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%m/%d %I:%M:%S %p")


def pct(v):
    return "—" if v is None else f"{v*100:.1f}%"


def show_prediction(label, p):
    print(label)
    if not p:
        print("  —")
        return
    print(f"  restock:      {fmt_ts(p.get('estimate_timestamp'))}")
    print(f"  window:       {fmt_ts(p.get('window_start_timestamp'))} .. {fmt_ts(p.get('window_end_timestamp'))}")
    print(f"  arrival:      {fmt_ts(p.get('recommended_arrival_timestamp'))}")
    print(f"  leave by:     {fmt_ts(p.get('recommended_leave_by_timestamp'))}")
    print(f"  reliability:  {p.get('travel_reliability')}")
    print(f"  usable:       {p.get('usable_for_departure')}")
    print(f"  projected:    {p.get('projected')}")
    print(f"  model:        {p.get('model_name')}")
    print(f"  method:       {p.get('method')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("country")
    ap.add_argument("item_name")
    ap.add_argument("--force-profile", action="store_true")
    args = ap.parse_args()

    r = build_live_prediction_v2(
        args.country, args.item_name, force_profile=args.force_profile
    )
    print(f"=== LIVE Prediction v2: {args.item_name} / {args.country.upper()} ===")
    print(f"Status: {r.get('status')}")
    print(f"Current stock: {r.get('current_stock')}")
    print(f"Cycle class: {r.get('behavior_class')}")
    print(f"Model evidence: {r.get('model_evidence_tier')}")
    print(f"Travel reliability: {r.get('travel_reliability')}")
    print(f"Historical arrival success: {pct(r.get('arrival_success_rate'))}")
    print(f"Recent 20: {pct(r.get('recent20_arrival_success_rate'))}")
    print(f"Recent 10: {pct(r.get('recent10_arrival_success_rate'))}")
    if r.get("current_stock") and r.get("current_stock_estimated_reachable") is not None:
        print(f"Current stock reachable if leaving now: {r.get('current_stock_estimated_reachable')}")
        print(f"ETA if leaving now: {fmt_ts(r.get('current_stock_eta_if_leave_now_timestamp'))}")
        print(f"Estimated current depletion: {fmt_ts(r.get('estimated_current_depletion_timestamp'))}")
    print()
    show_prediction("PREDICTION #1", r.get("prediction_1"))
    print()
    show_prediction("PREDICTION #2", r.get("prediction_2"))
    print()
    dp = r.get("display_prediction")
    print(f"ACTIVE DISPLAY TARGET: #{dp.get('prediction_number') if dp else 'NONE'}")
    print(f"Note: {r.get('note')}")


if __name__ == "__main__":
    main()
