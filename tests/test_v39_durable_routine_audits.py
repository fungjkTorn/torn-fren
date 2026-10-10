"""Verify routine audits never run in poller, and event queue survives crashes.

Tests use disposable SQLite only. No network, production data or service ops.
"""
from __future__ import annotations
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import history_service as hs
from services import durable_audit_queue_v39 as q


class DurableAuditTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"collector.db"
        for attribute,value in (("DB_PATH",self.path),("_DB_READY",False)):
            self.addCleanup(patch.stopall)
        self.path_patch=patch.object(hs,"DB_PATH",self.path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.ready_patch=patch.object(hs,"_DB_READY",False)
        self.ready_patch.start()
        self.addCleanup(self.ready_patch.stop)
        hs.init_db()

    def test_quantity_change_and_queue_update_are_atomic(self):
        x={"stocks":[{"id":7,"name":"Heather","quantity":30,"cost":50}]}
        self.assertEqual(hs.save_snapshot_from_export("uni",x,"yata"),["Heather"])
        with hs._connect() as db:
            job=db.execute("""
              SELECT country,item_name,generation,status
              FROM routine_audit_jobs_v39
            """).fetchone()
        self.assertEqual(job,("uni","Heather",1,"pending"))
        # Price-only update is persisted but never queues a new forecast.
        x["stocks"][0]["cost"]=60
        self.assertEqual(hs.save_snapshot_from_export("uni",x,"yata"),[])
        with hs._connect() as db:
            rev=db.execute("SELECT generation FROM routine_audit_jobs_v39").fetchone()[0]
            rows=db.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0]
        self.assertEqual((rev,rows),(1,2))
        # An item quantity transition creates next generation.
        x["stocks"][0]["quantity"]=0
        self.assertEqual(hs.save_snapshot_from_export("uni",x,"yata"),["Heather"])
        with hs._connect() as db:
            self.assertEqual(db.execute(
                "SELECT generation FROM routine_audit_jobs_v39"
            ).fetchone()[0],2)

    def test_recovery_of_expired_lease_and_retry(self):
        with hs._connect() as con:
            q.enqueue(con,"can","Wolverine Plushie",now=100)
        claimed=q.claim(now=110,lease_seconds=30)
        self.assertEqual(claimed["attempts"],1)
        self.assertIsNone(q.claim(now=120))
        replay=q.claim(now=141,lease_seconds=30)
        self.assertEqual(replay["attempts"],2)
        self.assertTrue(q.finish(replay,error="artificial failure",now=142))
        self.assertIsNone(q.claim(now=201))
        recovered=q.claim(now=203,lease_seconds=30)
        self.assertEqual(recovered["attempts"],3)
        self.assertTrue(q.finish(recovered,now=205))
        self.assertEqual(q.status(),{"done":1})

    def test_new_stock_during_work_cannot_be_lost(self):
        with hs._connect() as con:
            q.enqueue(con,"uni","Heather",now=100)
        original=q.claim(now=101,lease_seconds=100)
        with hs._connect() as con:
            q.enqueue(con,"uni","Heather",now=102)
        self.assertFalse(q.finish(original,now=103))
        latest=q.claim(now=104)
        self.assertEqual(latest["generation"],2)
        self.assertTrue(q.finish(latest,now=105))
        self.assertEqual(q.status(),{"done":1})

    def test_rollback_stock_change_rolls_back_queue(self):
        with self.assertRaises(RuntimeError):
            with hs._connect() as con:
                con.execute("""INSERT INTO stock_history(timestamp,country,item_id,
                    item_name,quantity,cost,source) VALUES(1,'uni',3,'Heather',30,4,'yata')""")
                q.enqueue(con,"uni","Heather",now=1)
                raise RuntimeError("rolled back")
        with hs._connect() as con:
            count=con.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0]
            queued=con.execute("SELECT COUNT(*) FROM routine_audit_jobs_v39").fetchone()[0]
        self.assertEqual((count,queued),(0,0))

    def test_collector_import_does_not_import_prediction_engines_or_threads(self):
        source=(Path(__file__).parents[1]/"poller.py").read_text(encoding="utf-8")
        self.assertNotIn("threading.Thread(",source)
        self.assertNotIn("_run_item_audits",source)
        self.assertNotIn("build_live_prediction_v2",source)
        self.assertIn("save_all_snapshots(export)",source)

    def test_drain_refuses_recovery_backlog_before_claiming(self):
        with hs._connect() as con:
            q.enqueue(con,"uni","Heather",now=100)
        with patch("research.v38_gap_recovery.pending",return_value={"pending":1}):
            with patch("services.history_service.get_collector_recovery_status",
                       return_value={"stale":False}):
                result=q.drain(runner=lambda *_:self.fail("run despite recovery"))
        self.assertEqual(result["status"],"DEFERRED_RECOVERY_OR_STALE_COLLECTOR")
        self.assertEqual(q.status(),{"pending":1})

    def test_bootstrap_preserves_recent_changed_items_without_requeueing_old(self):
        x={"stocks":[{"id":7,"name":"Heather","quantity":30,"cost":50}]}
        hs.save_snapshot_from_export("uni",x,"yata")
        with patch("services.forecast_auditor.get_profiled_items",return_value=[]):
            with patch("services.forecast_auditor.get_tracked_items",return_value=[]):
                self.assertGreaterEqual(q.bootstrap(),1)
                self.assertEqual(q.bootstrap(),0)
        with hs._connect() as con:
            row=con.execute(
                "SELECT generation,status FROM routine_audit_jobs_v39"
            ).fetchone()
        self.assertEqual(row,(1,"pending"))

    def test_worker_drains_one_job_without_running_audit_in_poller(self):
        with hs._connect() as con:
            q.enqueue(con,"uni","Heather",now=100)
        with patch("research.v38_gap_recovery.pending",return_value={"pending":0}):
            with patch("services.history_service.get_collector_recovery_status",
                       return_value={"stale":False}):
                with patch.object(q,"bootstrap",return_value=0):
                    out=q.drain(max_jobs=1,
                        runner=lambda c,i:{"checked":(c,i)})
        self.assertEqual(out["results"][0]["status"],"COMPLETED")
        self.assertEqual(out["queue"],{"done":1})

    def test_same_priority_queues_oldest_first(self):
        with hs._connect() as con:
            q.enqueue(con,"mex","Jaguar Plushie",now=100)
            q.enqueue(con,"cay","Stingray Plushie",now=110)
        first=q.claim(now=120)
        self.assertEqual(first["item_name"],"Jaguar Plushie")
        q.finish(first,now=125)
        second=q.claim(now=130)
        self.assertEqual(second["item_name"],"Stingray Plushie")

    def test_frozen_canary_beats_older_catalog_backlog(self):
        with hs._connect() as con:
            q.enqueue(con,"mex","Jaguar Plushie",now=100)
            q.enqueue(con,"uni","Heather",now=200)
        first=q.claim(now=205)
        self.assertEqual((first["country"],first["item_name"]),("uni","Heather"))
        self.assertEqual(first["generation"],1)
        with hs._connect() as con:
            priority=con.execute("""
                SELECT priority FROM routine_audit_jobs_v39
                WHERE country='uni' AND item_name='Heather'
            """).fetchone()[0]
        self.assertEqual(priority,q.CANARY_PRIORITY)

    def test_repeated_change_does_not_make_waiting_job_new(self):
        with hs._connect() as con:
            q.enqueue(con,"mex","Jaguar Plushie",now=100)
            q.enqueue(con,"cay","Stingray Plushie",now=110)
            q.enqueue(con,"mex","Jaguar Plushie",now=120)
            row=con.execute("""
                SELECT queued_at,generation
                FROM routine_audit_jobs_v39
                WHERE country='mex' AND item_name='Jaguar Plushie'
            """).fetchone()
        self.assertEqual(row,(100,2))
        self.assertEqual(q.claim(now=121)["item_name"],"Jaguar Plushie")

    def test_completed_job_new_change_starts_new_queue_age(self):
        with hs._connect() as con:
            q.enqueue(con,"mex","Jaguar Plushie",now=100)
        job=q.claim(now=110)
        self.assertTrue(q.finish(job,now=115))
        with hs._connect() as con:
            q.enqueue(con,"mex","Jaguar Plushie",now=180)
            row=con.execute("""
                SELECT queued_at,generation
                FROM routine_audit_jobs_v39
                WHERE country='mex' AND item_name='Jaguar Plushie'
            """).fetchone()
        self.assertEqual(row,(180,2))

    def test_legacy_high_priority_items_promoted_without_loss(self):
        with hs._connect() as con:
            con.execute("""
                INSERT INTO routine_audit_jobs_v39(
                  country,item_name,queued_at,generation,priority,status
                ) VALUES('jap','Xanax',100,7,10,'pending')
            """)
            con.execute("""
                INSERT INTO routine_audit_jobs_v39(
                  country,item_name,queued_at,generation,priority,status
                ) VALUES('mex','Jaguar Plushie',90,3,10,'pending')
            """)
        self.assertEqual(q.promote_canary_pending(),1)
        self.assertEqual(q.promote_canary_pending(),0)
        with hs._connect() as con:
            rows=con.execute("""
                SELECT country,queued_at,generation,priority,status
                FROM routine_audit_jobs_v39 ORDER BY country
            """).fetchall()
        self.assertEqual(rows,[
            ("jap",100,7,100,"pending"),
            ("mex",90,3,10,"pending"),
        ])
        self.assertEqual(q.claim(now=150)["item_name"],"Xanax")

    def test_quota_and_timer_declared_without_full_model_rollout(self):
        root=Path(__file__).parents[1]
        service=(root/"deploy/systemd/torn-fren-routine-audit.service").read_text()
        timer=(root/"deploy/systemd/torn-fren-routine-audit.timer").read_text()
        self.assertIn("CPUQuota=35%",service)
        self.assertIn("MemoryMax=768M",service)
        self.assertIn("ReadWritePaths=/opt/torn-fren/data /var/lib/torn-fren",service)
        self.assertIn("services.durable_audit_queue_v39 --once",service)
        self.assertIn("OnCalendar=*-*-* *:*:00",timer)


if __name__=="__main__":
    unittest.main()
