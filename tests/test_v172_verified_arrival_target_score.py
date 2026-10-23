"""V172: historical earliest restock-target scoring must fail closed."""
from __future__ import annotations
import unittest
from unittest.mock import patch

from research.v172_verified_arrival_target_score import grade_target_window
from research.v167_all24_live_policy_replay import score_decision
from research.v168_south_africa_xanax import _score as score_south_xanax, FLIGHT


class Evidence:
    def __init__(self,state):self.state=state
    def score(self,arrival):return self.state,"SYNTHETIC_POLL_COVERAGE",{}


class V172EvidenceQualifiedTests(unittest.TestCase):
    def test_sou_failed_stock_after_target_cannot_be_target_hit_without_depletion(self):
        arrival=1_000_000
        result=grade_target_window(arrival=arrival,state="FAILURE",
                                   restock=arrival-700,depletion=None)
        self.assertEqual(result,(None,"UNKNOWN_TARGET_DEPLETION"))

    def test_sou_unknown_arrival_cannot_be_target_hit_even_with_end(self):
        result=grade_target_window(arrival=1_000_000,state="UNKNOWN",
                                   restock=999_000,depletion=1_001_000)
        self.assertEqual(result,(None,"UNSCORABLE_STOCK_AT_LANDING"))

    def test_fully_observed_window_requires_stock_at_landing(self):
        epoch=1_000_000
        kw={"arrival":epoch,"restock":epoch-100,"depletion":epoch+20}
        self.assertEqual(grade_target_window(state="SUCCESS",**kw)[0],True)
        self.assertEqual(grade_target_window(state="FAILURE",**kw)[0],False)
        self.assertEqual(grade_target_window(state="SUCCESS",arrival=epoch-200,
                            restock=epoch-100,depletion=epoch+20)[0],False)
        self.assertEqual(grade_target_window(state="SUCCESS",arrival=epoch+30,
                            restock=epoch-100,depletion=epoch+20)[0],False)

    def test_v167_always_exposes_independent_verified_score(self):
        issued=1_000_000
        departure=issued+100
        arrival=departure+FLIGHT
        target={"status":"EARLIEST_REACHABLE_FOUND",
                "restock":arrival-300,"depletion":None,
                "oracle_earliest_departure":departure}
        with patch("research.v167_all24_live_policy_replay._earliest_reachable_window",
                   return_value=target):
            got=score_decision("sou:Xanax",issued,departure,arrival+5000,
                               [],[],Evidence("FAILURE"))
        self.assertEqual(got["arrival_state"],"FAILURE")
        self.assertIsNone(got["verified_earliest_target_hit"])
        self.assertEqual(got["verified_earliest_target_evidence"],"UNKNOWN_TARGET_DEPLETION")

    def test_v168_counter_requires_verified_target_end(self):
        issued=1_000_000
        departure=issued+100
        arrival=departure+FLIGHT
        target={"status":"EARLIEST_REACHABLE_FOUND",
                "restock":arrival-300,"depletion":None,
                "oracle_earliest_departure":departure}
        with patch("research.v168_south_africa_xanax._earliest_reachable_window",
                   return_value=target):
            counts,*_=score_south_xanax(departure,issued,[],[],Evidence("FAILURE"),arrival+500)
        self.assertEqual(counts["arrival_failure"],1)
        self.assertEqual(counts["earliest_scored"],0)
        self.assertEqual(counts["earliest_hit"],0)
        self.assertEqual(counts["temporal_target_proxy_hit"],1)
        self.assertEqual(counts["target_evidence_UNKNOWN_TARGET_DEPLETION"],1)


if __name__=="__main__":
    unittest.main()
