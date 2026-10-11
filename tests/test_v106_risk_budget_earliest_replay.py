"""V106: risk-budget policy must preserve original champion and no-lookahead."""
import types
import unittest

import numpy as np

from research import v106_risk_budget_earliest_replay as m


START=1_800_000
TRAVEL=6360


class SyntheticTimeline:
    def __init__(self, is_good=None, q=120):
        self.is_good=is_good or (lambda arrival:True)
        self.q=q
    def success(self,arrival,grace=10):
        return bool(self.is_good(arrival))
    def vals(self,t):
        n=len(t)
        return (np.ones(n,float),
                np.full(n,self.q,float),
                np.zeros(n,float))


class Planner:
    def plan(self,q):
        return (max(q,START+600),.98)


class RiskBudgetTests(unittest.TestCase):
    def test_selects_earliest_without_sacrificing_peak_margin(self):
        curve={
            "delay_seconds":np.array([0,300,600,900]),
            "availability_score":np.array([.75,.8,.97,.98]),
        }
        self.assertEqual(
            m.earliest_risk_budget(START,curve,loss_budget=.03)[0],
            START+600)
        self.assertEqual(
            m.earliest_risk_budget(START,curve,loss_budget=.20)[0],
            START+300)

    def test_requires_contiguous_two_points(self):
        curve={
            "delay_seconds":np.array([0,300,600,900,1200]),
            "availability_score":np.array([.98,.2,.99,.97,.2]),
        }
        p=m.earliest_risk_budget(START,curve,loss_budget=.03)
        self.assertEqual(p[0],START+600)

    def test_analog_robust_filter_rejects_local_spikes(self):
        curve={
            "delay_seconds":np.array([0,300,600,900]),
            "availability_score":np.array([.99,.98,.98,.97]),
            "robust_score":np.array([.3,.32,.91,.94]),
        }
        p=m.earliest_risk_budget(START,curve,loss_budget=.05)
        self.assertEqual(p[0],START+600)

    def test_stale_unknown_curve_causes_abstention(self):
        self.assertIsNone(
            m.earliest_risk_budget(START,None,loss_budget=.03))
        self.assertIsNone(
            m.earliest_risk_budget(START,{
                "delay_seconds":np.array([]),
                "availability_score":np.array([])},loss_budget=.03))
        self.assertIsNone(
            m.earliest_risk_budget(START,{
                "delay_seconds":np.array([0,300]),
                "availability_score":np.array([np.nan,.9])},
                loss_budget=.03))

    def test_five_minute_champion_parity_with_shorter_departure(self):
        def curve(p,q):
            return {
                "delay_seconds":np.array([0,300,600,900]),
                "availability_score":np.array([.96,.97,.99,.98]),
            }
        result=m.evaluate(
            [START],tl=SyntheticTimeline(q=0),planner=Planner(),
            travel=TRAVEL,curve_generator=curve)
        self.assertTrue(result["champion_dynamic_parity"])
        self.assertEqual(result["stats"]["champion"]["mean_wait_minutes"],10)
        self.assertEqual(result["stats"]["nearpeak_0.03"]["mean_wait_minutes"],0)
        self.assertEqual(result["initial_below_30"]["champion"]["hits"],1)
        self.assertEqual(result["stats"]["nearpeak_0.03"]["hits"],1)

    def test_peaky_curve_can_protect_champion_choice(self):
        def curve(p,q):
            return {
                "delay_seconds":np.array([0,300,600,900]),
                "availability_score":np.array([.2,.3,.99,.98]),
            }
        result=m.evaluate(
            [START],tl=SyntheticTimeline(q=400),
            planner=Planner(),travel=TRAVEL,curve_generator=curve)
        self.assertEqual(result["stats"]["nearpeak_0.03"]["mean_wait_minutes"],10)
        self.assertEqual(result["initial_at_least_30"]["nearpeak_0.03"]["hits"],1)

    def test_explicit_fixed_floor_baseline_remains_available(self):
        def curve(p,q):
            return {
                "delay_seconds":np.array([0,300,600,900]),
                "availability_score":np.array([.65,.66,.99,.98]),
            }
        result=m.evaluate(
            [START],tl=SyntheticTimeline(),planner=Planner(),
            travel=TRAVEL,curve_generator=curve)
        self.assertEqual(result["stats"]["floor_0.55"]["mean_wait_minutes"],0)
        self.assertEqual(result["stats"]["nearpeak_0.03"]["mean_wait_minutes"],10)

    def test_no_historical_starts_does_not_fabricate_precision(self):
        def curve(p,q):return None
        result=m.evaluate(
            [],tl=SyntheticTimeline(),planner=Planner(),
            travel=TRAVEL,curve_generator=curve)
        self.assertIsNone(result["stats"]["champion"]["hit_fraction_per_start"])
        self.assertTrue(result["champion_dynamic_parity"])


if __name__=="__main__":
    unittest.main()
