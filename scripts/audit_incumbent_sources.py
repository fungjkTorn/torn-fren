"""Read-only inventory of each historical pinned incumbent; no model execution.

Helps recover specialist sources from the user's older PC checkout before
implementing causal research adapters. A filename match is *not* equivalent
to a validated runtime or model result. Never auto-promote a recovered file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"research"/"v38_roster.json"
XANAX_EXTRAS={
    "can:Xanax":dict(model_family="V19",config_name="dyn8",
                     source_path="services/plushie_flower_dynamic_planner_v19.py",
                     source_verified=True),
    "uni:Xanax":dict(model_family="V19",config_name="dyn3",
                     source_path="services/plushie_flower_dynamic_planner_v19.py",
                     source_verified=True),
}


def inventory(external_root=None):
    entries=dict(json.loads(REGISTRY.read_text(encoding="utf-8"))["items"])
    if len(entries)!=22 or set(entries)&set(XANAX_EXTRAS):
        raise ValueError("Unexpected pinned historical specialist registry")
    entries.update(XANAX_EXTRAS)
    recovered_root=Path(external_root).expanduser().resolve(strict=True) if external_root else None
    if recovered_root is not None and not recovered_root.is_dir():
        raise ValueError("External code root must be a directory")
    out={}
    for key,entry in sorted(entries.items()):
        source=entry.get("source_path")
        checked=ROOT/source if source else None
        checked_exists=bool(checked and checked.is_file())
        # Only EXACT declared basename (not an arbitrary code search hit).
        found=[]
        if recovered_root is not None and source:
            external=recovered_root/source
            if external.is_file():found.append(str(external))
            elif (recovered_root/Path(source).name).is_file():
                found.append(str(recovered_root/Path(source).name))
        out[key]=dict(model_family=entry.get("model_family"),
            config_name=entry.get("config_name"),
            recorded_source_path=source,
            repository_file_present=checked_exists,
            previously_marked_source_verified=bool(entry.get("source_verified")),
            recovered_other_checkout_paths=found,
            separate_research_variant_paths=(
                ["research/japan_xanax/renewal_shadow.py"]
                if key=="jap:Xanax" and
                (ROOT/"research/japan_xanax/renewal_shadow.py").is_file()
                else []),
            separate_variant_is_original_incumbent=False,
            restock_clock_baseline_instead_of_incumbent=False,
            incumbent_historical_replay_verified=False,
            incumbent_physical_restock_accuracy_measured=False,
            incumbent_flight_survival_measured=False)
    if len(out)!=24:raise ValueError("24 item incumbent registry required")
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--external-root",type=Path,
                   help="Optional older local PC project root to inspect without writes")
    p.add_argument("--output",type=Path,
                   help="Optional report JSON file in research results directory")
    args=p.parse_args()
    rows=inventory(args.external_root)
    print("ITEM-SPECIFIC PINNED CHAMPIONS (not yet retested in this baseline):")
    for key,item in rows.items():
        flag="CHECKOUT_SOURCE" if item["repository_file_present"] else (
             "OLDER_PC_SOURCE" if item["recovered_other_checkout_paths"] else
             "SEPARATE_RESEARCH_VARIANT_ONLY" if item["separate_research_variant_paths"] else
             "SOURCE_NOT_YET_LOCATED")
        print(key+" | "+str(item["model_family"])+"/"+str(item["config_name"])+
              " | "+flag)
    if args.output:
        dest=args.output.expanduser().resolve()
        if dest.exists() or not dest.parent.is_dir() or dest.suffix!=".json":
            raise ValueError("Provide an unused .json path with existing parent folder")
        dest.write_text(json.dumps(dict(status="INCUMBENTS_NOT_YET_REPLAYED",
            model_count=len(rows),items=rows,production_modified=False,
            any_new_flight_accuracy_claim=False),indent=2,sort_keys=True)+"\n",
            encoding="utf-8")
        print("WROTE",dest)


if __name__=="__main__":
    main()
