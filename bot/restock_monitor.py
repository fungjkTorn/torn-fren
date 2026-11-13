"""Conservative, opt-in observed stock threshold notifications.

Scans only the local collector database in read-only mode. Never announces a
predicted restock, an in-stock increase, or a baseline state as a new event.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

THRESHOLD = 30
MAX_EVENT_AGE_SECONDS = 180
MAX_BATCH = 5000


class StockAlertMonitor:
    def __init__(self, db_path, state_path, watched_items, *, clock=time.time):
        self.db_path = Path(db_path)
        self.state_path = Path(state_path)
        self.watched_items = {item.casefold().strip() for item in watched_items}
        self.clock = clock

    def _connect(self):
        db = sqlite3.connect(self.db_path.resolve(strict=True).as_uri() + "?mode=ro", uri=True, timeout=3)
        db.execute("PRAGMA query_only=ON")
        return db

    @staticmethod
    def _fresh(now, timestamp):
        return type(timestamp) is int and -15 <= now - timestamp <= MAX_EVENT_AGE_SECONDS

    def _write_state(self, state):
        if self.state_path.is_symlink():
            raise ValueError("refuse symlinked alert cursor")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".alert-cursor-", dir=self.state_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.state_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def _baseline(self, db):
        cursor = db.execute("SELECT COALESCE(MAX(id), 0) FROM stock_history").fetchone()[0]
        rows = db.execute("""
            SELECT sh.country, sh.item_name, sh.quantity
            FROM stock_history sh JOIN (
                SELECT country, item_name, MAX(id) AS latest_id
                FROM stock_history GROUP BY country, item_name
            ) latest ON sh.id = latest.latest_id
        """).fetchall()
        state = {
            "schema_version": 1,
            "cursor": cursor,
            "quantities": {f"{country}:{item}".casefold(): qty for country, item, qty in rows},
        }
        self._write_state(state)
        return []

    def _country_freshness(self, db, now, countries):
        found = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='country_stock_observations'"
        ).fetchone()
        if not found:
            return set()
        fresh = set()
        for country in countries:
            receipt = db.execute("""
                SELECT received_epoch, country_update_epoch, clock_status
                FROM country_stock_observations
                WHERE country=? ORDER BY received_epoch DESC, id DESC LIMIT 1
            """, (country,)).fetchone()
            if (receipt and receipt[2] == "REPORTED"
                    and self._fresh(now, receipt[0]) and self._fresh(now, receipt[1])):
                fresh.add(country)
        return fresh

    def scan(self):
        """Returns at-most-once candidate threshold crossings.

        The durable cursor advances before sending messages to avoid duplicates
        after reconnects. Discord delivery is best-effort, not guaranteed.
        """
        now = int(self.clock())
        with self._connect() as db:
            if not self.state_path.exists():
                return self._baseline(db)
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                if (state.get("schema_version") != 1
                        or type(state.get("cursor")) is not int
                        or not isinstance(state.get("quantities"), dict)):
                    return self._baseline(db)
            except (ValueError, OSError, TypeError):
                return self._baseline(db)
            rows = db.execute("""
                SELECT id, timestamp, country, item_name, quantity, source
                FROM stock_history WHERE id>? ORDER BY id LIMIT ?
            """, (state["cursor"], MAX_BATCH + 1)).fetchall()
            if len(rows) > MAX_BATCH:
                # Never send delayed, truncated, or potentially misidentified events.
                return self._baseline(db)
            if not rows:
                return []
            latest_heartbeat = db.execute("""
                SELECT MAX(timestamp) FROM poll_heartbeats
                WHERE success=1 AND mode='poll-cycle'
            """).fetchone()[0]
            fresh_countries = (self._country_freshness(db, now, {r[2] for r in rows})
                               if self._fresh(now, latest_heartbeat) else set())
            quantities = state["quantities"]
            candidates = []
            for event_id, stamp, country, item, qty, source in rows:
                key = f"{country}:{item}".casefold()
                prev = quantities.get(key)
                if (key in self.watched_items or "*" in self.watched_items):
                    if (type(prev) is int and prev <= THRESHOLD
                            and type(qty) is int and qty > THRESHOLD
                            and self._fresh(now, stamp) and country in fresh_countries):
                        candidates.append({
                            "event_id": event_id, "key": key, "item": item,
                            "country": country, "quantity": qty,
                            "observed_epoch": stamp, "source": source,
                        })
                quantities[key] = qty
            state["cursor"] = rows[-1][0]
            self._write_state(state)
            return candidates
