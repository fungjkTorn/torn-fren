"""Safety regression for long collector gaps: durable queue and no fake scores."""
import sqlite3
import tempfile
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

    def test_gap_notification_does_not_run_historical_validation(self):
        with patch.object(poller,"gap_recovery_pending") as backlog:
            info=poller._schedule_gap_recovery(100,400)
            self.assertEqual(info["status"],"ENQUEUED")
            backlog.assert_not_called()

    def test_crash_does_not_erase_claimed_work(self):
        enqueue(100,400,connect=self.connect)
        def killed(*args,**kwargs):
            raise KeyboardInterrupt("simulated hard stop")
        with self.assertRaises(KeyboardInterrupt):
            process_one(connect=self.connect,invalidator=killed,now=500)
        self.assertEqual(pending(connect=self.connect,now=501),
                         {"pending":1,"ready":0})
        completed=process_one(connect=self.connect,
                              invalidator=lambda *a,**kw:2,now=801)
        self.assertEqual(completed["status"],"COMPLETED")
        with self.connect() as db:
            status,attempts=db.execute(
                "SELECT status,attempts FROM forecast_recovery_jobs_v38"
            ).fetchone()
        self.assertEqual((status,attempts),("done",2))

    def test_recovery_systemd_process_is_isolated_and_bounded(self):
        root=Path(__file__).resolve().parents[1]
        service=(root/"deploy/systemd/torn-fren-gap-recovery.service").read_text()
        timer=(root/"deploy/systemd/torn-fren-gap-recovery.timer").read_text()
        self.assertIn("CPUQuota=50%",service)
        self.assertIn("MemoryMax=768M",service)
        self.assertIn("TimeoutStartSec=180",service)
        self.assertIn("Nice=15",service)
        self.assertIn("research.v38_gap_recovery --once",service)
        self.assertIn("ReadWritePaths=/opt/torn-fren/data",service)
        self.assertIn("torn-fren-gap-recovery.service",timer)
        import inspect
        source=inspect.getsource(poller.run)
        self.assertNotIn("invalidate_pending_forecasts_crossing_gap(",source)
        self.assertNotIn("_recovery_worker",source)
        self.assertNotIn("process_gap_recovery",source)


if __name__=="__main__":
    unittest.main()
