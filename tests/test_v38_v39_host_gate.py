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
        self.add("can","Wolverine Plushie","pending",10,9750)
        self.add("sou","Lion Plushie","pending",0,1000)
        result=self.read()
        self.assertEqual(result["status"],"AUDIT_QUEUE_PROGRESSING")
        self.assertEqual(result["queue"],{"done":1,"pending":2})
        self.assertEqual(result["last_completion_age_seconds"],50)
        self.assertEqual(result["oldest_high_priority_pending_age_seconds"],250)
        self.assertTrue(result["read_only"])

    def test_only_running_or_pending_never_pass(self):
        self.add("uni","Heather","running",10,9600)
        self.assertEqual(self.read()["reason"],"NO_COMPLETED_AUDITS_YET")

    def test_stale_processing_cannot_pass(self):
        self.add("uni","Heather","done",0,9000,9000)
        self.assertEqual(self.read()["reason"],"AUDIT_WORKER_NOT_COMPLETING_RECENTLY")

    def test_urgent_backlog_deferred_even_with_recent_completion(self):
        self.add("uni","Heather","done",0,9400,9900)
        self.add("uni","Nessie Plushie","pending",10,8500)
        self.assertEqual(self.read()["reason"],"URGENT_STOCK_AUDITS_TOO_OLD")

    def test_missing_and_corrupt_db_fail_without_creating_files(self):
        missing=self.path.parent/"missing.db"
        self.assertEqual(inspect(missing,now=self.NOW)["reason"],"AUDIT_QUEUE_UNREADABLE")
        self.assertFalse(missing.exists())
        with sqlite3.connect(self.path) as con:
            con.execute("DROP TABLE routine_audit_jobs_v39")
        self.assertEqual(self.read()["reason"],"AUDIT_QUEUE_UNREADABLE")


if __name__=="__main__":unittest.main()
