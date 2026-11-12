"""Exact frozen generic v19 Canada/UK Xanax research single-tick adapter.

This is NOT the separately researched Japan Xanax specialist. Only the two
explicitly frozen v19 registry selections are available. The original v19
candidate engine has a six-hour native horizon and a five-minute replan,
which must not be silently inflated to eight hours.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from services.frozen_candidate_worker_v31 import frozen_single_tick

HERE = Path(__file__).resolve().parent
MASTER = HERE / "v42_can_uk_xanax_frozen_v19.json"
REGISTRY = HERE / "all_236_champions_v26.json"
ALLOWED = {"can:Xanax": "dyn8", "uni:Xanax": "dyn3"}
GENERATION = "v19"


def approved_source() -> bool:
    """Check that the exact source-pinned model identities still match."""
    frozen = json.loads(MASTER.read_text(encoding="utf-8"))["results"]
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["items"]
    from services.plushie_flower_dynamic_planner_v18 import configs
    source_configs = {x.name: asdict(x) for x in configs()}
    for key, name in ALLOWED.items():
        selected = registry[key]["original_all_item_selection"]
        if selected.get("model_family") != GENERATION or selected.get("config_name") != name:
            return False
        if frozen[key]["selected_on_training"]["config"] != source_configs.get(name):
            return False
    return True


def predict(db, country, item, now):
    country, item, now = str(country).strip().lower(), str(item).strip(), int(now)
    key = f"{country}:{item}"
    if key not in ALLOWED:
        return {"status": "NOT_APPROVED_FROZEN_XANAX_CANDIDATE"}
    if not approved_source():
        return {"status": "FROZEN_XANAX_CONFIG_MISMATCH"}
    # Generic 2019-model-family research candidate; only the existing native
    # versioned single-tick engine may generate its recommendation.
    output = frozen_single_tick(db, MASTER, GENERATION, country, item, now)
    if output.get("status") == "RESEARCH_PROPOSAL_ONLY":
        if (output.get("model_config") != ALLOWED[key]
                or output.get("model_generation") != GENERATION
                or output.get("replan_step_seconds") != 300
                or output.get("research_horizon_seconds") != 21600
                or output.get("quantity_threshold") != 30
                or output.get("grace_seconds") != 10
                or output.get("probability_calibrated") is not False):
            return {"status": "FROZEN_XANAX_OUTPUT_MISMATCH"}
        output["source"] = "V42_FROZEN_GENERIC_V19_XANAX_RESEARCH_ONLY"
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--item", required=True)
    parser.add_argument("--now", required=True, type=int)
    opts = parser.parse_args()
    try:
        result = predict(opts.db, opts.country, opts.item, opts.now)
    except Exception as exc:
        result = {"status": "V42_XANAX_CANDIDATE_ERROR", "error_type": type(exc).__name__}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
