"""Conservative per-item source-revision gate for experimental V38 web V2 reuse.

A verified collector heartbeat certifies that a quiet item's last change is
still the observed state. Never use a 20-second wall TTL to trigger repeatedly
expensive history rebuilds while the underlying stock and gap data are identical.
Active departure reachability is rolled forward in the web process separately.
This module only reads local SQLite; neither stock nor heartbeat is written.
"""
from __future__ import annotations

from contextlib import closing
import sqlite3
from pathlib import Path


def revision(db_path, *, country, item, item_state, now, max_age=180,
             replan_seconds=300):
    """Return either (FRESH, revision tuple) or (reason, None).

    Uses the latest item state already read for the /history response. Epoch is
    deliberately tied to a 5-minute clock boundary, not just a 5-minute TTL.
    Collection-gap versions invalidate regardless of item row timestamp.
    """
    if not item_state or not item_state.get("timestamp"):
        return "NO_ITEM_STATE", None
    now=int(now)
    if replan_seconds != 300:
        raise ValueError("V38 research cache cadence must remain five minutes")
    last_change=int(item_state["timestamp"])
    if last_change>now:
        return "FUTURE_STOCK", None
    try:
        path=Path(db_path).resolve(strict=True)
        with closing(sqlite3.connect(
                path.as_uri()+"?mode=ro",uri=True,timeout=.2)) as db:
            db.execute("PRAGMA query_only=ON")
            heartbeat=db.execute("""
                SELECT MAX(timestamp) FROM poll_heartbeats
                WHERE mode='poll-cycle' AND success=1
            """).fetchone()[0]
            gaps=db.execute("""
                SELECT COALESCE(MAX(id),0),COALESCE(MAX(end_timestamp),0)
                FROM collection_gaps
            """).fetchone()
    except (OSError,sqlite3.Error,ValueError):
        return "NO_VERIFIABLE_REVISION", None
    if heartbeat is None or heartbeat>now or now-int(heartbeat)>max_age:
        return "COLLECTOR_STALE_OR_NO_HEARTBEAT", None
    # Quantity and cost changes invalidate the base response. End-time changes
    # or new collector gaps also invalidate all history-dependent predictions.
    token=(country.lower(),item.lower(),last_change,
           item_state.get("quantity"),item_state.get("cost"),
           item_state.get("source"),int(gaps[0]),int(gaps[1]),
           now//replan_seconds)
    return "FRESH",token
