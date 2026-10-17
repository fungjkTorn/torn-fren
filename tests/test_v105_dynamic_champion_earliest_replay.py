"""V105 score-curve real-time replan smoke: strict parity vs native incumbent."""
import types
import unittest
from unittest.mock import patch

import numpy as np

from research import v105_dynamic_champion_earliest_replay as m


START=1800000
TRAVEL=6360


class SyntheticTimeline:
    def __init__(self, earliest_good=True, starting_quantity=200):
        self.earliest_good=earliest_good
        self.starting_quantity=starting_quantity

    def success(self, arrival, grace=10):
        # Historical truth is consulted only after both policies have chosen.
        immediate=(arrival<START+TRAVEL+300)
        return immediate if self.earliest_good else not immediate

    def vals(self,t):
        shape=len(t)
        return (np.ones(shape,float),
                np.full(shape,self.starting_quantity,float),
                np.zeros(shape,float))


class FixturePlanner:
    def __init__(self):
        self.calls=0

    def plan(self,q):
        self.calls+=1
        return (max(q,START+600),.98)


def availability_curve(q):
    return {
        "delay_seconds":np.array([0,300,600,900]),
        "availability_score":np.array([.75,.8,.99,.85]),
    }


class DynamicResearchTests(unittest.TestCase):
    def run_one(self,earliest_good,qty):
        timeline=SyntheticTimeline(earliest_good,qty)
        planner=FixturePlanner()
        return m.compare_policy_dynamic(
            [START],tl=timeline,planner=planner,
            curve_function=lambda p,q:availability_curve(q),travel=TRAVEL)

    def test_earliest_success_when_champion_waits_too_long(self):
        result=self.run_one(True,0)
        self.assertTrue(result["champion_dynamic_parity_verified"])
        ch=result["methods"]["champion"]
        e=result["methods"]["earliest_0.55"]
        self.assertEqual(ch["proxy_successes"],0)
        self.assertEqual(e["proxy_successes"],1)
        self.assertEqual(ch["average_wait_minutes"],10)
        self.assertEqual(e["average_wait_minutes"],0)
        self.assertEqual(result["by_initial_stock_state"]["BELOW_30"]
                         ["earliest_0.55"]["proxy_successes"],1)
        self.assertEqual(e["matched_vs_champion"]["alternative_only"],1)

    def test_earliest_can_fail_while_waiting_champion_succeeds(self):
        result=self.run_one(False,200)
        ch=result["methods"]["champion"]
        e=result["methods"]["earliest_0.70"]
        self.assertEqual(ch["proxy_successes"],1)
        self.assertEqual(e["proxy_successes"],0)
        self.assertEqual(e["matched_vs_champion"]["champion_only"],1)
        self.assertEqual(result["by_initial_stock_state"]["AT_LEAST_30"]
                         ["champion"]["proxy_successes"],1)

    def test_unsafe_score_is_not_taken_when_none_qualify(self):
        curve={
            "delay_seconds":np.array([0,300,600]),
            "availability_score":np.array([.25,.3,.39]),
        }
        result=m.compare_policy_dynamic(
            [START],tl=SyntheticTimeline(True,0),
            planner=FixturePlanner(),
            curve_function=lambda p,q:curve,travel=TRAVEL,
            thresholds=(.4,.55,.70))
        self.assertEqual(result["methods"]["earliest_0.40"]["departures"],0)
        self.assertEqual(result["methods"]["earliest_0.55"]["departures"],0)
        self.assertEqual(result["methods"]["earliest_0.70"]["departures"],0)
        self.assertEqual(result["methods"]["champion"]["departures"],1)
        self.assertEqual(result["methods"]["depart_now"]["departures"],1)

    def test_departure_decisions_are_shared_and_no_stock_truth_used(self):
        class NoTruth:
            def success(self,*args,**kwargs):
                raise AssertionError("future stock truth accessed during planning")
        planner=FixturePlanner()
        curve_count=[0]
        def curve(q):
            curve_count[0]+=1
            return availability_curve(q)
        d=m._strategy_decisions(start=START,planner=planner,
                                curve_at=curve)
        self.assertEqual(d["departures"]["champion"],START+600)
        self.assertEqual(d["departures"]["earliest_0.40"],START)
        self.assertEqual(d["departures"]["earliest_0.55"],START)
        self.assertEqual(d["departures"]["earliest_0.70"],START)
        self.assertEqual(d["departures"]["depart_now"],START)
        self.assertLessEqual(curve_count[0],d["ticks"])

    def test_missing_real_model_result_counts_abstention(self):
        class EmptyPlanner:
            def plan(self,q):return None
        curves=lambda p,q:None
        result=m.compare_policy_dynamic(
            [START],tl=SyntheticTimeline(True,0),
            planner=EmptyPlanner(),curve_function=curves,travel=TRAVEL)
        self.assertEqual(result["methods"]["champion"]["coverage"],0.0)
        self.assertEqual(result["methods"]["earliest_0.40"]["coverage"],0.0)
        self.assertEqual(result["methods"]["depart_now"]["coverage"],1.0)

    def test_no_historical_starts_returns_safe_nulls(self):
        result=m.compare_policy_dynamic(
            [],tl=SyntheticTimeline(True,0),
            planner=FixturePlanner(),curve_function=lambda p,q:None,
            travel=TRAVEL)
        self.assertEqual(result["start_count"],0)
        self.assertIsNone(result["methods"]["champion"]["coverage"])


if __name__=="__main__":
    unittest.main()
