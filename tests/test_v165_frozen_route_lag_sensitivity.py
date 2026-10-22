import unittest
from collections import Counter

from research.v165_frozen_route_lag_sensitivity import _score_shifted


class Evidence:
    def __init__(self, outcome):
        self.outcome=outcome
    def score(self, arrival):
        return (self.outcome,"TEST",None)


class V165LagSensitivityTests(unittest.TestCase):
    def test_shifted_arrival_is_scored(self):
        record={"issued":1000,"departure":1200,"arrival":1800}
        rows=[(900,0,"p"),(1700,40,"p"),(2500,0,"p")]
        c,wait,event_lag=_score_shifted(
            record=record,lag=60,evidence=Evidence("SUCCESS"),
            rows=rows,gaps=[],flight=600,truth_cutoff=3000)
        self.assertEqual(1,c["arrival_success"])
        self.assertEqual(260,wait)
        self.assertEqual(160,event_lag)

    def test_lag_can_push_outside_horizon(self):
        record={"issued":1000,"departure":1000+28800,"arrival":1000+29400}
        c,wait,event_lag=_score_shifted(
            record=record,lag=60,evidence=Evidence("SUCCESS"),
            rows=[(900,0,"p")],gaps=[],flight=600,truth_cutoff=40000)
        self.assertEqual(1,c["outside_horizon"])
        self.assertEqual(0,c["proposals"])
        self.assertIsNone(wait)
        self.assertIsNone(event_lag)

    def test_lag_can_turn_first_window_into_too_late(self):
        record={"issued":1000,"departure":1000,"arrival":1600}
        rows=[(900,0,"p"),(1500,40,"p"),(1650,0,"p"),(2000,40,"p"),(2600,0,"p")]
        c,_,_=_score_shifted(
            record=record,lag=100,evidence=Evidence("FAILURE"),
            rows=rows,gaps=[],flight=600,truth_cutoff=3000)
        self.assertEqual(1,c["arrival_failure"])
        self.assertEqual(1,c["earliest_too_late"])


if __name__=="__main__":
    unittest.main()
