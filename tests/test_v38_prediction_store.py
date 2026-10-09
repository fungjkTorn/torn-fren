"""Research cache contract tests (no collector, web, credentials, or VM)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v38_prediction_store import open_writer, record, read, prune_attempts

NOW = 1791540000
OUTPUT = {
    "status": "RESEARCH_PROPOSAL_ONLY",
    "recommended_departure_timestamp": NOW+600,
    "recommended_arrival_timestamp": NOW+6960,
    "quantity_threshold": 30,
    "grace_seconds": 10,
    "replan_step_seconds": 300,
    "probability_calibrated": False,
}


class PredictionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "sidecar.db"
        self.con = open_writer(self.path)
        self.addCleanup(self.con.close)

    def put(self, **kw):
        args = dict(
            key="uni:Heather", family="V18", config="dyn3", output=OUTPUT,
            now=NOW, stock_as_of=NOW-30, executed=True,
        )
        args.update(kw)
        return record(self.con, **args)

    def test_valid_proposal_and_stale_fallback(self):
        self.assertEqual(self.put(), "RESEARCH_PROPOSAL_ONLY")
        current = read(self.path, NOW, "uni:Heather")
        self.assertFalse(current["fallback_required"])
        self.assertEqual(current["recommended_departure_timestamp"], NOW+600)
        stale = read(self.path, NOW+301, "uni:Heather")
        self.assertTrue(stale["fallback_required"])
        self.assertEqual(stale["status"], "STALE_SNAPSHOT")
        self.assertIsNone(stale["recommended_departure_timestamp"])

    def test_no_fake_unintegrated_success(self):
        self.assertEqual(self.put(executed=False), "SPECIALIST_NOT_INTEGRATED")
        self.assertTrue(read(self.path,NOW,"uni:Heather")["fallback_required"])
        self.assertIsNone(read(self.path,NOW,"uni:Heather")["recommended_arrival_timestamp"])

    def test_arrival_criterion_and_horizon_checked(self):
        for change in [
            {"quantity_threshold": 10},
            {"grace_seconds": 60},
            {"replan_step_seconds": 900},
            {"probability_calibrated": True},
        ]:
            o = {**OUTPUT, **change}
            self.assertEqual(self.put(output=o), "INCOMPATIBLE_CHAMPION_CONTRACT")
        bad = {**OUTPUT, "recommended_departure_timestamp": NOW+28801}
        self.assertEqual(self.put(output=bad),"OUT_OF_BOUNDS_CANDIDATE_REJECTED")

    def test_future_records_rejected_and_stale_source_abstains(self):
        with self.assertRaises(ValueError):
            self.put(stock_as_of=NOW+1)
        self.assertEqual(self.put(stock_as_of=NOW-181), "STALE_SOURCE_REJECTED")

    def test_missing_cache_does_not_create_database(self):
        unknown = Path(self.tmp.name)/"not-created.db"
        self.assertEqual(read(unknown,NOW,"jap:Xanax")["status"],"CACHE_UNAVAILABLE")
        self.assertFalse(unknown.exists())
        self.assertEqual(read(self.path,NOW,"jap:Xanax")["status"],"NO_SNAPSHOT")

    def test_older_result_does_not_replace_newer(self):
        self.put()
        record(self.con,key="uni:Heather",family="V18",config="dyn3",
               output={"status":"WORKER_TIMEOUT"},now=NOW-1,
               stock_as_of=NOW-40,executed=True)
        self.assertEqual(read(self.path,NOW,"uni:Heather")["worker_status"],
                         "RESEARCH_PROPOSAL_ONLY")

    def test_prune_only_attempts(self):
        self.put()
        self.assertEqual(prune_attempts(self.con,NOW+1),1)
        self.assertFalse(read(self.path,NOW,"uni:Heather")["fallback_required"])

    def test_batch_read_and_unqualified_states(self):
        self.put()
        self.put(key="jap:Xanax",family="japan_xanax_specialist",
                 config=None,output={"status":"SPECIALIST_NOT_INTEGRATED"},
                 executed=False)
        rows = read(self.path,NOW)
        self.assertEqual(len(rows),2)
        self.assertEqual([r["item_key"] for r in rows],["jap:Xanax","uni:Heather"])
        self.assertTrue(rows[0]["fallback_required"])


if __name__ == "__main__":
    unittest.main()
