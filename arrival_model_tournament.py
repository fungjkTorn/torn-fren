import argparse

from services.arrival_model_tournament import tournament_arrival_models


def pct(v):
    return "—" if v is None else f"{100*v:.1f}%"


def dur(v):
    if v is None:
        return "—"
    v = int(round(v))
    sign = "-" if v < 0 else ""
    v = abs(v)
    h, rem = divmod(v, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{sign}{h}h{m:02d}m"
    if m:
        return f"{sign}{m}m{s:02d}s"
    return f"{sign}{s}s"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("country")
    p.add_argument("item_name")
    args = p.parse_args()

    r = tournament_arrival_models(args.country, args.item_name)

    print(f"=== Prediction v2 ARRIVAL model tournament: {r['item_name']} / {r['country']} ===")
    print(f"Behavior class: {r['behavior_class']}")
    print(f"Model evidence tier: {r['model_evidence_tier'].upper()}")
    print(f"Current point-model selector: {r['current_point_model']}")
    print(f"Median stock lifetime: {dur(r['median_stock_lifetime_seconds'])}")
    print()

    print(
        f"{'model':28} {'policy':9} {'n':>4} "
        f"{'life':>8} {'r20':>8} {'r10':>8} "
        f"{'offset':>9} {'window':>9} {'reliability':>12}"
    )
    print("-" * 116)

    for x in r["results"]:
        print(
            f"{x['model'][:28]:28} "
            f"{x['policy']:9} "
            f"{x['n']:4d} "
            f"{pct(x['arrival_success_rate']):>8} "
            f"{pct(x['recent20_success_rate']):>8} "
            f"{pct(x['recent10_success_rate']):>8} "
            f"{dur(x['current_arrival_offset_seconds']):>9} "
            f"{dur(x['window_width_seconds']):>9} "
            f"{x['reliability']:>12}"
        )

    print()
    if r["best"]:
        b = r["best"]
        print("TRAVEL-FIRST WINNER")
        print(f"  model: {b['model']}")
        print(f"  arrival policy: {b['policy']}")
        print(f"  walk-forward arrival success: {pct(b['arrival_success_rate'])}")
        print(f"  recent 20: {pct(b['recent20_success_rate'])}")
        print(f"  recent 10: {pct(b['recent10_success_rate'])}")
        print(f"  current target offset: {dur(b['current_arrival_offset_seconds'])}")
        print(f"  reliability: {b['reliability']}")
    else:
        print("Not enough resolved history for an arrival-model comparison.")

    print()
    print("Important:")
    print("- Cycle-speed class and travel reliability are now separate concepts.")
    print("- A model can be statistically PROVEN but still travel-UNRELIABLE.")
    print("- This tournament can reveal whether Japan benefits from a recent-10/recent-20 regime policy.")
    print("- No live graph/Discord behavior is changed by this patch yet.")


if __name__ == "__main__":
    main()
