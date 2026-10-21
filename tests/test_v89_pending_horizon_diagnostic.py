"""V89 pending explanations are timestamp arithmetic, not accuracy scoring."""
import tempfile
import unittest
from pathlib import Path

from research import v89_pending_horizon_diagnostic as m
from research.v38_prediction_store import open_writer,record
from research.plushie_champions.common import TRAVEL_SECONDS

NOW=1791650000
KEY="mex:Jaguar Plushie"
FLIGHT=TRAVEL_SECONDS["mex"]


class PendingHorizonTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"research.db"

    def add(self, issued, departure, *, key=KEY,
            status="RESEARCH_PROPOSAL_ONLY", source_age=25):
        conn=open_writer(self.db)
        try:
            return record(conn, key=key, family="fixture", config="fixture",
                          output={
                              "status":status,
                              "recommended_departure_timestamp":departure,
                              "recommended_arrival_timestamp":departure+FLIGHT,
                              "quantity_threshold":30,
                              "grace_seconds":10,
                              "replan_step_seconds":300,
                              "probability_calibrated":False},
                          now=issued,stock_as_of=issued-source_age,
                          executed=True,next_due=issued+300)
        finally:
            conn.close()

    def test_four_pending_stages_and_matured(self):
        self.add(NOW-3600,NOW-2200) # arrived 1180s ago
        self.add(NOW-1800,NOW-1200) # arrived 180s ago, +190 not complete
        self.add(NOW-1000,NOW-350)  # flying; arrival in 670s
        self.add(NOW-100,NOW+800)   # departure future
        out=m.analyze(sidecar=self.db,now=NOW)
        self.assertEqual(out["raw_rows"],4)
        self.assertEqual(out["unique_item_arrival_targets"],4)
        self.assertEqual(out["pending_equivalent_to_v76"],3)
        self.assertEqual(out["matured_equivalent_to_v76"],1)
        self.assertEqual(out["stage_counts"],{
            "WAITING_FOR_DEPARTURE":1,
            "HYPOTHETICALLY_IN_FLIGHT":1,
            "AWAITING_POST_ARRIVAL_BUFFER":1,
            "MATURED_FOR_OUTCOME_AUDIT":1})
        self.assertFalse(out["actual_restock_independence_certified"])
        self.assertTrue(out["read_only"])

    def test_duplicate_exact_arrival_not_new_opportunity(self):
        self.add(NOW-1000,NOW+600)
        self.add(NOW-700,NOW+600)
        out=m.analyze(sidecar=self.db,now=NOW)
        self.assertEqual(out["raw_valid_candidate_rows"],2)
        self.assertEqual(out["unique_item_arrival_targets"],1)
        self.assertEqual(out["exact_item_and_arrival_duplicate_rows"],1)

    def test_departure_target_shift_and_withdrawal(self):
        self.add(NOW-900,NOW+2000)
        self.add(NOW-600,NOW+3200) # +20 minutes
        self.add(NOW-300,NOW+3400,status="EXPERT_ABSTAINED")
        out=m.analyze(sidecar=self.db,now=NOW)
        self.assertEqual(out["forecast_revision_pair_counts"].get(
            "MOVED_LATER_15M_PLUS"),1)
        self.assertEqual(out["forecast_revision_pair_counts"].get(
            "RECOMMENDATION_WITHDRAWN"),1)
        self.assertEqual(out["invalid_or_abstained_rows"],1)

    def test_wait_buckets(self):
        self.assertEqual(m.wait_bucket(0),"0–5m")
        self.assertEqual(m.wait_bucket(300),"0–5m")
        self.assertEqual(m.wait_bucket(301),"5–15m")
        self.assertEqual(m.wait_bucket(8000),"2–4h")
        self.assertEqual(m.wait_bucket(24000),"6–8h")
        self.assertEqual(m.wait_bucket(28801),"OVER_8H")

    def test_nearby_target_groups_are_heuristic_only(self):
        fake=[{"item_key":KEY,"arrival":1000},
              {"item_key":KEY,"arrival":1010},
              {"item_key":KEY,"arrival":2300},
              {"item_key":"uni:Heather","arrival":1000}]
        self.assertEqual(m.count_nearby_target_groups(fake),
                         {KEY:2,"uni:Heather":1})

    def test_missing_sidecar_does_not_create_a_database(self):
        p=self.db
        with self.assertRaises((OSError, ValueError)):
            m.analyze(sidecar=p,now=NOW)
        self.assertFalse(p.exists())


if __name__=="__main__":
    unittest.main()
