"""Research-only proof of gap-reconciliation parity and O(1) heartbeat path."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import history_service as hs


class IncrementalHeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "stock.db"
        self.con = sqlite3.connect(self.db)
        self.addCleanup(self.con.close)
        self.con.executescript("""
            CREATE TABLE poll_heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,source TEXT NOT NULL,
                success INTEGER NOT NULL,error TEXT,mode TEXT
            );
            CREATE TABLE collection_gaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_timestamp INTEGER NOT NULL,
                end_timestamp INTEGER,
                reason TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                closed_at INTEGER,
                UNIQUE(start_timestamp,reason)
            );
            CREATE INDEX idx_poll_heartbeats_timestamp
                ON poll_heartbeats(timestamp);
        """)
        self.con.commit()

    def _record(self, stamp, success=True):
        with patch.object(hs, "init_db", lambda: None):
            with patch.object(hs, "_connect",
                              lambda: sqlite3.connect(self.db)):
                with patch.object(hs.time, "time", return_value=stamp):
                    return hs.record_poll_heartbeat(success,"test")

    def test_gap_boundaries_and_no_false_gaps(self):
        self._record(1000)
        self._record(1030)
        third=self._record(1250)
        self.assertTrue(third["recovered_from_gap"])
        self.assertEqual(third["gap_start_timestamp"],1030)
        self.assertEqual(third["gap_end_timestamp"],1250)
        self._record(1280,False)
        last=self._record(1310)
        self.assertFalse(last["recovered_from_gap"])
        rows=self.con.execute("""
            SELECT start_timestamp,end_timestamp,reason,created_at,closed_at
            FROM collection_gaps ORDER BY start_timestamp
        """).fetchall()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][:2],(1030,1250))
        self.assertIn("220s",rows[0][2])

    def test_latest_gap_matches_full_legacy_sweep(self):
        for t in (1000,1030,1300,1330,1550,1580):
            self._record(t)
        before=self.con.execute("""
            SELECT start_timestamp,end_timestamp,reason
            FROM collection_gaps ORDER BY start_timestamp
        """).fetchall()
        with self.con:
            hs._reconcile_heartbeat_collection_gaps_conn(self.con)
        after=self.con.execute("""
            SELECT start_timestamp,end_timestamp,reason
            FROM collection_gaps ORDER BY start_timestamp
        """).fetchall()
        self.assertEqual(before,after)
        self.assertEqual(len(before),2)

    def test_normal_poll_no_full_success_history_scan(self):
        # Stress the original workload shape using 20,000 historical successes.
        self.con.executemany("""
            INSERT INTO poll_heartbeats(timestamp,source,success,mode)
            VALUES(?,'test',1,'poll-cycle')
        """,[(1000+30*i,) for i in range(20000)])
        self.con.commit()
        statements=[]
        real_connect=sqlite3.connect
        def observed_connect():
            c=real_connect(self.db)
            c.set_trace_callback(statements.append)
            return c
        with patch.object(hs,"init_db",lambda:None):
            with patch.object(hs,"_connect",observed_connect):
                with patch.object(hs.time,"time",return_value=601030):
                    hs.record_poll_heartbeat(True,"test")
        queries="\n".join(statements).lower()
        self.assertFalse(any("from poll_heartbeats" in s.lower()
                             and "success = 1" in s.lower()
                             and "order by timestamp asc" in s.lower()
                             for s in statements))
        self.assertNotIn("select timestamp\n        from poll_heartbeats\n        where mode = 'poll-cycle'\n          and success = 1\n        order by timestamp asc",queries)
        count=self.con.execute("SELECT COUNT(*) FROM poll_heartbeats").fetchone()[0]
        self.assertEqual(count,20001)

    def test_legacy_history_scan_is_throttled_but_failure_immediate(self):
        tick=[100.0]
        with patch.object(hs,"_LEGACY_GAP_LAST_CHECK_MONOTONIC",None):
            with patch.object(hs.time,"monotonic",side_effect=lambda:tick[0]):
                with patch.object(hs,"_reconcile_known_collection_gaps_conn") as full:
                    self._record(1000)
                    self.assertEqual(full.call_count,1)
                    tick[0]=120.0
                    self._record(1030)
                    self.assertEqual(full.call_count,1)
                    tick[0]=140.0
                    self._record(1060,False)
                    self.assertEqual(full.call_count,2)
                    tick[0]=141.0
                    self._record(1090)
                    self.assertEqual(full.call_count,2)
                    tick[0]=742.0
                    self._record(1120)
                    self.assertEqual(full.call_count,3)

    def test_manual_full_history_recovery_still_works(self):
        self.con.executemany("""
            INSERT INTO poll_heartbeats(timestamp,source,success,mode)
            VALUES(?,'test',1,'poll-cycle')
        """,[(1000,),(1500,),(1530,)])
        with self.con:
            hs._reconcile_heartbeat_collection_gaps_conn(self.con)
        row=self.con.execute("""
            SELECT start_timestamp,end_timestamp FROM collection_gaps
        """).fetchone()
        self.assertEqual(row,(1000,1500))


if __name__=="__main__":
    unittest.main()
