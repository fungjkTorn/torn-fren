"""V62 isolated ONE-SHOT private mirror smoke. Never alters scheduled workers.

Build a transactionally consistent DELETE-mode research copy, then evaluate
four source-pinned representative specialists (V18, V19, V20, Red Fox) against
the SAME snapshot. All results go to a separate opt-in research sidecar.
"""
from __future__ import annotations

import json
from pathlib import Path

from research.v60_private_snapshot_probe import (
    approved_collector_source, snapshot_once,
)
from research.v38_budgeted_runner import run_tick

SOURCE = Path("/opt/torn-fren/data/stock_history.db")
ROOT = Path("/var/lib/torn-fren-v38")
SNAPSHOT = ROOT / "v60_stock_snapshot.db"
ISOLATED_SIDECAR = ROOT / "v62_mirror_smoke.db"
LIVE_SIDECAR = ROOT / "private_predictions.db"
PROBE_KEYS = (
    "uni:Heather",             # original source-pinned V18
    "sou:African Violet",      # original source-pinned V19
    "chi:Peony",               # original source-pinned V20 traj12
    "uni:Red Fox Plushie",    # original k18/global-regime analog
)


def smoke(*, source=SOURCE, snapshot=SNAPSHOT, sidecar=ISOLATED_SIDECAR,
          snapshotter=snapshot_once, infer=run_tick):
    source, snapshot, sidecar = map(Path, (source, snapshot, sidecar))
    if source.resolve() == snapshot.resolve(strict=False):
        raise ValueError("live source and mirror must be distinct")
    if sidecar.resolve(strict=False) in (
        snapshot.resolve(strict=False), LIVE_SIDECAR.resolve(strict=False),
        source.resolve(),
    ):
        raise ValueError("research smoke cannot write active sidecar or stock DB")
    snap = snapshotter(source, snapshot)
    if not snap.get("published") or snap.get("status") != "PRIVATE_SNAPSHOT_READY":
        return {"status": "V62_NO_FRESH_SNAPSHOT", "research_only": True,
                "snapshot": snap, "executed": []}
    if not snapshot.is_file():
        raise RuntimeError("snapshot claimed published but is absent")
    # Observed heartbeat in this immutable mirror remains the time source.
    # A stale snapshot results in the existing runner/worker abstention paths.
    result = infer(
        stock_db=snapshot, sidecar_db=sidecar, execute=True,
        with_xanax=True, with_redfox=True, approved_keys=PROBE_KEYS,
        max_jobs=4, worker_seconds=30, budget_seconds=160,
        max_rows=10000,
    )
    records = result.get("executed", [])
    return {
        "status": ("V62_SMOKE_EXECUTED" if result.get("mode") ==
                   "EXECUTED_RESEARCH_ONLY" else "V62_SMOKE_DEFERRED"),
        "research_only": True,
        "collector_written": False,
        "snapshot": snap,
        "runner_mode": result.get("mode"),
        "snapshot_path_is_private": snapshot.parent.resolve() == ROOT.resolve(),
        "results": records,
        "proposal_count": sum(r.get("status") == "RESEARCH_PROPOSAL_ONLY"
                              for r in records),
        "error_count": sum(str(r.get("status","")).endswith("_ERROR")
                           for r in records),
    }


def main():
    # No configuration flags: callers cannot redirect sidecar to production.
    # Approved source is canonicalized on both sides to support the symlink.
    if not approved_collector_source(SOURCE):
        raise SystemExit("STOP: collector source identity mismatch")
    if not ROOT.is_dir():
        raise SystemExit("STOP: private research directory absent")
    try:
        output = smoke()
    except Exception as exc:
        # Safe text only: avoid logging SQL, paths, API keys or tracebacks.
        output = {"status": "V62_SMOKE_ERROR",
                  "error_type": type(exc).__name__,
                  "research_only": True}
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
