"""Pinned research-only V125 entry point. Explicit --preview or --record."""

import argparse
import importlib
import json
import sys
from pathlib import Path

RESEARCH = Path("/home/ubuntu/torn-fren-private-models/v127_stage/pinned/research")
CHECKOUT = Path("/home/ubuntu/torn-fren-v38-probe")
MODULES = (
    "plushie_champions.common",
    "v60_private_snapshot_probe",
    "v88_poll_state_forward_report",
    "v102_restock_departure_bridge",
    "v107_explicit_restock_cycle_baseline",
    "v109_raw_restock_transition_event_audit",
    "v110_multicycle_restock_horizon_audit",
    "v123_empirical_phase_survival_challenger",
    "v125_earliest_credible_shadow",
)


def load():
    stage = RESEARCH.resolve(strict=True)
    repo = CHECKOUT.resolve(strict=True)
    sys.path.insert(0, str(repo))
    import research
    research.__path__ = [
        str(stage),
        *[str(p) for p in research.__path__ if Path(p).resolve() != stage],
    ]
    importlib.invalidate_caches()
    for name in MODULES:
        module = importlib.import_module("research." + name)
        expected = stage / "plushie_champions" if "." in name else stage
        assert Path(module.__file__).resolve().parent == expected, name
    return importlib.import_module("research.v125_earliest_credible_shadow")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--record", action="store_true")
    args = parser.parse_args()
    result = load().observe(record=args.record)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
