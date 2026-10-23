"""Contract tests for 25th South Africa Xanax challenger carried into V171."""
from __future__ import annotations
import unittest
from unittest.mock import patch

from research.v168_south_africa_xanax import (
    KEY, COUNTRY, ITEM, FLIGHT, CANDIDATES, GENERIC_NAMES,
    _score, _rank_summary,
)
from research.plushie_champions.common import TRAVEL_SECONDS


class SouthAfricaV168ChampionTests(unittest.TestCase):
    def test_frozen_incumbent_and_distinct_long_flight(self):
        self.assertEqual(KEY,"sou:Xanax")
        self.assertEqual((COUNTRY,ITEM),("sou","Xanax"))
        self.assertEqual(FLIGHT,TRAVEL_SECONDS["sou"])
        self.assertEqual(FLIGHT,11820)
        self.assertEqual(len(set(CANDIDATES)),len(CANDIDATES))
        self.assertIn("v19:dyn1",CANDIDATES)
        self.assertIn("v20:traj14",CANDIDATES)
        self.assertTrue(set(GENERIC_NAMES)<=set(CANDIDATES))

    def test_flight_success_is_success_even_if_before_targeted_oracle(self):
        class Evidence:
            def score(self,arrival):
                return "SUCCESS","POLL_BACKED_DELTA_STATE",{
                    "pre_quantity":1000,"post_quantity":995}
        issued=1000000
        depart=issued+30
        target={"status":"EARLIEST_REACHABLE_FOUND",
                "restock":depart+FLIGHT+300,
                "depletion":depart+FLIGHT+1500,
                "oracle_earliest_departure":depart}
        with patch("research.v168_south_africa_xanax._earliest_reachable_window",
                   return_value=target):
            counts,delta,offset=_score(depart,issued,[],[],Evidence(),issued+50000)
        self.assertEqual(counts["arrival_success"],1)
        self.assertEqual(counts["earliest_hit"],0)
        self.assertEqual(delta,0)
        self.assertEqual(offset,-300)

    def test_screen_values_broad_coverage_over_tiny_conditional_win_rate(self):
        # A cherry-picked 4/4 record is worse advice than reliably successful
        # 60/100 from the same 100 issue clock opportunities.
        rare={"issues":100,"proposals":4,"arrival_known":4,
              "arrival_success_fraction":1.0,
              "earliest_hit_fraction":1.0,
              "proposal_coverage":.04,
              "counts":{"arrival_success":4}}
        broad={"issues":100,"proposals":80,"arrival_known":75,
               "arrival_success_fraction":.8,
               "earliest_hit_fraction":.8,
               "proposal_coverage":.8,
               "counts":{"arrival_success":60}}
        self.assertGreater(_rank_summary(broad),_rank_summary(rare))

    def test_screen_prefers_real_successful_arrivals_over_abstaining(self):
        a={"issues":100,"proposals":75,"arrival_known":70,
           "arrival_success_fraction":.95,"earliest_hit_fraction":.9,
           "proposal_coverage":.75,"counts":{"arrival_success":66}}
        b={"issues":100,"proposals":90,"arrival_known":85,
           "arrival_success_fraction":.83,"earliest_hit_fraction":.8,
           "proposal_coverage":.9,"counts":{"arrival_success":71}}
        self.assertGreater(_rank_summary(b),_rank_summary(a))

    def test_sparse_unscored_model_is_not_mistaken_for_good_candidate(self):
        summary={"arrival_success_fraction":None,"earliest_hit_fraction":None,
                 "proposal_coverage":0.0,"arrival_known":0}
        known={"arrival_success_fraction":0.7,"earliest_hit_fraction":0.5,
               "proposal_coverage":0.75,"arrival_known":100}
        self.assertLess(_rank_summary(summary),_rank_summary(known))


if __name__=="__main__":
    unittest.main()
