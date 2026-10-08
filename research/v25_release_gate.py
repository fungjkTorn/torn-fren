"""Research-only evidence gate for a Torn Fren item-specific model promotion.

This module has no side effects, no database writes and no gameplay actions.
A positive outcome is prerequisite evidence, not a guarantee of player success.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def assess(evidence: dict, target: str = "public_live_guidance") -> dict:
    valid = {"experimental_private_shadow", "public_live_guidance"}
    if target not in valid:
        raise ValueError(f"Unknown target: {target}")
    blockers = []
    def require(condition, reason):
        if not condition:
            blockers.append(reason)

    require(bool(evidence.get("frozen_model_id")), "missing frozen model identity")
    require(bool(evidence.get("raw_config_sha256")), "missing exact config hash")
    require(bool(evidence.get("read_only_shadow")), "shadow must be read-only, never automatic travel")
    require(bool(evidence.get("baseline_fallback_tested")), "V2 fallback not tested")
    require(bool(evidence.get("freshness_and_gap_checks_tested")), "collector freshness/gaps not tested")

    if evidence.get("uses_item_specific_specialist"):
        require(bool(evidence.get("specialist_source_present_and_importable")),
                "item-specific specialist source missing or not importable")
        require(bool(evidence.get("item_specific_departure_adapter_tested")),
                "item-specific specialist needs a tested live departure adapter")

    if evidence.get("uses_japan_xanax_specialist"):
        require(bool(evidence.get("specialist_live_departure_adapter_tested")),
                "Japan specialist does not yet have a validated real-time departure adapter")

    if evidence.get("publishes_probability"):
        require(bool(evidence.get("probabilities_independently_calibrated")),
                "cannot publish uncalibrated trip-success percentages")

    if target == "public_live_guidance":
        require(bool(evidence.get("native_replay_parity_passed")), "no native replay parity")
        require(bool(evidence.get("causal_prefix_invariance_passed")),
                "replay may use future data to qualify predecision history")
        require(bool(evidence.get("prospective_after_model_freeze")), "no untouched forward validation")
        require(int(evidence.get("independent_starts") or 0) >= 30,
                "fewer than 30 prospective eligible starts")
        require(int(evidence.get("distinct_resolved_qualified_windows") or 0) >= 8,
                "fewer than 8 distinct resolved stock windows")
        item_key = evidence.get("item_key")
        require(bool(item_key), "missing item key for item-specific promotion")
        temporary_75 = item_key in {
            "arg:Monkey Plushie", "swi:Chamois Plushie", "uae:Camel Plushie"
        }
        minimum = .75 if temporary_75 else .90
        requested = float(evidence.get("required_arrival_success", minimum))
        require(requested >= minimum,
                "requested reliability target below allowed per-item floor")
        if temporary_75 and requested < .90:
            require(bool(evidence.get("temporary_low_reliability_caution_visible")),
                    "temporary 75%-floor plushie requires explicit caution disclosure")
        require(float(evidence.get("all_start_success") or 0) >= max(requested, minimum),
                "all-start arrival success below reliability target")
        require(float(evidence.get("coverage") or 0) >= 0.95,
                "recommendation coverage below 95%")
        require(bool(evidence.get("feature_flag_default_off")), "public feature flag must default OFF")
        require(bool(evidence.get("rollback_smoke_tested")), "rollback not tested")

    return {"target": target, "ready": not blockers, "blockers": blockers,
            "note": "Passing these checks does not create calibrated individual trip probabilities."}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True)
    p.add_argument("--target", choices=("experimental_private_shadow", "public_live_guidance"),
                   default="public_live_guidance")
    p.add_argument("--output")
    args = p.parse_args()
    report = assess(json.loads(Path(args.evidence).read_text(encoding="utf-8")), args.target)
    contents = json.dumps(report, indent=2)
    if args.output:
        output = Path(args.output)
        if output.exists():
            raise SystemExit("Refusing to overwrite an existing audit: " + str(output))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(contents + "\n", encoding="utf-8")
    print(contents)
    raise SystemExit(0 if report["ready"] else 2)


if __name__ == "__main__":
    main()
