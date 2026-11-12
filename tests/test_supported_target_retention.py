import sys
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from research.supported_target_retention import Band, Policy, WAIT, template_band, analog_band, observe_v20_plan, native_band


class RetentionTests(unittest.TestCase):
    def test_retains_only_current_supported_target_as_center_moves(self):
        p = Policy(0, 'retain_original_band')
        self.assertEqual(p.update(Band(0, 600, ((300, .8), (600, .8), (900, .8))), 0), 600)
        self.assertEqual(p.update(Band(300, 900, ((600, .8), (900, .8), (1200, .8))), 0), 600)
        self.assertEqual(p.update(Band(600, 1200, ((600, .8), (900, .8), (1200, .8))), 0), 615)

    def test_withdraws_old_target_if_band_moves_and_adopts_earlier_native(self):
        p = Policy(0, 'retain_original_band')
        p.update(Band(0, 900, ((600, .8), (900, .8))), 0)
        self.assertEqual(p.update(Band(300, 600, ((600, .8), (900, .8))), 0), 600)
        self.assertEqual(p.update(Band(600, 1200, ((1200, .8),)), 0), 1200)

    def test_source_expiry_and_model_abstention_clear_retention(self):
        p = Policy(0, 'retain_original_band')
        p.update(Band(0, 900, ((900, .9),)), 0)
        self.assertIsNone(p.update(Band(300, 1200, ((900, .9), (1200, .9))), 166))
        self.assertEqual(p.update(Band(600, 1200, ((900, .9), (1200, .9))), 0), 1200)
        self.assertIsNone(p.update(Band(900, None, ()), 0))

    def test_fallback_is_native_only_and_floor_is_current_score(self):
        b = Band(0, 0, ())
        self.assertEqual(Policy(0, 'native').update(b, 0), 15)
        self.assertIsNone(Policy(0, 'retain_original_band').update(b, 0))
        p = Policy(0, 'retain_original_band55')
        p.update(Band(0, 600, ((600, .7),)), 0)
        self.assertEqual(p.update(Band(300, 900, ((600, .54), (900, .8))), 0), 900)
        self.assertIsNone(p.update(Band(600, 1200, ((900, .5), (1200, .5))), 0))

    def test_fixed_deadline_and_passed_target_are_not_shifted(self):
        p = Policy(0, 'retain_original_band')
        p.update(Band(0, 300, ((300, .9),)), 0)
        self.assertIsNone(p.update(Band(600, None, ()), 0))
        self.assertIsNone(p.update(Band(WAIT, WAIT + 300, ((WAIT + 300, .9),)), 0))
        with self.assertRaises(ValueError):
            p.update(Band(WAIT, None, ()), 0)

    def test_invalid_band_and_future_target_rejected(self):
        for args in ((0, 300, ((600, .8),)), (0, 300, ((300, float('nan')),)),
                     (0, None, ((-300, .8),)), (0, 300, ((300, .8), (300, .8)))):
            with self.assertRaises(ValueError): Band(*args)


