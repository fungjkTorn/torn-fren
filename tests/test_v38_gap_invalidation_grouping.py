"""Recovery invalidation computes source continuity once per unique item."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services import forecast_auditor


class InvalidationGroupTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/"audits.db"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE forecast_audit_runs(
                    id INTEGER PRIMARY KEY,
                    country TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE forecast_audit_points(
                    id INTEGER PRIMARY KEY,
                    run_id INTEGER,
                    status TEXT NOT NULL,
                    ground_truth_valid INTEGER,
                    validation_reason TEXT,
                    resolved_at INTEGER
                );
            """)
            for rid in range(1,82):
                country,item=("uni","Heather") if rid<81 else ("jap","Xanax")
                db.execute("INSERT INTO forecast_audit_runs VALUES(?,?,?,?)",
                           (rid,country,item,100))
                db.execute("INSERT INTO forecast_audit_points (run_id,status) VALUES(?,'pending')",
                           (rid,))
            db.execute("INSERT INTO forecast_audit_runs VALUES(90,'uni','Heather',500)")
            db.execute("INSERT INTO forecast_audit_points(run_id,status) VALUES(90,'pending')")

    def connect(self):
        return sqlite3.connect(self.path)

    def test_one_continuity_check_per_item_with_all_pending_runs_updated(self):
        def continuity(country,item,start,end):
            return {"valid":item=="Xanax",
                    "reason":"ambiguous outage",
                    "max_gap_seconds":end-start}
        checks=Mock(side_effect=continuity)
        with patch.object(forecast_auditor,"ensure_forecast_audit_schema"):
            with patch.object(forecast_auditor,"_connect",self.connect):
                with patch.object(forecast_auditor,
                                  "_interval_gaps_preserve_item_cycle",checks):
                    changed=forecast_auditor.invalidate_pending_forecasts_crossing_gap(
                        200,400)
        self.assertEqual(changed,80)
        self.assertEqual(checks.call_count,2)
        with self.connect() as db:
            totals=db.execute("""
              SELECT status,COUNT(*) FROM forecast_audit_points
              GROUP BY status
            """).fetchall()
        self.assertEqual(dict(totals),{"invalidated":80,"pending":2})

    def test_idempotency_after_interrupted_job(self):
        with patch.object(forecast_auditor,"ensure_forecast_audit_schema"):
            with patch.object(forecast_auditor,"_connect",self.connect):
                with patch.object(forecast_auditor,
                    "_interval_gaps_preserve_item_cycle",
                    return_value={"valid":False,"reason":"unsafe"}):
                    once=forecast_auditor.invalidate_pending_forecasts_crossing_gap(200,400)
                    twice=forecast_auditor.invalidate_pending_forecasts_crossing_gap(200,400)
        self.assertEqual(once,81)
        self.assertEqual(twice,0)


if __name__=="__main__":
    unittest.main()
