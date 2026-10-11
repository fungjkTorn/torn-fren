"""V81 private, as-issued Lion/Panda A/B/selector comparison.

Uses one read-only V75 stock snapshot, with causal feature context shared
between both items. Never modifies V75, public services or gameplay.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import time
from pathlib import Path

from research.plushie_champions.common import (
    AnalogPlanner, ResearchContext, GRACE, MAX_WAIT, MIN_QTY, STEP, TRAVEL_SECONDS,
)
from research.v49_lion_panda_pair_probe import TARGETS, original_features
from research.v50_pair_selector_artifact import choose_from_features
from research.v52_pair_trained_tick import load_pinned_artifact
from services.frozen_candidate_worker_v31 import inspect_live_source

SOURCE = Path("/var/lib/torn-fren-v38/v75_stock_snapshot.db")
ARTIFACT_DIR = Path("/home/ubuntu/torn-fren-private-models")
SIDECAR = ARTIFACT_DIR / "v81_pair_forward.db"
PINS = {
    "lion": "a8a5e7d989c701fa75975dd9b8d73c128e5fd895298443c2cfd6bb3d72e824bd",
    "panda": "84037c778301fa5a3825007dd439abec7c971ec05b176efae3bffe99fc827280",
}
VARIANTS = ("a", "b", "selector")
SCHEMA = """CREATE TABLE IF NOT EXISTS pair_issued_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_key TEXT NOT NULL,
    variant TEXT NOT NULL,
    issued_at INTEGER NOT NULL,
    planned_at INTEGER NOT NULL,
    stock_as_of INTEGER NOT NULL,
    valid_until INTEGER NOT NULL,
    status TEXT NOT NULL,
    selected_expert TEXT NOT NULL,
    departure INTEGER,
    arrival INTEGER,
    artifact_sha256 TEXT NOT NULL,
    min_quantity INTEGER NOT NULL,
    grace_seconds INTEGER NOT NULL,
    actual_player_departure INTEGER NOT NULL DEFAULT 0,
    UNIQUE(item_key,variant,issued_at)
)"""


def v75_busy():
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", "torn-fren-v38-private-shadow.service"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0


def file_stamp(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def bounded(proposal, issued, country):
    if proposal is None:
        return "EXPERT_ABSTAINED", None, None
    departure = int(proposal[0])
    if departure < issued:
        return "DEPARTURE_PASSED", None, None
    if departure > issued + MAX_WAIT:
        return "OUT_OF_HORIZON", None, None
    return "FORWARD_CANDIDATE_ONLY", departure, departure + TRAVEL_SECONDS[country]


def store_decisions(ledger, records):
    target = Path(ledger)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("unsafe research ledger symlink")
    if target.resolve(strict=False) == SOURCE.resolve(strict=False):
        raise ValueError("collector sidecar collision")
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target, timeout=5) as con:
        con.execute("PRAGMA busy_timeout=5000")
        con.execute(SCHEMA)
        con.execute("CREATE INDEX IF NOT EXISTS v81_arrival ON pair_issued_decisions(arrival)")
        con.executemany("""INSERT OR IGNORE INTO pair_issued_decisions (
            item_key,variant,issued_at,planned_at,stock_as_of,valid_until,
            status,selected_expert,departure,arrival,artifact_sha256,
            min_quantity,grace_seconds,actual_player_departure
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)""", records)


def tick(*, source=SOURCE, artifact_dir=ARTIFACT_DIR, ledger=SIDECAR,
         clock=time.time, inspector=inspect_live_source,
         context_builder=ResearchContext.build, planner_cls=AnalogPlanner,
         busy_check=v75_busy):
    source = Path(source)
    artifact_dir = Path(artifact_dir)
    ledger = Path(ledger)
    if source.is_symlink() or not source.is_file():
        raise ValueError("snapshot is not a regular research file")
    if ledger.resolve(strict=False) == source.resolve(strict=True):
        raise ValueError("ledger cannot overwrite snapshot")
    if busy_check():
        return {"status": "V81_DEFERRED_V75_BUSY", "records_written": 0}

    start = int(clock())
    models = {}
    for target, digest in PINS.items():
        path = artifact_dir / f"{target}_selector_artifact.json"
        if path.is_symlink():
            raise ValueError("artifact cannot be a symlink")
        models[target] = load_pinned_artifact(path, digest, target)

    before = inspector(source, start)
    if before.get("status") != "FRESH":
        return {"status": "V81_SOURCE_NOT_FRESH", "source_status": before.get("status"),
                "records_written": 0}
    source_as_of = before["last_successful_heartbeat"]
    if any(model["train_asof"] >= source_as_of for model in models.values()):
        raise ValueError("training cutoff not older than source evidence")
    stamp = file_stamp(source)
    planned = start // STEP * STEP

    context = context_builder(str(source), asof=start, readonly=True)
    choices = {}
    try:
        if not len(context.grid) or planned > context.grid[-1]:
            return {"status": "V81_CONTEXT_UNAVAILABLE", "records_written": 0}
        for target, config in TARGETS.items():
            country, item = config["key"].split(":", 1)
            pair = {}
            for expert in ("a", "b"):
                k, weight = config["expert_" + expert]
                pair[expert] = planner_cls(
                    context, country, item, k=k, global_weight=weight,
                    cutoff=planned,
                ).plan(float(planned))
            features = original_features(
                context, country, item, float(planned),
                pair["a"], pair["b"], target,
            )
            selected = "b" if choose_from_features(models[target], features) else "a"
            choices[target] = (pair, selected)
    finally:
        context.con.close()

    issued = int(clock())
    after = inspector(source, issued)
    if (file_stamp(source) != stamp or after.get("status") != "FRESH" or
            after.get("last_successful_heartbeat") != source_as_of or
            not 0 <= issued - source_as_of <= 180):
        return {"status": "V81_SOURCE_CHANGED_OR_STALE", "records_written": 0}

    records = []
    summary = {}
    for target, (pair, selected) in choices.items():
        config = TARGETS[target]
        country = config["key"].split(":", 1)[0]
        summary[target] = {}
        for variant in VARIANTS:
            picked = selected if variant == "selector" else variant
            status, dep, arr = bounded(pair[picked], issued, country)
            records.append((config["key"], variant, issued, planned,
                            source_as_of, issued + STEP, status, picked,
                            dep, arr, PINS[target], MIN_QTY, GRACE))
            summary[target][variant] = {
                "status": status, "selected_expert": picked,
            }

    if len(records) != 6:
        raise AssertionError("expected exactly six comparisons")
    store_decisions(ledger, records)
    return {"status": "V81_PRIVATE_PAIR_RECORDED", "records_written": len(records),
            "issued_at": issued, "stock_as_of": source_as_of,
            "planning_timestamp": planned, "research_only": True,
            "published_to_website": False, "gameplay_automated": False,
            "comparisons": summary}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--status", action="store_true", help="read-only ledger counts")
    args = p.parse_args()
    if args.status:
        if not SIDECAR.is_file():
            print(json.dumps({"status": "V81_LEDGER_ABSENT"}))
            return
        with sqlite3.connect(SIDECAR.as_uri() + "?mode=ro", uri=True) as con:
            rows = con.execute("""SELECT item_key,variant,status,count(*)
                       FROM pair_issued_decisions
                       GROUP BY item_key,variant,status""").fetchall()
        print(json.dumps({"status": "V81_LEDGER_COUNTS", "rows": rows}, sort_keys=True))
        return
    result = tick()
    print(json.dumps(result, sort_keys=True))
    if result["status"] not in {"V81_PRIVATE_PAIR_RECORDED", "V81_DEFERRED_V75_BUSY"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