class NativeBandTests(unittest.TestCase):
    def test_all_supported_keeps_native_but_exposes_earlier_equal_score_window(self):
        import numpy as np
        from types import SimpleNamespace
        planner=SimpleNamespace(plan=lambda q:(q+1500,1.,{}))
        values=dict(delays=np.array([0,300,1200,1500,1800]),scores=np.ones(5))
        with patch('research.template_window_study.curve',return_value=values):
            original=template_band(planner,3000)
            earlier=template_band(planner,3000,all_supported=True)
        self.assertEqual(original.native,earlier.native)
        self.assertEqual(min(dict(original.points)),4200)
        self.assertEqual(min(dict(earlier.points)),3000)
        self.assertEqual(Policy(3000,'front_original_band').update(earlier,0),3015)

    def test_all_supported_does_not_relax_original_score_margin(self):
        import numpy as np
        from types import SimpleNamespace
        planner=SimpleNamespace(plan=lambda q:(q+1500,1.,{}))
        values=dict(delays=np.array([0,300,1200,1500,1800]),scores=np.array([.8,.8,1.,1.,1.]))
        with patch('research.template_window_study.curve',return_value=values):
            earlier=template_band(planner,3000,all_supported=True)
        self.assertEqual(min(dict(earlier.points)),4200)
        with self.assertRaisesRegex(ValueError,'bounded to Nessie'):
            native_band('unused','uae:Camel Plushie',3000,all_supported=True)

    def test_camel_whole_bank_matches_original_slow_winner(self):
        from research.template_window_study import GuardedTimeline
        from research.plushie_champions.common import DAY, TemplatePlanner
        from research.v38_camel_single_tick import EXPERTS
        q = 1792255500
        rows = []
        for t in range(q-10*DAY, q+1, 3600):
            rows.extend([(t, 0, 'a'), (t+1800, 100, 'a'), (t+2400, 0, 'a')])
        rows = sorted(r for r in rows if r[0] <= q)
        tl = GuardedTimeline(rows, [], 'uae:Camel Plushie', q)
        ctx = types.SimpleNamespace(timelines={('uae', 'Camel Plushie'): tl})
        candidates = [TemplatePlanner(ctx, 'uae', 'Camel Plushie', lags=lags,
            lookback=look, shift_range=shift).plan(q) for lags, look, shift in EXPERTS]
        original = max(candidates, key=lambda c: (c[1], c[2]['maxfit'], -c[0]))
        with tempfile.TemporaryDirectory() as d:
            db = Path(d)/'causal.sqlite'
            with sqlite3.connect(db) as c:
                c.executescript('CREATE TABLE stock_history(timestamp,country,item_name,quantity,source);'
                    'CREATE TABLE poll_heartbeats(timestamp);'
                    'CREATE TABLE collection_gaps(start_timestamp,end_timestamp);')
                c.executemany('INSERT INTO stock_history VALUES(?,?,?,?,?)',
                    [(t, 'uae', 'Camel Plushie', n, s) for t, n, s in rows])
            band = native_band(db, 'uae:Camel Plushie', q)
            self.assertEqual(band.native, int(original[0]))
            with sqlite3.connect(db) as c:
                c.execute('INSERT INTO collection_gaps VALUES(?,?)', (q-10, q+10))
            with self.assertRaisesRegex(ValueError, 'Future evidence'):
                native_band(db, 'uae:Camel Plushie', q)

    def test_template_band_matches_unmodified_slow_native(self):
        from research.template_window_study import GuardedTimeline
        from research.plushie_champions.common import DAY, TemplatePlanner
        from research.v46_fast_template import FastTemplatePlanner
        q = 1792255500
        rows = []
        for t in range(q - 10*DAY, q + 1, 3600):
            rows.extend([(t, 0, 'a'), (t+1800, 100, 'a'), (t+2400, 0, 'a')])
        tl = GuardedTimeline(sorted(rows), [], 'uni:Nessie Plushie', q)
        ctx = types.SimpleNamespace(timelines={('uni', 'Nessie Plushie'): tl})
        slow = TemplatePlanner(ctx, 'uni', 'Nessie Plushie', lags=(1,), minfit=.5)
        fast = FastTemplatePlanner(ctx, 'uni', 'Nessie Plushie', lags=(1,), minfit=.5)
        b = template_band(fast, q)
        self.assertEqual(b.native, int(slow.plan(q)[0]))
        self.assertTrue(b.points)
        self.assertIn(b.native, dict(b.points))

    def test_analog_band_matches_native_not_another_template_model(self):
        from tests.test_v103_champion_score_curves import ChampionCurveTests, Q
        model = ChampionCurveTests().analog()
        b = analog_band(model, Q)
        self.assertEqual(b.native, int(model.plan(Q)[0]))
        self.assertTrue(b.points)

    def test_v20_observes_actual_original_selection_and_restores_profiler(self):
        # History's unused network provider is disabled for this isolated import.
        provider = types.ModuleType('services.yata_api')
        provider.get_country_stock = lambda *a, **k: None
        # Keep the disabled provider installed throughout import and observation.
        with patch.dict(sys.modules, {'services.yata_api': provider}):
            self.check_v20_observation()

    def check_v20_observation(self):
        from services import plushie_flower_dynamic_planner_v20 as engine
        cfg = next(c for c in engine.configs() if c.name == 'traj12')
        points = [(0, types.SimpleNamespace(t=100+i*7200)) for i in range(12)]
        pack = points, [1.]*12, 12., 12.
        timeline = types.SimpleNamespace(success=lambda t, g: 1800 <= t % 7200 < 4800)
        def run():
            return engine.plan(100000., [], [], timeline, [], [], cfg,
                               list(range(0, 28801, 300)), 9600, 10)
        with patch.object(engine, 'context_at', return_value=object()), \
             patch.object(engine, '_trajectory_neighbors', return_value=pack):
            original = run()
            result, band = observe_v20_plan(run)
        self.assertEqual(result, original)
        self.assertEqual(band.native, int(original['departure_time']))
        self.assertIn(band.native, dict(band.points))
        self.assertIsNone(sys.getprofile())
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            observe_v20_plan(lambda: (_ for _ in ()).throw(RuntimeError('fixture')))
        self.assertIsNone(sys.getprofile())


if __name__ == '__main__': unittest.main()
