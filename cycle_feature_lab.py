import argparse

from services.cycle_feature_lab import analyze_cycle_features


def fmt_duration(seconds):
    if seconds is None:
        return "—"
    sign = "-" if seconds < 0 else ""
    seconds = abs(int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{sign}{h}h {m}m {s}s"
    if m:
        return f"{sign}{m}m {s}s"
    return f"{sign}{s}s"


def main():
    parser = argparse.ArgumentParser(description="Analyze cycle features and wait-time structure for a Torn foreign item.")
    parser.add_argument("country")
    parser.add_argument("item", nargs="+")
    args = parser.parse_args()
    item = " ".join(args.item)

    result = analyze_cycle_features(args.country.lower(), item)
    print(f"=== {result['item_name']} / {result['country'].upper()} ===")
    print(f"Qualified feature rows: {result['samples']}")
    print(f"Median zero->restock: {fmt_duration(result['median_wait_seconds'])}")
    print(f"Median prior stock lifetime: {fmt_duration(result['median_lifetime_seconds'])}")
    print(f"Provider bounces suppressed: {result['provider_bounces_suppressed']}")

    print("\n=== Strongest feature relationships to NEXT wait ===")
    if not result["correlations"]:
        print("Not enough data.")
    else:
        print(f"{'feature':34} {'n':>4} {'spearman':>10} {'pearson':>10}")
        for row in result["correlations"][:10]:
            sp = "—" if row["spearman"] is None else f"{row['spearman']:+.3f}"
            pe = "—" if row["pearson"] is None else f"{row['pearson']:+.3f}"
            print(f"{row['feature']:34} {row['n']:>4} {sp:>10} {pe:>10}")

    print("\n=== Wait-time clustering ===")
    cluster = result["clusters"]
    print(f"Selected cluster count: {cluster.get('selected_k', 1)}")
    if cluster.get("silhouette") is not None:
        print(f"Cluster separation score: {cluster['silhouette']:.3f}")
    if cluster.get("outliers_ignored"):
        print(f"Extreme waits ignored for clustering only: {cluster['outliers_ignored']}")
    for i, c in enumerate(cluster.get("clusters", []), 1):
        print(
            f"  cluster {i}: n={c['count']} center={fmt_duration(c['center'])} "
            f"std={fmt_duration(c['stddev'])} range={fmt_duration(c['min'])}..{fmt_duration(c['max'])}"
        )

    print("\nMost common rounded waits:")
    for mode in result["rounded_modes"][:8]:
        print(f"  {fmt_duration(mode['seconds']):>10} : {mode['count']} cycle(s)  ({mode['bucket_minutes']}m buckets)")

    print("\n=== Walk-forward FEATURE model results ===")
    if not result["feature_models"]:
        print("Not enough data for feature models yet.")
    else:
        print(f"{'model':28} {'n':>4} {'med err':>10} {'mean err':>10} {'p90 err':>10} {'bias':>10}")
        for model in result["feature_models"]:
            print(
                f"{model.name:28} {model.predictions:>4} "
                f"{fmt_duration(model.median_absolute_error_seconds):>10} "
                f"{fmt_duration(model.mean_absolute_error_seconds):>10} "
                f"{fmt_duration(model.p90_absolute_error_seconds):>10} "
                f"{fmt_duration(model.signed_bias_seconds):>10}"
            )

    print("\n=== Walk-forward CLUSTER classifier results ===")
    classifiers = result.get("cluster_classifiers") or []
    if not classifiers:
        print("Not enough stable clustered history for cluster classifiers yet.")
    else:
        print(f"{'model':28} {'n':>4} {'cluster hit':>11} {'med err':>10} {'mean err':>10} {'p90 err':>10} {'bias':>10}")
        for model in classifiers:
            hit = "—" if model.cluster_accuracy is None else f"{model.cluster_accuracy * 100:.1f}%"
            print(
                f"{model.name:28} {model.predictions:>4} {hit:>11} "
                f"{fmt_duration(model.median_absolute_error_seconds):>10} "
                f"{fmt_duration(model.mean_absolute_error_seconds):>10} "
                f"{fmt_duration(model.p90_absolute_error_seconds):>10} "
                f"{fmt_duration(model.signed_bias_seconds):>10}"
            )

    print("\nInterpretation:")
    print("- Large |Spearman| values suggest a feature may help explain why waits change.")
    print("- Multiple tight wait clusters suggest the item may use discrete timing regimes rather than one smooth distribution.")
    print("- Cluster hit measures whether known-at-depletion features correctly identified the next timing regime; timing error still decides whether that classification is practically useful.")
    print("- A feature model only matters if it beats baseline_all_median in walk-forward testing; otherwise the feature is interesting but not predictive yet.")


if __name__ == "__main__":
    main()
