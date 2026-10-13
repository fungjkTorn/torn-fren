"""Actual country-flight horizon comparisons of completed LOW/HIGH cycles."""
import unittest

from research.v107_explicit_restock_cycle_baseline import StockObservation as O
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v158_flight_horizon_router import (
    _fully_bounded_episodes,_origin_future_states,
    _simulator_probability,_score_complete_episodes,
    flight_horizon_item_route,
)
from research.plushie_champions.common import TRAVEL_SECONDS

T=1791800000


def evidence(pairs, gap_at=None):
    t=T
    out=[O(t,0,"yata")]
    for i,(low,high) in enumerate(pairs):
        t+=low
        out.append(O(t,100,"yata"))
        t+=high
        out.append(O(t,0,"yata"))
        if gap_at==i:
            t+=600
            out.append(O(t,0,"yata"))
    phases=provider_continuous_phases(out,asof=t)
    return phases,t


class FlightHorizonTests(unittest.TestCase):
    def test_phase_truth_requires_verified_contiguous_future_episodes(self):
        phases,issue=evidence([(100,200)]*12)
        windows=_fully_bounded_episodes(phases,issue)
        self.assertGreaterEqual(len(windows),11)
        res=_origin_future_states(windows,0,(50,150,250,310,720))
        self.assertFalse(res[50])
        self.assertTrue(res[150])
        self.assertTrue(res[250])
        self.assertFalse(res[310])
        self.assertTrue(res[720])

    def test_future_gap_never_becomes_assumed_outcome(self):
        # These complete pairs are independently valid, but the 400s gap
        # between pairs 2 and 3 makes subsequent arrival truth unknown.
        windows=((T+100,T+200,T+300),
                 (T+300,T+400,T+500),
                 (T+900,T+1000,T+1100))
        result=_origin_future_states(windows,1,(50,250,700))
        self.assertFalse(result[50])
        self.assertIsNone(result[250])
        self.assertIsNone(result[700])

    def test_same_actual_flight_horizons_and_no_outcome_leakage(self):
        pairs=[(900,1500),(1300,1500)]*16
        phases,issued=evidence(pairs)
        result=flight_horizon_item_route(
            "mex:Jaguar Plushie",phases,asof=issued)
        expected=tuple(TRAVEL_SECONDS["mex"]+10+wait
                       for wait in (0,300,900))
        self.assertEqual(result["arrival_horizons_seconds"],expected)
        self.assertGreater(result["completed_episode_count"],10)
        self.assertGreater(result["validation_origin_count"],3)
        self.assertTrue(result["future_bounded_phases_not_used"])
        self.assertFalse(result["publication_allowed"])
        self.assertIn(result["selected_sampling"],
                      ("paired_complete","independent"))
        subsequent=flight_horizon_item_route(
            "mex:Jaguar Plushie",phases,asof=issued+300)
        self.assertEqual(result["paired_brier_lift"],
                         subsequent["paired_brier_lift"])
        with self.assertRaisesRegex(ValueError,"future observation"):
            flight_horizon_item_route(
                "mex:Jaguar Plushie",phases,asof=issued-1)

    def test_insufficient_future_continuity_fails_closed(self):
        phases,issued=evidence([(100,200)]*8)
        result=flight_horizon_item_route("jap:Xanax",phases,asof=issued)
        self.assertEqual(result["selected_sampling"],"independent")
        self.assertEqual(result["reason"],"INSUFFICIENT_COMPLETE_EPISODES")

    def test_independent_vs_paired_simulator_has_real_difference(self):
        train=((120,120),(900,900),(120,120),(900,900))*3
        horizons=(400,800,1200)
        a=_simulator_probability(train,horizons,paired=True,seed=42)
        b=_simulator_probability(train,horizons,paired=False,seed=42)
        self.assertEqual(set(a),set(horizons))
        self.assertEqual(set(b),set(horizons))
        self.assertNotEqual(a,b)
        self.assertEqual(a,_simulator_probability(
            train,horizons,paired=True,seed=42))

    def test_clipped_or_future_interval_not_accepted(self):
        phases,issued=evidence([(600,900)]*15)
        phases["observed_bounded_depleted_windows"].append(
            (issued+1,issued+100))
        with self.assertRaises(ValueError):
            flight_horizon_item_route(
                "uni:Red Fox Plushie",phases,asof=issued)

    def test_elapsed_predicted_horizon_larger_than_observed_known_truth_abstains(self):
        phases,issued=evidence([(500,500)]*11)
        e=_fully_bounded_episodes(phases,issued)
        actual=_origin_future_states(e,len(e)-1,(1100,4000))
        self.assertIsNone(actual[1100])
        self.assertIsNone(actual[4000])


if __name__=="__main__":
    unittest.main()
