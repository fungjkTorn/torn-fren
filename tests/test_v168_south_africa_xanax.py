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

    def test_sparse_unscored_model_is_not_mistaken_for_good_candidate(self):
        summary={"arrival_success_fraction":None,"earliest_hit_fraction":None,
                 "proposal_coverage":0.0,"arrival_known":0}
        known={"arrival_success_fraction":0.7,"earliest_hit_fraction":0.5,
               "proposal_coverage":0.75,"arrival_known":100}
        self.assertLess(_rank_summary(summary),_rank_summary(known))


if __name__=="__main__":
    unittest.main()
