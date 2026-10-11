"""V92 stress/robustness contract for future full-roster travel selection.

Runs in GitHub CI with *synthetic* opportunity data; does not ask YATA,
execute VM jobs, or replace real model artifacts. Timings are smoke budgets,
not hardware comparisons with the production VM.
"""
import time
import unittest
from dataclasses import replace

from research import v91_travel_decision_contract as policy

NOW=1791650000


class FullRosterScaleTests(unittest.TestCase):
    def candidates(self, items=236, options=48):
        for i in range(items):
            key=f"mex:Stress Item {i} Plushie"
            for j in range(options):
                delay=j*300 # 0..235 minutes, includes immediate and later.
                yield policy.Opportunity(
                    item_key=key,model_id=f"candidate_{j}",
                    issued_at=NOW-30,stock_as_of=NOW-50,
                    valid_until=NOW+270,
                    depart_at=NOW+delay,arrive_at=NOW+delay+1020,
                    category="plushies",
                    threshold=30,grace_seconds=10,
                    projected_stock_floor=30+((i+j*13)%2450),
                    projected_survival_minutes=((i+j)%180)*1.0,
                    evidence_tier="research",
                )

    def test_more_than_11000_options_remain_bounded_and_nonactionable(self):
        candidates=list(self.candidates())
        self.assertEqual(len(candidates),11328)
        before=time.perf_counter()
        response=policy.evaluate_views(candidates,now=NOW)
        elapsed=time.perf_counter()-before
        print("V92_SELECTION_BENCHMARK",round(elapsed,3),"seconds",
              len(candidates),"candidates",flush=True)
        self.assertLess(elapsed,15,
                        "Research selection too slow for a bounded CI smoke")
        self.assertEqual(response["valid_candidate_count"],len(candidates))
        for name in ("leave_now","next_opportunity","best_chance"):
            self.assertEqual(len(response[name]),236,name)
            self.assertEqual(len({p["item_key"] for p in response[name]}),236)
            self.assertTrue(all(p["experimental"] and not p["accuracy_verified"]
                                for p in response[name]))
        self.assertEqual(response["next_opportunity"][0]["wait_seconds"],0)
        self.assertEqual(response["leave_now"][0]["wait_seconds"],0)

    def test_stale_candidates_do_not_hide_current_candidates(self):
        c=list(self.candidates(2,3))
        stale=replace(c[0],model_id="stale",stock_as_of=NOW-1000)
        invalid=replace(c[0],status="OLD_RETRACTED")
        mixed=[stale,invalid,None,{"item_key":"mex:Oops"},*c]
        result=policy.evaluate_views(mixed,now=NOW)
        self.assertEqual(result["valid_candidate_count"],6)
        self.assertEqual(sum(result["excluded_by_reason"].values()),4)
        self.assertEqual(len(result["next_opportunity"]),2)

    def test_filtering_and_adjustable_quick_limit_scale(self):
        rows=list(self.candidates(50,40))
        quick=policy.evaluate_views(rows,now=NOW,quick_seconds=0,category="plushies")
        self.assertEqual(len(quick["leave_now"]),50)
        self.assertTrue(all(p["wait_seconds"]==0 for p in quick["leave_now"]))
        no=policy.evaluate_views(rows,now=NOW,category="medical")
        self.assertEqual(no["next_opportunity"],[])
        self.assertEqual(no["leave_now"],[])


if __name__=="__main__":
    unittest.main()
