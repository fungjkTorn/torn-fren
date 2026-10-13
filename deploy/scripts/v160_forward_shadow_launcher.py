"""V160 isolated pinned stage launcher: no production/site operations."""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

WORK=Path("/home/ubuntu/torn-fren-v38-probe")
STAGE=Path("/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research")


def load():
    stage=STAGE.resolve(strict=True)
    if not (stage/"v38_roster.json").is_file():
        raise RuntimeError("missing pinned 24-item roster")
    sys.path.insert(0,str(WORK.resolve(strict=True)))
    import research
    research.__path__=[str(stage), *[
        str(p) for p in research.__path__
        if Path(p).resolve()!=stage
    ]]
    importlib.invalidate_caches()
    for name in (
        "v60_private_snapshot_probe",
        "v107_explicit_restock_cycle_baseline",
        "v125_earliest_credible_shadow",
        "v128_full24_earliest_shadow",
        "v145_provider_continuous_phases",
        "v151_stable_earliest_departure",
        "v160_prospective_v151_shadow",
        "v161_prospective_v151_forward_report",
    ):
        module=importlib.import_module("research."+name)
        if Path(module.__file__).resolve().parent!=stage:
            raise RuntimeError("unpinned shadow module: "+name)
    return (
        importlib.import_module("research.v160_prospective_v151_shadow"),
        importlib.import_module("research.v161_prospective_v151_forward_report"),
    )


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preview",action="store_true")
    group.add_argument("--record",action="store_true")
    group.add_argument("--report",action="store_true")
    a=parser.parse_args()
    capture,report=load()
    if a.report:
        output=report.score(days=7)
        print(json.dumps(output,sort_keys=True))
        return
    output=capture.capture_once(record=a.record)
    statuses=Counter(row["decision_status"] for row in output["predictions"].values())
    models={
        mode:sum(
            row["models"][mode]["departure_epoch"] is not None
            for row in output["predictions"].values())
        for mode in capture.MODEL_VARIANTS
    }
    print(json.dumps({
        "status":"V160_PRIVATE_FORWARDED_ISSUE" if a.record else
                 "V160_PRIVATE_PREVIEW_NO_WRITES",
        "roster":output["roster_count"],
        "issued_epoch":output["issued_epoch"],
        "source_heartbeat_age_seconds":output["source_heartbeat_age_seconds"],
        "latency_seconds":output["latency_seconds"],
        "model_candidates":models,
        "decision_statuses":dict(statuses),
        "sidecar_written":output["private_sidecar_written"],
        "collector_written":False,
        "websites_untouched":True,
        "specialists_untouched":True,
        "forward_lookahead_used":False,
        "real_player_flights_verified":False,
    },sort_keys=True))


if __name__=="__main__":
    main()
