"""V173 causal recency and special abroad waiting-window contract."""
from __future__ import annotations
from collections import Counter
import unittest
from unittest.mock import Mock

from research.v173_adaptive_flight_policy import (
    CausalCycles, weighted_quantile, historical_openings,
    wait_window_grade, plan_at_issue, summary, rank, SPECIAL_WINDOWS,
)


class Evidence:
    def __init__(self,at_success=None,at_unknown=None):
        self.success=at_success
        self.unknown=at_unknown
        self.asked=[]
    def score(self,at):
        self.asked.append(at)
        if at==self.unknown:return "UNKNOWN","NO_BRACKET",None
        return ("SUCCESS" if at==self.success else "FAILURE"),"POLL_BRACKET",{}


class V173CausalTests(unittest.TestCase):
    def test_trailing_weighting_lowers_effective_old_regime(self):
        x=[3600]*24+[1200]*6
        recent=weighted_quantile(x,6,.5)
        slow=weighted_quantile(x,24,.5)
        self.assertEqual(recent,1200)
        self.assertGreater(slow,recent)

    def test_completed_cycle_history_only_adds_after_observed_depletion(self):
        rows=[
            (0,0,"yata"),(100,1000,"yata"),(250,0,"yata"),
            (500,2000,"yata"),(650,0,"yata"),
            (900,1000,"yata"),(1050,0,"yata"),
            (1300,2000,"yata"),(1450,0,"yata"),
            (1700,1000,"yata"),(1850,0,"yata"),
        ]
        c=CausalCycles(rows,lambda *_:False)
        c.advance(200)
        self.assertEqual(c.available_durations,[])
        self.assertEqual(c.restock_intervals,[])
        c.advance(1000)
        self.assertEqual(c.available_durations,[150,150])
        self.assertEqual(c.restock_intervals,[400,400])
        c.advance(1800)
        self.assertEqual(len(c.restock_intervals),4)
        self.assertEqual(len(c.available_durations),4)
        # Do not count 5th stocked window before crossing below 30.
        self.assertTrue(c.last[1]>=30)

    def test_current_restocks_may_launch_toward_next_restock(self):
        rows=[]
        for i in range(10):
            base=1000+i*3000
            rows.extend([(base-100,0,"yata"),(base,500,"yata"),
                         (base+300,10,"yata"),(base+350,0,"yata")])
        # final cycle is already stocked when departure is proposed.
        rows.extend([(31000,0,"yata"),(31100,500,"yata")])
        c=CausalCycles(rows,lambda *_:False)
        c.advance(31110)
        dep,target=c.next_departure(31110,600,10,buffer_seconds=120)
        self.assertIsNotNone(dep)
        self.assertIsNotNone(target)
        self.assertGreater(target,31110)
        self.assertGreaterEqual(dep,31110)
        self.assertEqual(c.last[1],500)

    def test_provider_switch_cannot_fabricate_zero_to_positive_restock(self):
        rows=[(0,0,"yata"),(100,1000,"torn"),(200,0,"torn"),
              (300,1000,"torn")]
        c=CausalCycles(rows,lambda *_:False)
        c.advance(350)
        self.assertEqual(c.restock_intervals,[])
        self.assertEqual(historical_openings(rows,lambda *_:False),[300])

    def test_canada_wait5_wait10_separate_from_stock_at_landing(self):
        self.assertEqual(SPECIAL_WINDOWS["can:Xanax"],(300,600))
        e=Evidence(at_success=1190)
        d=wait_window_grade(1000,"FAILURE",(300,600),[1070],e)
        self.assertEqual(d["300"],"POST_ARRIVAL_RESTOCK_WITHIN_WINDOW")
        self.assertEqual(d["600"],"POST_ARRIVAL_RESTOCK_WITHIN_WINDOW")
        d2=wait_window_grade(1000,"FAILURE",(300,600),[1370],Evidence(1490))
        self.assertEqual(d2["300"],"NO_QUALIFYING_RESTOCK")
        self.assertEqual(d2["600"],"POST_ARRIVAL_RESTOCK_WITHIN_WINDOW")
        d3=wait_window_grade(1000,"SUCCESS",(300,600),[1070],e)
        self.assertEqual(d3["300"],"ARRIVAL_SUCCESS_NOT_WAIT")

    def test_japan_wait10_20_30_cumulative_and_polls_required(self):
        self.assertEqual(SPECIAL_WINDOWS["jap:Xanax"],(600,1200,1800))
        e=Evidence(at_success=2500)
        d=wait_window_grade(1000,"FAILURE",(600,1200,1800),[2380],e)
        self.assertEqual(d["600"],"NO_QUALIFYING_RESTOCK")
        self.assertEqual(d["1200"],"NO_QUALIFYING_RESTOCK")
        self.assertEqual(d["1800"],"POST_ARRIVAL_RESTOCK_WITHIN_WINDOW")
        u=wait_window_grade(1000,"FAILURE",(600,1200,1800),
                            [1380],Evidence(at_unknown=1500))
        self.assertEqual(u["600"],"UNCONFIRMED_RESTOCK_EVIDENCE")

    def test_low_coverage_policy_cannot_win_by_cherry_picking(self):
        sparse=summary(Counter(issues=100,proposals=4,executions=4,
                               arrival_success=4),())
        broad=summary(Counter(issues=100,proposals=65,executions=55,
                              arrival_success=45,arrival_failure=5),())
        self.assertGreater(rank(broad),rank(sparse))

    def test_special_wait_success_changes_preference_only_for_canada_japan(self):
        # Same issue tape: one model lands stocked more often, but another
        # has more combined landing-or-wait successes.
        strong_landing=summary(Counter(
            issues=100,proposals=80,executions=75,arrival_success=60,
            arrival_failure=15,wait_600_success=0),(300,600))
        stronger_with_wait=summary(Counter(
            issues=100,proposals=80,executions=75,arrival_success=50,
            arrival_failure=25,wait_600_success=20),(300,600))
        self.assertGreater(rank(strong_landing),rank(stronger_with_wait))
        self.assertGreater(rank(stronger_with_wait,(300,600)),
                           rank(strong_landing,(300,600)))

    def test_first_stock_observation_is_left_censored_not_new_restock(self):
        c=CausalCycles([(0,500,"yata"),(100,480,"yata")],lambda *_:False)
        c.advance(200)
        self.assertIsNone(c.high_start)
        self.assertFalse(c.viable_current(200,500,6))
        self.assertEqual(c.available_durations,[])

    def test_causal_forecast_ignores_rows_after_issue(self):
        rows=[(0,0,"yata")]
        for i in range(6):
            s=100+i*3000
            rows += [(s,1000,"yata"),(s+500,0,"yata")]
        c=CausalCycles(rows+[(100000,1000,"yata")],lambda *_:False)
        d=CausalCycles(rows+[(100000,0,"yata")],lambda *_:False)
        for obj in (c,d):obj.advance(15800)
        self.assertEqual(c.restock_intervals,d.restock_intervals)
        self.assertEqual(c.available_durations,d.available_durations)
        self.assertEqual(c.next_departure(15800,1000,6),
                         d.next_departure(15800,1000,6))


if __name__=="__main__":
    unittest.main()
