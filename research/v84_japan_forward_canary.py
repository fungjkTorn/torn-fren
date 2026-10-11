"""V84 single-shot, Japan Xanax V8 private forward canary.

Never schedules, publishes, sends gameplay actions, or changes the V75/V82
workers. Saves as-issued evidence (including model abstentions) in an isolated
research SQLite ledger after a fresh read-only collector snapshot. All source
inspection uses the independent immutable snapshot, not live WAL history.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import time
from pathlib import Path

from research.japan_xanax.v8_regime_candidate import predict as japan_predict
from research.v60_private_snapshot_probe import approved_collector_source
from research.v65_private_mirror_shadow_tick import snapshot_with_retry
from services.frozen_candidate_worker_v31 import inspect_live_source

COLLECTOR = Path("/opt/torn-fren/data/stock_history.db")
SNAPSHOT = Path("/var/lib/torn-fren-v38/v84_japan_stock_snapshot.db")
LEDGER = Path("/home/ubuntu/torn-fren-private-models/v84_japan_forward.db")
STEP = 300
HORIZON = 28800
TRAVEL = 8940
SCHEMA = """CREATE TABLE IF NOT EXISTS japan_forward_decisions (
    slot INTEGER PRIMARY KEY,
    queried_at INTEGER NOT NULL,
    issued_at INTEGER NOT NULL,
    source_heartbeat INTEGER NOT NULL,
    status TEXT NOT NULL,
    model_generation TEXT,
    model_config TEXT,
    departure INTEGER,
    arrival INTEGER,
    quantity_threshold INTEGER NOT NULL,
    grace_seconds INTEGER NOT NULL,
    actual_player_departure INTEGER NOT NULL DEFAULT 0,
    source_model TEXT NOT NULL,
    experiment TEXT NOT NULL
)"""


def research_workers_busy():
    return any(subprocess.run(
        ["systemctl", "is-active", "--quiet", name],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode == 0 for name in (
        "torn-fren-v38-private-shadow.service",
        "torn-fren-v82-pair-forward.service",
    ))


def file_stamp(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def safe_paths(collector, snapshot, ledger):
    src = Path(collector)
    snap = Path(snapshot)
    log = Path(ledger)
    if snap.is_symlink() or log.is_symlink() or log.parent.is_symlink():
        raise ValueError("unsafe research output symlink")
    paths = (src.resolve(strict=True), snap.resolve(strict=False),
             log.resolve(strict=False))
    if len(set(paths)) != 3 or paths[0] in (paths[1], paths[2]):
        raise ValueError("source and research outputs must be distinct")


def verified_candidate(result, queried, issued):
    if not isinstance(result, dict):
        return "INVALID_V8_RESULT", None, None
    status = str(result.get("status", "INVALID_V8_RESULT"))
    if status != "RESEARCH_PROPOSAL_ONLY":
        return status[:64], None, None
    try:
        dep = result["recommended_departure_timestamp"]
        arr = result["recommended_arrival_timestamp"]
        if (type(dep) is not int or type(arr) is not int or
            result.get("key") != "jap:Xanax" or
            result.get("model_generation") != "V8_REGIME_CANDIDATE" or
            result.get("research_horizon_seconds") != HORIZON or
            result.get("replan_step_seconds") != STEP or
            result.get("quantity_threshold") != 30 or
            result.get("grace_seconds") != 10 or
            result.get("gameplay_automated") is not False or
            result.get("probability_calibrated") is not False or
            result.get("query_timestamp") != queried or
            arr - dep != TRAVEL or dep > queried + HORIZON):
            return "INVALID_V8_CONTRACT", None, None
        if dep < issued:
            return "DEPARTURE_PASSED_BEFORE_ISSUE", None, None
        return "FORWARD_CANDIDATE_ONLY", dep, arr
    except (KeyError, TypeError, ValueError):
        return "INVALID_V8_CONTRACT", None, None


def store(ledger, record):
    if Path(ledger).is_symlink():
        raise ValueError("research sidecar symlink")
    with sqlite3.connect(ledger, timeout=5) as con:
        con.execute("PRAGMA busy_timeout=5000")
        con.execute(SCHEMA)
        con.execute("""INSERT OR IGNORE INTO japan_forward_decisions
           (slot,queried_at,issued_at,source_heartbeat,status,
            model_generation,model_config,departure,arrival,
            quantity_threshold,grace_seconds,actual_player_departure,
            source_model,experiment)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,0,?,?)""", record)


def tick(*, collector=COLLECTOR, snapshot=SNAPSHOT, ledger=LEDGER,
         clock=time.time, source_approver=approved_collector_source,
         snapshotter=snapshot_with_retry, inspector=inspect_live_source,
         predictor=japan_predict, busy_check=research_workers_busy):
    if not source_approver(collector):
        return {"status": "V84_UNAPPROVED_COLLECTOR", "records_written": 0}
    safe_paths(collector, snapshot, ledger)
    if busy_check():
        return {"status": "V84_DEFERRED_RESEARCH_BUSY", "records_written": 0}
    snap = snapshotter(collector, snapshot)
    if snap.get("status") != "PRIVATE_SNAPSHOT_READY" or not snap.get("published"):
        return {"status": "V84_SNAPSHOT_NOT_READY", "records_written": 0}
    if Path(snapshot).is_symlink() or not Path(snapshot).is_file():
        raise ValueError("V84 snapshot not regular")
    queried = int(clock())
    before = inspector(snapshot, queried)
    if before.get("status") != "FRESH":
        return {"status": "V84_SOURCE_NOT_FRESH", "records_written": 0,
                "source_status": before.get("status")}
    heartbeat = before["last_successful_heartbeat"]
    stamp = file_stamp(snapshot)
    result = predictor(str(snapshot), "jap", "Xanax", queried)
    issued = int(clock())
    slot = queried // STEP * STEP
    if not 0 <= issued - slot < STEP:
        return {"status": "V84_PLANNING_SLOT_EXPIRED", "records_written": 0}
    after = inspector(snapshot, issued)
    if (file_stamp(snapshot) != stamp or after.get("status") != "FRESH" or
        after.get("last_successful_heartbeat") != heartbeat or
        not 0 <= issued - heartbeat <= 180):
        return {"status": "V84_SOURCE_CHANGED_OR_STALE", "records_written": 0}

    status, departure, arrival = verified_candidate(result, queried, issued)
    # Abstentions are stored with NULL departure and arrival; unverified
    # model outputs never become actionable private candidate records.
    record = (slot, queried, issued, heartbeat, status,
              str(result.get("model_generation", ""))[:64]
                  if isinstance(result, dict) else "",
              str(result.get("model_config", ""))[:128]
                  if isinstance(result, dict) else "",
              departure, arrival, 30, 10,
              "v8_regime_candidate_checkpoint_parity_pending",
              "v84_japan_private_canary")
    store(ledger, record)
    return {"status": "V84_JAPAN_RESEARCH_RECORDED",
            "model_status": status, "model_config": record[6],
            "records_written": 1, "issued_at": issued,
            "source_heartbeat_age_seconds": issued - heartbeat,
            "planning_age_seconds": issued - slot,
            "research_only": True, "published_to_website": False,
            "gameplay_automated": False,
            "recommended_departure_timestamp": departure,
            "recommended_arrival_timestamp": arrival}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        if not LEDGER.is_file():
            print(json.dumps({"status": "V84_LEDGER_ABSENT"}))
            return
        with sqlite3.connect(LEDGER.as_uri() + "?mode=ro", uri=True) as con:
            rows = con.execute("""SELECT status, COUNT(*) FROM japan_forward_decisions
                                  GROUP BY status ORDER BY status""").fetchall()
        print(json.dumps({"status": "V84_LEDGER_COUNTS", "rows": rows}))
        return
    try:
        answer = tick()
    except Exception as exc:
        answer = {"status": "V84_CANARY_ERROR",
                  "error_type": type(exc).__name__, "records_written": 0}
    print(json.dumps(answer, sort_keys=True))
    if answer["status"] not in ("V84_JAPAN_RESEARCH_RECORDED",
                                "V84_DEFERRED_RESEARCH_BUSY"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
