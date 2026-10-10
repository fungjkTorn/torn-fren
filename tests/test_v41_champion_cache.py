"""V41 beta is sidecar-only, explicitly opt-in, and refuses stale actions."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from web.v41_champion_cache import read_snapshots, read_live_poll_heartbeat
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
        data = read_snapshots(self.path, now=NOW, live_heartbeat=NOW, key="uni:Heather")
        self.assertTrue(data["actionable"])
        self.assertFalse(data["prediction_accuracy_verified"])
        self.assertEqual(data["quantity_threshold"],30)
        self.assertEqual(data["grace_seconds"],10)

    def test_expired_future_and_missed_departure_fail_closed(self):
        self.assertEqual(read_snapshots(self.path, now=NOW+251, live_heartbeat=NOW+251, key="uni:Heather")["status"],
                         "EXPIRED_SNAPSHOT")
        self.assertEqual(read_snapshots(self.path, now=NOW-100, live_heartbeat=NOW-100, key="uni:Heather")["status"],
                         "FUTURE_SNAPSHOT")
        self.assertEqual(read_snapshots(self.path, now=NOW+101, live_heartbeat=NOW+101, key="uni:Heather")["status"],
                         "DEPARTURE_PASSED")

    def test_stale_collector_and_rejected_worker_fail_closed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE latest_predictions SET stock_as_of=?",(NOW-231,))
        self.assertEqual(read_snapshots(self.path, now=NOW, key="uni:Heather")["status"],
                         "STALE_AT_INFERENCE")
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE latest_predictions SET stock_as_of=?,status='WORKER_ERROR'",
                       (NOW,))
        self.assertFalse(read_snapshots(self.path, now=NOW, key="uni:Heather")["actionable"])


    def test_previously_false_stale_after_180_seconds_remains_valid(self):
        with sqlite3.connect(self.path) as db:
            db.execute("""UPDATE latest_predictions SET
                computed_at=?,stock_as_of=?,valid_until=?,departure=?,arrival=?""",
                (NOW-270,NOW-275,NOW+30,NOW+10,NOW+1500))
        d=read_snapshots(self.path,now=NOW,live_heartbeat=NOW-5,key="uni:Heather")
        self.assertTrue(d["actionable"])
        self.assertEqual(d["collector_last_verified"],NOW-5)
        expired=read_snapshots(self.path,now=NOW+30,live_heartbeat=NOW+30,key="uni:Heather")
        self.assertEqual(expired["status"],"EXPIRED_SNAPSHOT")

    def test_current_collector_outage_and_missing_heartbeat_fail_closed(self):
        missing=read_snapshots(self.path,now=NOW,key="uni:Heather")
        self.assertEqual(missing["status"],"COLLECTOR_UNVERIFIED")
        stale=read_snapshots(self.path,now=NOW,live_heartbeat=NOW-181,key="uni:Heather")
        self.assertEqual(stale["status"],"COLLECTOR_STALE")
        future=read_snapshots(self.path,now=NOW,live_heartbeat=NOW+1,key="uni:Heather")
        self.assertEqual(future["status"],"FUTURE_COLLECTOR_HEARTBEAT")
        regressed=read_snapshots(self.path,now=NOW,live_heartbeat=NOW-100,key="uni:Heather")
        self.assertEqual(regressed["status"],"COLLECTOR_HEARTBEAT_REGRESSION")

    def test_read_only_indexed_collector_heartbeat(self):
        collector=Path(self.temp.name)/"collector.db"
        with sqlite3.connect(collector) as db:
            db.execute("CREATE TABLE poll_heartbeats (timestamp INTEGER,mode TEXT,success INTEGER)")
            db.executemany("INSERT INTO poll_heartbeats VALUES(?,?,?)",[
                (NOW-10,"poll-cycle",1),(NOW-3,"poll-cycle",0),
                (NOW-2,"manual",1)])
            db.execute("CREATE INDEX idx_timestamp ON poll_heartbeats(timestamp)")
        before=collector.read_bytes()
        self.assertEqual(read_live_poll_heartbeat(collector),NOW-10)
        self.assertEqual(collector.read_bytes(),before)
        self.assertIsNone(read_live_poll_heartbeat(collector.with_name("missing.db")))

    def test_key_parameterized_and_source_unchanged(self):
        before = self.path.read_bytes()
        self.assertEqual(read_snapshots(self.path, now=NOW, key="x' OR 1=1 --")["status"],
                         "NO_MODEL_SNAPSHOT")
        self.assertEqual(len(read_snapshots(self.path, now=NOW, live_heartbeat=NOW)),1)
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
            with patch("web.app.time.time",return_value=NOW), \
                 patch("web.app.read_live_poll_heartbeat",return_value=NOW):
                data=api_v41_champion_predictions(country="uni",item="Heather")
        self.assertTrue(data["latest"]["actionable"])
        self.assertEqual(data["source"],"PRECOMPUTED_READ_ONLY_SIDECAR")
        self.assertEqual(data["latest"]["collector_last_verified"],NOW)

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
