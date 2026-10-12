"""V134 original V2 graph archived restock outcomes without DB writes."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v134_original_graph_v2_audit as m

T0=(1790000000//3600)*3600


def fixture(path):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE forecast_audit_runs(
            id INTEGER PRIMARY KEY,
            country TEXT,item_name TEXT,created_at INTEGER,
            source TEXT,active_prediction_number INTEGER
        )""")
        db.execute("""CREATE TABLE forecast_audit_points(
            id INTEGER PRIMARY KEY,run_id INTEGER,
            prediction_number INTEGER,projection_depth INTEGER,
            status TEXT,ground_truth_valid INTEGER,
            window_hit INTEGER,arrival_hit INTEGER,
            absolute_error_seconds INTEGER,
            estimate_timestamp INTEGER,
            recommended_arrival_timestamp INTEGER,
            recommended_leave_by_timestamp INTEGER
        )""")
        db.executemany("INSERT INTO forecast_audit_runs VALUES (?,?,?,?,?,?)",[
            (1,"uni","Nessie Plushie",T0,"live",1),
            (2,"uni","Nessie Plushie",T0+300,"live",1),
            (3,"uni","Nessie Plushie",T0+3600,"live",1),
            (4,"mex","Jaguar Plushie",T0,"live",1),
            (5,"uni","Nessie Plushie",T0+7200,"live",1),
        ])
        db.executemany(
            "INSERT INTO forecast_audit_points VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (1,1,1,0,"resolved",1,1,1,120,T0+5000,T0+5400,T0+300),
                (2,2,1,1,"resolved",1,0,0,1500,T0+5500,T0+5800,T0+600),
                (3,3,1,1,"pending",None,None,None,None,T0+9000,T0+9300,T0+3700),
                (4,4,1,2,"resolved",0,1,1,10,T0+7000,T0+7300,T0+300),
                (5,5,1,1,"resolved",1,0,0,2400,T0+12300,T0+12500,T0+7500),
            ]
        )
        db.commit()


class OriginalV2AuditTests(unittest.TestCase):
    def test_first_hour_and_missing_or_invalid_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector=Path(tmp)/"stock.db"
            fixture(collector)
            result=m.audit(collector=collector,asof=T0+14000,days=1)
            self.assertTrue(result["read_only"])
            self.assertEqual(result["status"],
                "V134_ORIGINAL_GRAPH_PREDICTION_V2_RECORDED_AUDIT")
            # First Nessie per hour + Jaguar first in same hour.
            self.assertEqual(result["24_item_first_issued_active_UTC_hours"],4)
            overall=result["overall"]
            self.assertEqual(overall["resolved_valid_target_cycles"],2)
            self.assertEqual(overall["restock_window_hit"],1)
            self.assertEqual(overall["restock_window_miss"],1)
            self.assertEqual(overall["pending_or_unresolved"],1)
            self.assertEqual(overall["resolved_but_invalid_observation"],1)
            self.assertEqual(overall["arrival_inside_target_restock_to_depletion_period"],1)
            self.assertEqual(overall["arrival_outside_target_restock_to_depletion_period"],1)
            self.assertTrue(result["restock_hit_is_not_same_as_30_stock_on_arrival"])
            self.assertEqual(len(result["per_item"]),24)

    def test_no_table_is_not_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector=Path(tmp)/"stock.db"
            with sqlite3.connect(collector) as db:
                db.execute("CREATE TABLE stock_history(dummy INTEGER)")
                db.commit()
            result=m.audit(collector=collector,asof=T0,days=1)
            self.assertEqual(result["status"],
                "ORIGINAL_V2_FORECAST_AUDIT_TABLES_NOT_PRESENT")
            with sqlite3.connect(collector) as db:
                t={x[0] for x in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(t,{"stock_history"})

    def test_bounded_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector=Path(tmp)/"stock.db"
            fixture(collector)
            with self.assertRaisesRegex(ValueError,"too many archived"):
                m.audit(collector=collector,asof=T0+14000,
                        days=1,limit=1)

    def test_original_stored_arrival_label_not_poll_stock_proxy(self):
        points=[
            dict(status="resolved",ground_truth_valid=1,
                 window_hit=1,arrival_hit=1,absolute_error_seconds=60),
            dict(status="resolved",ground_truth_valid=1,
                 window_hit=0,arrival_hit=None,absolute_error_seconds=300),
        ]
        s=m._stats(points)
        self.assertEqual(s["resolved_valid_target_cycles"],2)
        self.assertEqual(s["cycle_arrival_scorable"],1)
        self.assertTrue(s["arrival_hit_is_not_persisted_threshold_30_stock_truth"])
        self.assertAlmostEqual(s["mean_absolute_restock_error_minutes"],3)


if __name__=="__main__":
    unittest.main()
