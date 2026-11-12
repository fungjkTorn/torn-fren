"""Read-only preflight for the first isolated 5/16 flower-plushie canary.

No inference, no historical DB writes, no service actions, no tokens.
Passing this gate authorizes a *manual read-only runtime probe*, never a
production service deployment or player-facing predictions.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path

from research.v38_readonly_resource_probe import ALL, PROBES

FRESH_SECONDS = 180
EXPECTED_FLOWER_PLUSHIE_COUNT = 21


def inspect(db: str | Path, *, now: int | None = None,
            cpu_slots: int | None = None, load1: float | None = None) -> dict:
    now = int(time.time() if now is None else now)
    if cpu_slots is None:
        cpu_slots = (len(os.sched_getaffinity(0))
                     if hasattr(os, "sched_getaffinity") else os.cpu_count())
    if load1 is None:
        load1 = os.getloadavg()[0]
    cpu_slots = max(1, int(cpu_slots or 1))
    load1 = float(load1)
    budget_ok = load1 <= cpu_slots * 0.80
    source = {"status": "NOT_CHECKED", "last_successful_poll": None,
              "age_seconds": None}
    try:
        real = Path(db).resolve(strict=True)
        with sqlite3.connect(real.as_uri() + "?mode=ro",
                             uri=True, timeout=2.0) as con:
            con.execute("PRAGMA query_only=ON")
            row = con.execute("""
                SELECT MAX(timestamp) FROM poll_heartbeats
                WHERE mode='poll-cycle' AND success=1
            """).fetchone()
            heartbeat = int(row[0]) if row and row[0] is not None else None
            last_stock = con.execute(
                "SELECT MAX(timestamp) FROM stock_history"
            ).fetchone()[0]
            if heartbeat is None:
                status = "COLLECTOR_NO_SUCCESS"
            elif heartbeat > now:
                status = "FUTURE_HEARTBEAT"
            elif now - heartbeat > FRESH_SECONDS:
                status = "COLLECTOR_STALE"
            elif last_stock is None:
                status = "NO_STOCK_ROWS"
            elif int(last_stock) > now:
                status = "FUTURE_STOCK_ROWS"
            else:
                status = "FRESH"
            source = {"status": status,
                      "last_successful_poll": heartbeat,
                      "age_seconds": now - heartbeat if heartbeat is not None else None}
    except (OSError, sqlite3.Error) as error:
        source = {"status": "COLLECTOR_READ_ERROR",
                  "error_type": type(error).__name__,
                  "last_successful_poll": None,"age_seconds": None}
    eligible = sorted(ALL)
    return {
        "status": ("READY_FOR_BOUNDED_READONLY_PROBE"
                   if source["status"] == "FRESH" and budget_ok
                   else "DEFER_PROBE"),
        "source": source,
        "capacity": {"cpu_slots":cpu_slots,"load1":round(load1,3),
                     "max_load1":round(cpu_slots*.80,3),"headroom_ok":budget_ok},
        "first_five":list(PROBES),"source_pinned_worker_count":len(eligible),
        "flower_plushie_roster_count":EXPECTED_FLOWER_PLUSHIE_COUNT,
        "not_integrated_count":EXPECTED_FLOWER_PLUSHIE_COUNT-len(eligible),
        "read_only":True,"services_changed":False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",default="/opt/torn-fren/data/stock_history.db")
    args = parser.parse_args()
    report = inspect(args.db)
    print(json.dumps(report,indent=2,sort_keys=True))
    if report["status"] != "READY_FOR_BOUNDED_READONLY_PROBE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
