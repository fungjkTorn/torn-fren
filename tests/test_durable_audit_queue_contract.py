"""Isolated regression checks for the production durable stock-audit queue."""
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class DurableAuditQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"audit.db"
        with sqlite3.connect(self.db) as con:
            pass
        self.fake_hs=types.ModuleType("services.history_service")
        self.fake_hs._connect=lambda: sqlite3.connect(self.db)
        self.fake_hs.init_db=lambda: None
        fake_services=types.ModuleType("services")
        fake_services.__path__=[str(ROOT/'services')]
        fake_services.history_service=self.fake_hs
        patcher=patch.dict(sys.modules,{"services":fake_services,"services.history_service":self.fake_hs})
        patcher.start();self.addCleanup(patcher.stop)
        spec=importlib.util.spec_from_file_location("durable_under_test", ROOT/'services'/'durable_audit_queue_v39.py')
        self.queue=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.queue)
        with sqlite3.connect(self.db) as con:self.queue.ensure_schema(con)

    def _row(self):
        with sqlite3.connect(self.db) as con:
            return con.execute("SELECT generation,priority,status,next_due_at,lease_until FROM routine_audit_jobs_v39 WHERE country='can' AND item_name='Wolverine Plushie'").fetchone()

    def test_coalesces_canary_stock_transitions(self):
        with sqlite3.connect(self.db) as con:
            self.queue.enqueue(con,'can','Wolverine Plushie',1000)
            self.queue.enqueue(con,'can','Wolverine Plushie',1030)
        generation,priority,status,due,lease=self._row()
        self.assertEqual((generation,priority,status,due,lease),(2,100,'pending',0,0))

    def test_new_stock_update_supersedes_running_audit(self):
        with sqlite3.connect(self.db) as con:
            self.queue.enqueue(con,'can','Wolverine Plushie',1000)
        job=self.queue.claim(1001)
        self.assertEqual(job['generation'],1)
        with sqlite3.connect(self.db) as con:
            self.queue.enqueue(con,'can','Wolverine Plushie',1002)
        self.assertFalse(self.queue.finish(job,now=1003))
        self.assertEqual(self._row()[0],2)
        self.assertEqual(self._row()[2],'pending')
        second=self.queue.claim(1004)
        self.assertEqual(second['generation'],2)
        self.assertTrue(self.queue.finish(second,now=1005))
        self.assertEqual(self._row()[2],'done')

    def test_failures_remain_retryable(self):
        with sqlite3.connect(self.db) as con:
            self.queue.enqueue(con,'can','Wolverine Plushie',1000)
        job=self.queue.claim(1001)
        self.assertTrue(self.queue.finish(job,error='test',now=1002))
        self.assertEqual(self._row()[2],'pending')
        self.assertGreater(self._row()[3],1002)
        self.assertIsNone(self.queue.claim(1003))
        self.assertEqual(self.queue.claim(1033)['generation'],1)

if __name__=='__main__':unittest.main()
