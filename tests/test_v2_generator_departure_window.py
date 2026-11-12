"""Reproduce the generator/UI reachability disagreement with real V2 code."""
import unittest
from services import prediction_v2_live as v2
from services.v2_departure_window import departure_window
from research.v141_v2_feasible_departure_window import assess

N=1800000000


def make(now=N+60,life=1200,**updates):
    args=dict(number=1,estimate=N+600,window_start=N+540,window_end=N+660,
        arrival_offset=300,travel_seconds=900,reliability='good',
        evidence_tier='fixture',model_name='baseline_all_median',method='fixture',
        now=now,expected_stock_lifetime=life)
    args.update(updates)
    return v2._make_prediction(**args)


class GeneratorWindowTests(unittest.TestCase):
    def test_past_point_and_restock_window_do_not_discard_open_stocked_window(self):
        p=make()
        self.assertLess(p['recommended_leave_by_timestamp'],N+60)
        self.assertLess(p['window_end_timestamp']-p['travel_seconds'],N+60)
        self.assertTrue(p['usable_for_departure'])
        self.assertEqual(p['latest_safe_leave_timestamp'],N+780)
        self.assertEqual(p['estimate_timestamp'],N+600)
        self.assertEqual(assess(p,now=N+60)['latest_departure_epoch'],N+780)
        self.assertEqual(v2._select_active_forecast([p]),p)

    def test_true_window_expiry_negative_window_and_unknown_lifetime_do_not_become_go(self):
        self.assertFalse(make(now=N+781)['usable_for_departure'])
        self.assertFalse(make(life=300)['usable_for_departure'])
        self.assertFalse(make(life=None)['usable_for_departure'])

    def test_annotation_and_generator_use_identical_clock_not_wall_time(self):
        p=make(life=None)
        v2._annotate_target_depletion([p],1200,now=N+60)
        self.assertTrue(p['usable_for_departure'])
        self.assertEqual(departure_window(p),departure_window(make()))
        v2._annotate_target_depletion([p],1200,now=N+781)
        self.assertFalse(p['usable_for_departure'])

    def test_first_reachable_cycle_is_not_skipped_for_later_projection(self):
        p1=make()
        p2=make(number=2,estimate=N+5000,window_start=N+4940,window_end=N+5060)
        self.assertEqual(v2._select_active_forecast([p1,p2])['prediction_number'],1)


if __name__=='__main__':unittest.main()
