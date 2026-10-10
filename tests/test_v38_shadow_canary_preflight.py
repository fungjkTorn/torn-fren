"""Dry-run V38 preflight must never touch production services or stock rows."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v38_shadow_canary_preflight import inspect


class CanaryPreflightTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db=Path(tmp.name)/"collector.db"
        with sqlite3.connect(self.db) as con:
            con.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER, mode TEXT, success INTEGER)")
            con.execute("CREATE TABLE stock_history(timestamp INTEGER)")
            con.execute("INSERT INTO stock_history VALUES(990)")
            con.execute("INSERT INTO poll_heartbeats VALUES(985,'poll-cycle',1)")
        self.now=1000

    def call(self,**kw):
        return inspect(self.db,now=self.now,cpu_slots=2,load1=0.5,**kw)

    def test_fresh_collector_with_quiet_stock_is_eligible(self):
        result=self.call()
        self.assertEqual(result["status"],"READY_FOR_BOUNDED_READONLY_PROBE")
        self.assertEqual(result["source"]["age_seconds"],15)
        self.assertEqual(result["source_pinned_worker_count"],16)
        self.assertEqual(result["flower_plushie_roster_count"],21)
        self.assertEqual(result["not_integrated_count"],5)
        self.assertEqual(len(result["first_five"]),5)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["services_changed"])

    def test_stale_or_future_collectors_fail_closed(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE poll_heartbeats SET timestamp=400")
        x=self.call()
        self.assertEqual(x["source"]["status"],"COLLECTOR_STALE")
        self.assertEqual(x["status"],"DEFER_PROBE")
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE poll_heartbeats SET timestamp=1200")
        self.assertEqual(self.call()["source"]["status"],"FUTURE_HEARTBEAT")

    def test_overloaded_vm_refuses_new_research(self):
        report=inspect(self.db,now=1000,cpu_slots=2,load1=3.0)
        self.assertEqual(report["status"],"DEFER_PROBE")
        self.assertFalse(report["capacity"]["headroom_ok"])

    def test_no_implicit_db_create(self):
        absent=self.db.parent/"does-not-exist.db"
        report=inspect(absent,now=1000,cpu_slots=2,load1=0.1)
        self.assertEqual(report["status"],"DEFER_PROBE")
        self.assertFalse(absent.exists())


if __name__=="__main__":unittest.main()
