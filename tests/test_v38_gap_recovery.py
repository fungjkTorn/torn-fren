"""Safety regression for long collector gaps: durable queue and no fake scores."""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import poller
from research.v38_gap_recovery import enqueue, pending, process_one


class GapQueueTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"source.db"

    def connect(self):
        return sqlite3.connect(self.path)

    def test_enqueue_unique_process_and_idempotent_redrain(self):
        enqueue(100,400,connect=self.connect)
        enqueue(100,400,connect=self.connect)
        self.assertEqual(pending(connect=self.connect,now=450),
                         {"pending":1,"ready":1})
        inv=Mock(return_value=39)
        result=process_one(connect=self.connect,invalidator=inv,now=450)
        self.assertEqual(result["status"],"COMPLETED")
        self.assertEqual(result["invalidated_count"],39)
        inv.assert_called_once_with(100,400,reason="collector heartbeat recovery gap")
        self.assertEqual(pending(connect=self.connect,now=450),
                         {"pending":0,"ready":0})
        self.assertEqual(process_one(connect=self.connect,invalidator=inv,now=450)
                         ["status"],"NO_DUE_GAPS")
        inv.assert_called_once()
        with self.connect() as db:
            n=db.execute("SELECT COUNT(*) FROM forecast_recovery_jobs_v38").fetchone()[0]
            self.assertEqual(n,1)

    def test_failure_remains_durable_with_backoff_after_restart(self):
        enqueue(100,400,connect=self.connect)
        def unavailable(*args,**kwargs):
            raise RuntimeError("temporary lock")
        failed=process_one(connect=self.connect,invalidator=unavailable,now=500)
        self.assertEqual(failed["status"],"RETRY_SCHEDULED")
        self.assertEqual(pending(connect=self.connect,now=501),
                         {"pending":1,"ready":0})
        self.assertEqual(process_one(connect=self.connect,now=501)
                         ["status"],"NO_DUE_GAPS")
        succeeded=process_one(connect=self.connect,invalidator=lambda *a,**kw:2,
                              now=800)
        self.assertEqual(succeeded["status"],"COMPLETED")
        self.assertEqual(pending(connect=self.connect,now=801)
                         ["pending"],0)
        with self.connect() as db:
            row=db.execute("SELECT attempts,status,invalidated_count FROM forecast_recovery_jobs_v38").fetchone()
            self.assertEqual(row,(2,"done",2))

    def test_invalid_enqueues_rejected_without_creating_files(self):
        for start,end in [(0,5),(5,5),(10,9)]:
            with self.assertRaises(ValueError):
                enqueue(start,end,connect=self.connect)
        self.assertFalse(self.path.exists())

    def test_poller_schedule_never_invokes_expensive_auditor(self):
        with patch.object(poller,"enqueue_gap_recovery",
                          return_value={"status":"ENQUEUED",
                                        "gap_start":100,"gap_end":400}) as write:
            with patch.object(poller,"_RECOVERY_EVENT",threading.Event()) as evt:
                self.assertEqual(poller._schedule_gap_recovery(100,400)
                                 ["status"],"ENQUEUED")
                write.assert_called_once_with(100,400)
                self.assertTrue(evt.is_set())

    def test_poller_recovery_thread_records_job_and_keeps_running(self):
        event=threading.Event()
        stop=threading.Event()
        with patch.object(poller,"_RECOVERY_EVENT",event):
            with patch.object(poller,"_RECOVERY_STOP",stop):
                with patch.object(poller,"process_gap_recovery",
                    side_effect=[{"status":"COMPLETED","gap_start":100,
                                  "gap_end":400,"invalidated_count":39},
                                 {"status":"NO_DUE_GAPS"}]) as process:
                    t=threading.Thread(target=poller._recovery_worker,daemon=True)
                    t.start()
                    import time
                    deadline=time.monotonic()+2
                    while process.call_count<2 and time.monotonic()<deadline:
                        time.sleep(0.005)
                    stop.set()
                    event.set()
                    t.join(2)
                    self.assertFalse(t.is_alive())
                    self.assertGreaterEqual(process.call_count,2)


if __name__=="__main__":
    unittest.main()
