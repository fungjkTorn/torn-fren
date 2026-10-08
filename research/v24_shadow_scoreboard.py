"""Read-only V24-v2 all-item shadow scoreboard. Never promotes live models.

Usage:
python -m research.v24_shadow_scoreboard \
  --master data/frozen_champion_v24/new_vm_master_v2_smoke.json \
  --csv data/frozen_champion_v24/v24_scoreboard.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

SCHEMA = "frozen-champion-v24-new-data-shadow-v2"
FIELDS = (
    "item", "status", "version", "eligible_starts", "recommendations",
    "coverage", "successes", "all_start_success_rate",
    "conditional_success_rate", "item_leader", "leader_evidence",
)


def summarize(master: dict, min_starts: int = 30) -> list[dict]:
    """Sort versions by all-eligible-start successes, not conditional hit rate.

    With no independent post-selection holdout or calibrated event forecasts,
    even a clear leader is only descriptive and never eligible for promotion.
    """
    if master.get("schema") != SCHEMA:
        raise ValueError("Expected V24-v2 replay. Never silently mix v1 denominators.")
    if min_starts < 1:
        raise ValueError("min_starts must be positive")
    out = []
    for item, result in sorted((master.get("results") or {}).items()):
        if result.get("status") != "complete":
            out.append(dict.fromkeys(FIELDS, None) | {
                "item": item, "status": result.get("status", "missing")
            })
            continue
        comparisons = (result.get("matched") or {}).get("versions") or {}
        if not comparisons:
            raise ValueError(f"{item}: missing V24-v2 matched results")
        values = []
        for version, result_row in sorted(comparisons.items()):
            eligible = int(result_row["paired_n"])
            recommended = int(result_row["recommendations"])
            hits = int(result_row["hits"])
            if eligible != result.get("shared_starts") or eligible < 1:
                raise ValueError(f"{item}:{version} bad eligible denominator")
            if not (0 <= hits <= recommended <= eligible):
                raise ValueError(f"{item}:{version} invalid hit/coverage counts")
            values.append((version, eligible, recommended, hits))
        max_hits = max(x[3] for x in values)
        leaders = [x[0] for x in values if x[3] == max_hits]
        leader = leaders[0] if len(leaders) == 1 else "tie"
        status = "too_few_independent_starts" if values[0][1] < min_starts else "descriptive_only_no_promotion"
        for version, n, recommended, hits in values:
            out.append({
                "item": item, "status": "complete", "version": version,
                "eligible_starts": n, "recommendations": recommended,
                "coverage": recommended / n,
                "successes": hits,
                "all_start_success_rate": hits / n,
                "conditional_success_rate": hits / recommended if recommended else None,
                "item_leader": leader, "leader_evidence": status,
            })
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--master", required=True)
    p.add_argument("--csv", required=True)
    p.add_argument("--min-starts", type=int, default=30)
    args = p.parse_args()
    report = json.loads(Path(args.master).read_text(encoding="utf-8"))
    rows = summarize(report, min_starts=args.min_starts)
    output = Path(args.csv)
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing report: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"WROTE {output}: {len(rows)} model rows; no model promotions")


if __name__ == "__main__":
    main()
