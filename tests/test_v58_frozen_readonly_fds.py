"""V58 regression: close every frozen read connection; Red Fox never reads ahead."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import history_service
from services.frozen_candidate_worker_v31 import _install_frozen_readonly_history
from research import v38_red_fox_single_tick as red

NOW=1791540300


class V58ReadOnlySourceSafetyTests(unittest.TestCase):
    def test_patched_history_with_block_really_closes_database(self):
        """sqlite3's normal context manager *does not* close; the patched one must."""
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"frozen.db"
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE stock_history(timestamp INTEGER)")
                c.execute("INSERT INTO stock_history VALUES(?)",(NOW,))
                c.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT)")
            with (
                patch.object(history_service,"DB_PATH"),
                patch.object(history_service,"_connect"),
                patch.object(history_service,"init_db"),
                patch.object(history_service,"_DB_READY"),
            ):
                _install_frozen_readonly_history(history_service,db)
                con=history_service._connect()
                with con as cursor:
                    self.assertEqual(cursor.execute(
                        "SELECT MAX(timestamp) FROM stock_history"
                    ).fetchone()[0],NOW)
                    self.assertEqual(cursor.execute(
                        "PRAGMA query_only").fetchone()[0],1)
                    with self.assertRaises(sqlite3.OperationalError):
                        cursor.execute("CREATE TABLE illegal_write(x INTEGER)")
                # Regression: with sqlite3.connect(...) usually leaves the
                # connection OPEN. Closing subclass must refuse any SQL here.
                with self.assertRaises(sqlite3.ProgrammingError):
                    con.execute("SELECT 1")
                for _ in range(80):
                    with history_service._connect() as cursor:
                        self.assertEqual(cursor.execute(
                            "SELECT 1").fetchone()[0],1)
                # A real history-service read traverses the adapter and its
                # nested "with" without needing any write privileges.
                self.assertEqual(history_service.get_collection_gaps(),[])
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute(
                    "SELECT count(*) FROM stock_history").fetchone()[0],1)

    def test_original_history_connect_and_schema_init_restored(self):
        original=(history_service.DB_PATH,history_service._connect,
                  history_service.init_db,history_service._DB_READY)
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"frozen.db"
            with sqlite3.connect(db) as c:
                c.execute("CREATE TABLE stock_history(x INTEGER)")
            with (
                patch.object(history_service,"DB_PATH"),
                patch.object(history_service,"_connect"),
                patch.object(history_service,"init_db"),
                patch.object(history_service,"_DB_READY"),
            ):
                _install_frozen_readonly_history(history_service,db)
                self.assertEqual(history_service.DB_PATH,db)
                self.assertTrue(history_service._DB_READY)
        self.assertEqual((history_service.DB_PATH,history_service._connect,
                          history_service.init_db,history_service._DB_READY),
                         original)

    def test_redfox_interleaved_collector_append_is_nonactionable_abstention(self):
        with patch.object(red,"inspect_live_source",
                          return_value={"status":"FRESH"}):
            with patch.object(red.ResearchContext,"build",
                side_effect=ValueError("future stock rows relative to requested as-of")
            ) as build:
                with patch.object(red,"AnalogPlanner") as planner:
                    result=red.predict("unused","uni","Red Fox Plushie",NOW)
        self.assertEqual(result,{"status":"SOURCE_ADVANCED_DURING_TICK"})
        build.assert_called_once_with("unused",asof=NOW,readonly=True)
        planner.assert_not_called()
        self.assertNotIn("recommended_departure_timestamp",result)

    def test_redfox_other_value_errors_still_fail_closed(self):
        with patch.object(red,"inspect_live_source",return_value={"status":"FRESH"}):
            with patch.object(red.ResearchContext,"build",
                              side_effect=ValueError("invalid feature array")):
                with self.assertRaisesRegex(ValueError,"invalid feature"):
                    red.predict("unused","uni","Red Fox Plushie",NOW)

    def test_redfox_unverified_source_never_builds_context(self):
        with patch.object(red,"inspect_live_source",
                          return_value={"status":"COLLECTOR_STALE_OR_NO_HEARTBEAT"}):
            with patch.object(red.ResearchContext,"build") as builder:
                result=red.predict("unused","uni","Red Fox Plushie",NOW)
        self.assertEqual(result["status"],"COLLECTOR_STALE_OR_NO_HEARTBEAT")
        builder.assert_not_called()


if __name__=="__main__":
    unittest.main()
