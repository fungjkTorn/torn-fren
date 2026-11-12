"""V104: comparators must share one as-of instant and real model scores."""
import types
import unittest
from unittest.mock import patch

import numpy as np

from research import v104_real_champion_earliest_replay as m
from research.plushie_champions.common import TemplatePlanner


class FakeTimeline:
    def success(self, arrival, grace=10):
        # Succeeds only inside a synthetic stocked window.
        return arrival % 3600 >= 1200


class V104PilotTests(unittest.TestCase):
    def test_episode_sampling_is_bounded_and_holdout_only(self):
        starts=list(range(0,100*1800,1800))
        selected=m.select_starts(starts,7)
        self.assertEqual(len(selected),7)
        self.assertTrue(all(x in starts[75:] for x in selected))
        self.assertEqual(selected,sorted(selected))

    def test_score_plateaus_are_contiguous_windows_not_proven_restock(self):
        q=1800000
        curve={
            "delay_seconds":np.array([0,300,600,1200]),
            "availability_score":np.array([.8,.9,.3,.8]),
        }
        output=m._score_windows(curve,q,1020,.7)
        self.assertEqual(len(output),2)
        self.assertEqual(output[0]["grid_points"],2)
        self.assertEqual(output[0]["score_supported_arrival_start"],q+1020)
        self.assertEqual(output[0]["score_supported_arrival_end_exclusive"],
                         q+1020+600)
        self.assertEqual(output[1]["score_supported_arrival_start"],
                         q+1020+1200)

    def test_same_curve_is_used_for_champion_and_all_earliest_floors(self):
        starts=[i*1800+1800000 for i in range(12)]
        # The post-75% holdout has three query ticks.
        ctx=types.SimpleNamespace(timelines={
            ("uni","Nessie Plushie"):FakeTimeline()})
        champion=object.__new__(TemplatePlanner)
        champion.plan=lambda q:(q+600,.9,{"fit":.9})
        curve={
            "delay_seconds":np.array([0,300,600,900]),
            "availability_score":np.array([.65,.7,.9,.75]),
            "model_type":"template",
        }
        with patch.object(m,"valid_starts",return_value=starts), \
             patch.object(m,"model_for",return_value=champion), \
             patch.object(m,"score_curve",return_value=curve):
            output=m.inspect_item(ctx,"nessie",2,thresholds=(.4,.55,.8))
        self.assertEqual(output["asof_holdout_query_count"],2)
        self.assertEqual(output["statistics"]["champion"]["departures"],2)
        self.assertEqual(output["statistics"]["earliest_floor_0.40"]["departures"],2)
        self.assertEqual(output["statistics"]["earliest_floor_0.80"]["departures"],2)
        self.assertLess(
            output["statistics"]["earliest_floor_0.40"]["waiting_time"]["mean_minutes"],
            output["statistics"]["champion"]["waiting_time"]["mean_minutes"])
        self.assertEqual(len(output["examples"]),2)
        self.assertFalse(output["replanning_during_trip_simulated"])
        self.assertFalse(output["score_calibrated"])

    def test_no_episodes_without_holdout(self):
        self.assertEqual(m.select_starts([],4),[])
        self.assertEqual(m.FOX_CONFIG["k"],18)
        self.assertEqual(m.NESS_CONFIG["lags"],(1,))

    def test_model_parity_mismatch_is_not_silenced(self):
        starts=[i*1800+1800000 for i in range(12)]
        ctx=types.SimpleNamespace(timelines={
            ("uni","Nessie Plushie"):FakeTimeline()})
        model=object.__new__(TemplatePlanner)
        model.plan=lambda q:(q+1200,.95,{"fit":.9})
        curve={
            "delay_seconds":np.array([0,300,600]),
            "availability_score":np.array([.65,.7,.9]),
        }
        with patch.object(m,"valid_starts",return_value=starts), \
             patch.object(m,"model_for",return_value=model), \
             patch.object(m,"score_curve",return_value=curve):
            with self.assertRaises(AssertionError):
                m.inspect_item(ctx,"nessie",2)


if __name__=="__main__":
    unittest.main()
