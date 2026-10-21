"""Run only staged pinned V128 source; isolated research, preview by default."""
import argparse
import importlib
import json
import sys
from pathlib import Path

STAGE=Path("/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research")
WORK=Path("/home/ubuntu/torn-fren-v38-probe")
MODULES=(
    "plushie_champions.common",
    "v60_private_snapshot_probe",
    "v88_poll_state_forward_report",
    "v102_restock_departure_bridge",
    "v107_explicit_restock_cycle_baseline",
    "v109_raw_restock_transition_event_audit",
    "v110_multicycle_restock_horizon_audit",
    "v123_empirical_phase_survival_challenger",
    "v125_earliest_credible_shadow",
    "v128_full24_earliest_shadow",
)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview",action="store_true")
    mode.add_argument("--record",action="store_true")
    a=p.parse_args()
    stage=STAGE.resolve(strict=True)
    assert (stage/"v38_roster.json").is_file(),"missing frozen roster"
    sys.path.insert(0,str(WORK.resolve(strict=True)))
    import research
    research.__path__=[str(stage), *[
        str(x) for x in research.__path__
        if Path(x).resolve()!=stage
    ]]
    importlib.invalidate_caches()
    for name in MODULES:
        mod=importlib.import_module("research."+name)
        expected=stage/"plushie_champions" if "." in name else stage
        if Path(mod.__file__).resolve().parent!=expected:
            raise RuntimeError("unpinned research module: "+name)
    v128=importlib.import_module("research.v128_full24_earliest_shadow")
    result=v128.observe(record=a.record)
    if result.get("roster_count")!=24:
        raise AssertionError("exact 24 research predictions not produced")
    if a.record:
        summary=dict(
            status=result["status"],
            issued_epoch=result["issued_epoch"],
            captured_epoch=result["captured_epoch"],
            roster_count=result["roster_count"],
            collector_heartbeat_age_seconds=result[
                "collector_heartbeat_age_seconds"],
            decision_status_counts=result["decision_status_counts"],
            private_sidecar=result["private_sidecar"],
            research_only=True,
        )
        print(json.dumps(summary,sort_keys=True))
    else:
        print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
