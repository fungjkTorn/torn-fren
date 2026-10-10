"""V41 beta is sidecar-only, explicitly opt-in, and refuses stale actions."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from web.v41_champion_cache import read_snapshots
from web.app import api_v41_champion_predictions

NOW = 1800000000
CREATE = """CREATE TABLE latest_predictions(
    item_key TEXT PRIMARY KEY,model_family TEXT,model_config TEXT,status TEXT,
    computed_at INTEGER,stock_as_of INTEGER,valid_until INTEGER,next_due_at INTEGER,
    departure INTEGER,arrival INTEGER,executed INTEGER)"""


class ChampionCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private.db"
        with sqlite3.connect(self.path) as db:
            db.execute(CREATE)
            db.execute("INSERT INTO latest_predictions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       ("uni:Heather","v18","dyn3","RESEARCH_PROPOSAL_ONLY",
                        NOW-50,NOW-55,NOW+250,NOW+250,NOW+100,NOW+3200,1))

    def test_valid_snapshot_is_experimental_not_verified(self):
        data = read_snapshots(self.path, now=NOW, key="uni:Heather")
        self.assertTrue(data["actionable"])
        self.assertFalse(data["prediction_accuracy_verified"])
        self.assertEqual(data["quantity_threshold"],30)
        self.assertEqual(data["grace_seconds"],10)

    def test_expired_future_and_missed_departure_fail_closed(self):
        self.assertEqual(read_snapshots(self.path, now=NOW+251, key="uni:Heather")["status"],
                         "EXPIRED_SNAPSHOT")
        self.assertEqual(read_snapshots(self.path, now=NOW-100, key="uni:Heather")["status"],
                         "FUTURE_SNAPSHOT")
        self.assertEqual(read_snapshots(self.path, now=NOW+101, key="uni:Heather")["status"],
                         "DEPARTURE_PASSED")

    def test_stale_collector_and_rejected_worker_fail_closed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE latest_predictions SET stock_as_of=?",(NOW-181,))
        self.assertEqual(read_snapshots(self.path, now=NOW, key="uni:Heather")["status"],
                         "STALE_SOURCE")
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE latest_predictions SET stock_as_of=?,status='WORKER_ERROR'",
                       (NOW,))
        self.assertFalse(read_snapshots(self.path, now=NOW, key="uni:Heather")["actionable"])

    def test_key_parameterized_and_source_unchanged(self):
        before = self.path.read_bytes()
        self.assertEqual(read_snapshots(self.path, now=NOW, key="x' OR 1=1 --")["status"],
                         "NO_MODEL_SNAPSHOT")
        self.assertEqual(len(read_snapshots(self.path, now=NOW)),1)
        self.assertEqual(self.path.read_bytes(),before)

    def test_missing_database_or_table_fails_closed(self):
        self.assertEqual(read_snapshots(self.path.with_name("missing.db"),now=NOW,
                                        key="uni:Heather")["status"],
                         "SNAPSHOT_CACHE_UNAVAILABLE")

    def test_disabled_by_default(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(HTTPException) as result:
                api_v41_champion_predictions()
        self.assertEqual(result.exception.status_code,404)

    def test_enabled_route_reads_without_model_invocation(self):
        with patch.dict(os.environ,{"TORN_FREN_V41_CHAMPION_BETA":"1",
                                    "TORN_FREN_V41_SNAPSHOT_DB":str(self.path)}):
            with patch("web.app.time.time",return_value=NOW):
                data=api_v41_champion_predictions(country="uni",item="Heather")
        self.assertTrue(data["latest"]["actionable"])
        self.assertEqual(data["source"],"PRECOMPUTED_READ_ONLY_SIDECAR")

    def test_missing_path_and_unpaired_filters(self):
        with patch.dict(os.environ,{"TORN_FREN_V41_CHAMPION_BETA":"1"},clear=True):
            self.assertEqual(api_v41_champion_predictions()["status"],
                             "SIDECAR_NOT_CONFIGURED")
        with patch.dict(os.environ,{"TORN_FREN_V41_CHAMPION_BETA":"1",
                                    "TORN_FREN_V41_SNAPSHOT_DB":str(self.path)}):
            with self.assertRaises(HTTPException):
                api_v41_champion_predictions(country="uni")


if __name__=="__main__":
    unittest.main()
