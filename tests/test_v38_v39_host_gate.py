"""V39 queue admission tests; operate only on disposable read-only DB."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v38_v39_host_gate import inspect


class AuditQueueHostGateTests(unittest.TestCase):
    NOW = 10000

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"stock.db"
        with sqlite3.connect(self.path) as con:
            con.execute("""
                CREATE TABLE routine_audit_jobs_v39(
                    country TEXT,item_name TEXT,
                    priority INTEGER,status TEXT,
                    queued_at INTEGER,last_finished_at INTEGER)
            """)

    def add(self,c,i,status,priority,queued,finished=None):
        with sqlite3.connect(self.path) as con:
            con.execute("""
                INSERT INTO routine_audit_jobs_v39 VALUES(?,?,?,?,?,?)
            """,(c,i,priority,status,queued,finished))

    def read(self):
        return inspect(self.path,now=self.NOW)

    def test_allows_live_pending_with_recently_finished_work(self):
        self.add("uni","Heather","done",0,9500,9950)
        self.add("can","Wolverine Plushie","pending",100,9750)
        self.add("sou","Lion Plushie","pending",0,1000)
        result=self.read()
        self.assertEqual(result["status"],"AUDIT_QUEUE_PROGRESSING")
        self.assertEqual(result["queue"],{"done":1,"pending":2})
        self.assertEqual(result["last_completion_age_seconds"],50)
        self.assertEqual(result["oldest_high_priority_pending_age_seconds"],250)
        self.assertTrue(result["read_only"])

    def test_only_running_or_pending_never_pass(self):
        self.add("uni","Heather","running",100,9600)
        self.assertEqual(self.read()["reason"],"NO_COMPLETED_AUDITS_YET")

    def test_stale_processing_cannot_pass(self):
        self.add("uni","Heather","done",0,9000,9000)
        self.assertEqual(self.read()["reason"],"AUDIT_WORKER_NOT_COMPLETING_RECENTLY")

    def test_urgent_backlog_is_reported_but_does_not_block_independent_shadow(self):
        self.add("uni","Heather","done",0,9400,9900)
        self.add("uni","Nessie Plushie","pending",100,8500)
        result=self.read()
        self.assertEqual(result["status"],"AUDIT_QUEUE_PROGRESSING")
        self.assertIsNone(result["reason"])
        self.assertEqual(result["oldest_high_priority_pending_age_seconds"],1500)
        self.assertEqual(result["warnings"],["URGENT_STOCK_AUDITS_LAGGING"])

    def test_real_world_large_old_urgent_backlog_with_recent_liveness(self):
        # 1 -> 6 done rows in VM logs while 12 queued priority=100 and
        # 381 others remain pending; graph-only queue is not shadow input.
        self.add("jap","Xanax","running",100,7000)
        self.add("uni","Heather","pending",100,7000)
        self.add("uni","Nessie Plushie","done",0,7500,9940)
        for i in range(40):
            self.add("mex",f"Catalog item {i}","pending",10,6900)
        result=self.read()
        self.assertEqual(result["status"],"AUDIT_QUEUE_PROGRESSING")
        self.assertEqual(result["last_completion_age_seconds"],60)
        self.assertGreater(result["oldest_high_priority_pending_age_seconds"],1200)
        self.assertIn("URGENT_STOCK_AUDITS_LAGGING",result["warnings"])

    def test_large_old_general_backlog_does_not_block_new_canary(self):
        self.add("uni","Heather","done",0,9000,9950)
        self.add("uni","Nessie Plushie","pending",100,9900)
        for i in range(40):
            self.add("mex",f"Catalog item {i}","pending",10,1000)
        result=self.read()
        self.assertEqual(result["status"],"AUDIT_QUEUE_PROGRESSING")
        self.assertEqual(result["oldest_high_priority_pending_age_seconds"],100)
        self.assertEqual(result["oldest_general_pending_age_seconds"],9000)

    def test_requeued_finished_item_still_proves_worker_made_progress(self):
        self.add("uni","Heather","pending",100,9750,9990)
        result=self.read()
        self.assertEqual(result["completed_count"],0)
        self.assertEqual(result["status"],"AUDIT_QUEUE_PROGRESSING")
        self.assertEqual(result["last_completion_age_seconds"],10)

    def test_missing_and_corrupt_db_fail_without_creating_files(self):
        missing=self.path.parent/"missing.db"
        self.assertEqual(inspect(missing,now=self.NOW)["reason"],"AUDIT_QUEUE_UNREADABLE")
        self.assertFalse(missing.exists())
        with sqlite3.connect(self.path) as con:
            con.execute("DROP TABLE routine_audit_jobs_v39")
        self.assertEqual(self.read()["reason"],"AUDIT_QUEUE_UNREADABLE")


if __name__=="__main__":unittest.main()
