import unittest
from research.japan_xanax.recent_regime import combine,unique_departures,select_curve
from research.japan_xanax.renewal_shadow import History


class RecentTests(unittest.TestCase):
    def test_short_memory_has_only_past_cycles_and_defaults_unchanged(self):
        from test_renewal_shadow import rows,T
        h=History(lambda a,b:False)
        for r in rows():h.add(r)
        self.assertEqual(h.plans(T,poll_age=0),h.plans(T,poll_age=0,cycle_limit=96,half_life_seconds=259200))
        p=h.plans(T,poll_age=0,cycle_limit=16,half_life_seconds=21600)
        for v in p.values():
            if 'completed_cycles' in v:
                self.assertEqual(v['completed_cycles'],16);self.assertLessEqual(v['latest_training_cycle_end'],T)
        with self.assertRaises(ValueError):h.plans(T,poll_age=0,cycle_limit=15)
        with self.assertRaises(ValueError):h.plans(T,poll_age=0,half_life_seconds=0)

    def test_combination_keeps_missing_history_in_confidence_denominator(self):
        curve=dict(delays=[0,60],support=[.1,.9])
        p=combine(30,{'recent16_6h':60},{'recent16_6h':curve},0)
        self.assertEqual(p['fallback_recent16_6h'],30)
        self.assertEqual(p['recent_mean_peak'],60);self.assertIsNone(p['recent_mean_45'])
        self.assertIsNone(select_curve(None,0))
        self.assertTrue(all(v is None for v in combine(None,{'recent16_6h':None},{},0).values()))

    def test_correlated_start_counts_do_not_become_independent_flights(self):
        c=[dict(start=0,wait=60,outcome='SUCCESS'),dict(start=30,wait=30,outcome='SUCCESS'),dict(start=90,wait=None,outcome='ABSTAIN')]
        r=unique_departures(c);self.assertEqual(r['distinct_departure_epochs'],1)
        self.assertEqual(r['distinct_outcomes'],{'SUCCESS':1});self.assertFalse(r['independent_samples'])
        with self.assertRaises(ValueError):unique_departures(c+[dict(start=60,wait=0,outcome='FAILURE')])


if __name__=='__main__':unittest.main()
