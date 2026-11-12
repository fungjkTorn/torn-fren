import unittest

from deploy.scripts import v163_readonly_event_first_preview as model
from research.causal_phase_analogs import PhaseAnalogs

T = 1791000000


class AnalogTests(unittest.TestCase):
    def tracker(self, rows, crosses=lambda a, b: False):
        a = PhaseAnalogs(crosses, neighbors=4, capacity=8)
        p = model._ReplayPhases(crosses)
        for row in rows:
            obs = model.OBS(*row)
            a.add(obs); p.add(obs)
        return a, p

    def rows(self):
        return [(T + i * 1200 + offset, q, 'yata')
                for i in range(16) for offset, q in ((0, 0), (600, 200), (900, 0))]

    def test_completed_only_bounded_and_predicts_all_future_events(self):
        rows = self.rows()
        a, p = self.tracker(rows)
        now = rows[-1][0] + 10
        f = a.forecast('mex:Jaguar Plushie', p.asof(), asof=now)
        self.assertEqual(f['model_name'], 'causal_item_phase_analogs_v1')
        self.assertEqual(f['history_stocked_phases'], 4)
        self.assertEqual(f['history_depleted_phases'], 4)
        self.assertGreater(len(f['restock_events']), 1)
        self.assertTrue(all(len(r) <= 8 for r in a.records.values()))
        self.assertTrue(all(r[2] <= now for rs in a.records.values() for r in rs))
        with self.assertRaises(ValueError):
            a.forecast('mex:Jaguar Plushie', p.asof(), asof=now-100)

    def test_benign_provider_switch_keeps_cycle_but_crossing_switch_invalidates(self):
        rows = [(T, 0, 'a'), (T+100, 200, 'a'), (T+150, 100, 'b'), (T+200, 0, 'b')]
        a, _ = self.tracker(rows)
        self.assertEqual(a.records[True][0][1], 100)
        bad, _ = self.tracker(rows[:-1]+[(T+200, 0, 'c')])
        self.assertFalse(bad.records[True])
        gap, _ = self.tracker(rows, crosses=lambda x, y: x <= T+175 <= y)
        self.assertFalse(gap.records[True])

    def test_future_mutation_cannot_change_frozen_forecast(self):
        rows = self.rows(); split = T+12*1200
        prefix = [r for r in rows if r[0] <= split]
        a, p = self.tracker(prefix)
        before = a.forecast('mex:Jaguar Plushie', p.asof(), asof=split)
        altered = [(t, 99999 if t > split else q, s) for t, q, s in rows]
        b, other = self.tracker([r for r in altered if r[0] <= split])
        self.assertEqual(before, b.forecast('mex:Jaguar Plushie', other.asof(), asof=split))

    def test_insufficient_history_abstains_and_invalid_limits_rejected(self):
        a, p = self.tracker([(T, 0, 'yata'), (T+100, 200, 'yata')])
        f = a.forecast('mex:Jaguar Plushie', p.asof(), asof=T+200)
        self.assertFalse(f['restock_events'])
        with self.assertRaises(ValueError): PhaseAnalogs(lambda a,b: False, neighbors=0)


if __name__ == '__main__': unittest.main()
