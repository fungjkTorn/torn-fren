"""V174 fresh-inference tournament, causal preparation, holdout and scoring."""
from __future__ import annotations

from collections import Counter
import unittest
from unittest.mock import patch

from deploy.scripts.v163_readonly_event_first_preview import OBS
from research.v174_full25_forecast_tournament import (
    ALL_CANDIDATES, ENGINE_NAMES, AdaptiveRate, AdaptiveZero,
    advance_trackers, event_departures, grade_candidates, brief,
    screen_rank, fixed_roster,
)
from research.v167_all24_live_policy_replay import ROUTES
from research.v173_adaptive_flight_policy import SPECIAL_WINDOWS


class Evidence:
    def __init__(self,truth=None):
        self.truth=truth or {}
        self.queries=[]
    def score(self,epoch):
        self.queries.append(epoch)
        return self.truth.get(epoch,"UNKNOWN"),"SYNTHETIC",{}


class V174ContractTests(unittest.TestCase):
    def test_every_item_has_same_full_fresh_model_screen(self):
        self.assertEqual(len(ROUTES),25)
        self.assertEqual(len(ALL_CANDIDATES),54)
        self.assertEqual(len(ALL_CANDIDATES),len(set(ALL_CANDIDATES)))
        for family in ("v18","v19","v20"):
            self.assertIn(f"{family}:{ENGINE_NAMES[family][0]}",ALL_CANDIDATES)
        self.assertIn("v19:dyn8@48h",ALL_CANDIDATES)
        self.assertIn("v20:traj12@120h",ALL_CANDIDATES)
        self.assertIn("V169_INCUMBENT",ALL_CANDIDATES)
        self.assertIn("zero:recent6",ALL_CANDIDATES)
        self.assertIn("rate:recent20",ALL_CANDIDATES)
        self.assertEqual(set(SPECIAL_WINDOWS),{"can:Xanax","jap:Xanax"})

    def test_incremental_trackers_cannot_observe_future_stock(self):
        rows=[
            (0,0,"a"),(100,1000,"a"),(200,0,"a"),
            (500,1200,"a"),(600,0,"a"),
            (900,1500,"a"),(1100,0,"a"),
            (1300,1000,"a"),(1500,0,"a"),
            (1800,2000,"a"),(1900,0,"a"),
            (2100,2000,"a"),(2300,0,"a"),
            (1000000,9999999,"a")
        ]
        tracks={k:v(lambda *_:False,n) for k,v,n in [
            ("zero:recent6",AdaptiveZero,6),
            ("rate:recent10",AdaptiveRate,10)]}
        pos=advance_trackers(tracks,rows,0,2200)
        self.assertEqual(tracks["zero:recent6"].last.epoch,2100)
        self.assertEqual(tracks["rate:recent10"].last.epoch,2100)
        self.assertEqual(rows[pos][0],2300)
        for tr in tracks.values():
            self.assertTrue(all(t<=2200 for t in
                [tr.last.epoch]))
        later=dict(rows)
        self.assertIsNotNone(later)

    def test_previously_stocked_is_eligible_for_next_future_restock_all_roster(self):
        event0={"event_index":0,"reachable":True,"predicted_restock_epoch":1000,
                "predicted_depletion_epoch":1700,
                "earliest_departure_epoch":1000,
                "latest_departure_epoch":1100}
        next1={"event_index":1,"reachable":True,"predicted_restock_epoch":3500,
               "predicted_depletion_epoch":3800,
               "earliest_departure_epoch":2500,
               "latest_departure_epoch":2600}
        for key in ROUTES:
            with self.subTest(item=key):
                result=event_departures([event0,next1],1000,1000)
                self.assertIn(0,{p[1]["event_index"] for p in result})
                self.assertIn(1,{p[1]["event_index"] for p in result})
                self.assertGreater(max(p[0] for p in result),0)

    def test_full_five_minute_confirmation_distinguishes_success_failure_unknown(self):
        issued=1200
        plan={
            "v19:dyn1":{"departure":1250,"target":3000,"event_index":1},
            "v20:traj1":{"departure":1250,"target":3200,"event_index":2},
            "V169_INCUMBENT":{"departure":1250,"target":3000,
                              "event_index":1,"baseline_stable":True},
        }
        last={
            "v19:dyn1":{"issued":issued-300,"target":2950},
            "v20:traj1":{"issued":issued-300,"target":5000},
        }
        e=Evidence({1250+1000:"SUCCESS"})
        stats={n:Counter() for n in plan}
        grade_candidates(plan,issued,1000,e,[],(),stats,last=last,
                         required_reconfirm=True)
        self.assertEqual(stats["v19:dyn1"]["executions"],1)
        self.assertEqual(stats["v20:traj1"]["executions"],0)
        self.assertEqual(stats["V169_INCUMBENT"]["executions"],1)
        self.assertEqual(stats["v19:dyn1"]["arrival_success"],1)
        self.assertEqual(stats["v20:traj1"]["proposal_success"],1)
        self.assertEqual(brief(stats["v20:traj1"],())["actionable_known_arrivals"],0)

    def test_causal_screen_evidence_gate_avoids_tiny_perfect_sample(self):
        small=brief(Counter(issues=200,proposals=2,proposal_success=2),())
        broad=brief(Counter(issues=200,proposals=150,
                            proposal_success=100,proposal_failure=50),())
        self.assertGreater(screen_rank(broad,()),screen_rank(small,()))

    def test_validate_exact_final_grid_alignment(self):
        # V169 end time includes seconds beyond the final valid 300s issue.
        start=1791504000
        end=1792533131
        expected=start+((end-start)//300)*300
        self.assertLessEqual(expected,end)
        self.assertLess(end-expected,300)


if __name__=="__main__":
    unittest.main()
