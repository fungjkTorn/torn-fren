"""Build a research-only 236-item registry with the frozen plushie handoff.

Explicitly NOT a runtime planner, probability calibration, or deployment hook.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path


SOURCE_KEYS = ("v19", "v20", "v21")


def _config_hash(config):
    raw = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def merge_registry(prior, plushie_manifest, masters):
    if not isinstance(prior, list) or len(prior) != 236:
        raise ValueError("expected 236 prior all-item candidates")
    index = {row["item_key"]: row for row in prior}
    if len(index) != len(prior):
        raise ValueError("duplicate all-item keys")
    overrides = plushie_manifest["items"]
    if len(overrides) != 21 or len({x["item_key"] for x in overrides}) != 21:
        raise ValueError("expected 21 unique flower/plushie handoff rows")
    if not set(x["item_key"] for x in overrides) <= index.keys():
        raise ValueError("handoff item is missing from catalog")
    if any(x["promotion_status"] != "RESEARCH_ONLY_BLOCKED" for x in overrides):
        raise ValueError("cannot merge a pre-promoted champion into a research registry")
    frozen = {}
    for key, row in sorted(index.items()):
        dynamic = {}
        for family in SOURCE_KEYS:
            record = masters[family].get("results", {}).get(key, {})
            config = (record.get("selected_on_training") or {}).get("config")
            if record.get("status") == "complete" and config:
                dynamic[family] = {
                    "config": config,
                    "sha256": _config_hash(config),
                    "status": "research_candidate",
                }
        frozen[key] = {
            "item_key": key,
            "category": row["category"],
            "historical_all_item_selection": {
                "family": row["old_provisional_family"],
                "config": row["old_provisional_config"] or None,
                "historical_success_rate": float(row["old_matched_success_rate"]) if row.get("old_matched_success_rate") else None,
                "historical_hits": int(row["old_matched_hits"]) if row.get("old_matched_hits") else None,
                "historical_n": int(row["old_matched_n"]) if row.get("old_matched_n") else None,
            },
            "frozen_generic_candidates": dynamic,
            "candidate": {
                "model_family": row["old_provisional_family"],
                "config_name": row["old_provisional_config"] or None,
                "source": "old_all_item_provisional",
            },
            "promotion_status": "RESEARCH_ONLY_BLOCKED",
        }
    for override in overrides:
        key = override["item_key"]
        frozen[key]["candidate"] = override
        frozen[key]["replaces_old_all_item_candidate_for_research"] = True
    if "jap:Xanax" in frozen:
        if "jap:Xanax" in {x["item_key"] for x in overrides}:
            raise ValueError("Japan Xanax specialist must remain separate")
        frozen["jap:Xanax"]["candidate"] = {
            "model_family": "japan_xanax_specialist",
            "source": "separate_specialist_research",
            "promotion_status": "RESEARCH_ONLY_BLOCKED",
        }
    return {
        "schema": "torn-fren-236-candidate-registry-v26-research-only",
        "benchmark_warning": "8h specialized plushie holdouts are not matched to 12h generic holdouts.",
        "promotion_warning": "NO model should be routed to production from this file alone.",
        "items": frozen,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-csv", required=True)
    parser.add_argument("--plushies", default="research/plushie_flower_champions_v26.json")
    for family in SOURCE_KEYS:
        parser.add_argument("--" + family, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    prior = list(csv.DictReader(Path(args.prior_csv).open(encoding="utf-8-sig", newline="")))
    plushies = json.loads(Path(args.plushies).read_text(encoding="utf-8"))
    masters = {
        family: json.loads(Path(getattr(args, family)).read_text(encoding="utf-8"))
        for family in SOURCE_KEYS
    }
    artifact = merge_registry(prior, plushies, masters)
    output = Path(args.output)
    if output.exists():
        raise SystemExit("Refusing to overwrite existing frozen registry: " + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"Frozen {len(artifact['items'])} research candidates, including 21 plushie/flower overrides: {output}")


if __name__ == "__main__":
    main()
