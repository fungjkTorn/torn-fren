"""Correct challenger choice logic before any historical accuracy replay."""
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from research.corrected_challengers import MODELS, forecast
from services.first_release_schedule import build_first_release_decision, FIRST_RELEASE_MODELS, native_timing_choice
from test_first_release_schedule import NOW, event, forecast as events
from test_first_release_schedule import FirstReleaseNativeTests as NativeFixture


class CorrectedChallengerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        NativeFixture.setUpClass()
        cls.tmp=tempfile.TemporaryDirectory()
        cls.source=Path(cls.tmp.name)/'challengers.sqlite'
        shutil.copyfile(NativeFixture.source,cls.source)
        with sqlite3.connect(cls.source) as con:
            rows=con.execute("SELECT timestamp,quantity,source FROM stock_history WHERE country='can' AND item_name='Crocus'").fetchall()
            for key in MODELS:
                country,item=key.split(':',1)
                con.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',[(t,country,item,q,s) for t,q,s in rows])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup();NativeFixture.tearDownClass()

    def decision(self,key,items,scorer=None,current=None):
        return build_first_release_decision(events(key,items,current),now=NOW,
            flight_seconds=1200,poll_age_seconds=0,timing_choice=scorer,model_roster=MODELS)

    def test_seven_research_models_no_rolling_restriction_no_live_roster_change(self):
        self.assertEqual(7,len(MODELS));self.assertEqual(10,len(FIRST_RELEASE_MODELS))
        self.assertTrue(set(MODELS).isdisjoint(FIRST_RELEASE_MODELS))
        self.assertTrue(all('@' not in c for g,c in MODELS.values()))
        self.assertEqual(('v20','traj12'),MODELS['sou:Lion Plushie'])

    def test_each_challenger_only_sees_first_reachable_window(self):
        for key in MODELS:
            seen=[]
            def scorer(**kw):
                seen.append(kw)
                return {'departure':NOW+kw['delays'][-1],'score':0}
            d=self.decision(key,[event(NOW+100,200),event(NOW+10000),event(NOW+20000)],scorer)
            self.assertEqual(2,d['selected_restock_event_index'])
            self.assertEqual(1,len(seen))
            self.assertGreater(min(seen[0]['delays']),300)  # Far future advice is eligible now.
            self.assertEqual(31,d['target_quantity']);self.assertEqual(0,d['arrival_grace_seconds'])
            self.assertLess(d['estimated_arrival_epoch'],NOW+11800)

    def test_missing_low_and_out_of_window_scores_never_skip_event(self):
        for key in MODELS:
            for scorer in (lambda **kw:None, lambda **kw:{'departure':NOW+kw['delays'][0],'score':0},
                           lambda **kw:{'departure':NOW+18800,'score':1}):
                d=self.decision(key,[event(NOW+10000),event(NOW+20000)],scorer)
                self.assertEqual(1,d['selected_restock_event_index'])
                self.assertEqual(NOW+8800,d['estimated_departure_epoch'])

    def test_current_stock_first_only_if_reachable(self):
        for key in MODELS:
            self.assertEqual(0,self.decision(key,[event(NOW+10000)],current=event(NOW-600,4000))['selected_restock_event_index'])
            self.assertEqual(1,self.decision(key,[event(NOW+10000)],current=event(NOW-600,900))['selected_restock_event_index'])

    def test_actual_native_engines_use_corrected_adapter_and_full_points(self):
        before=self.source.read_bytes()
        for key,(generation,config) in MODELS.items():
            from importlib import import_module
            engine=import_module('services.plushie_flower_dynamic_planner_'+generation)
            real_build=engine.build_points;built=[]
            def build(*args,**kwargs):
                points=real_build(*args,**kwargs);built.append(points);return points
            with self.subTest(key=key),patch.object(engine,'build_points',side_effect=build),patch.object(engine,'plan',wraps=engine.plan) as plan:
                row=forecast(self.source,key,NOW);d=row['decision']
                self.assertEqual((generation,config),(d['timing_model_generation'],d['timing_model_config']))
                self.assertEqual('FIRST_REACHABLE_EVENT_BEFORE_TIMING_SCORE',d['scheduling_policy'])
                reachable=[e for e in d['forecast_events'] if e['flight_reachable']]
                self.assertEqual(reachable[0]['index'],d['selected_restock_event_index'])
                self.assertTrue(plan.called)
                self.assertEqual(len(built[0]),len(plan.call_args.args[1]))
                self.assertIsNone(plan.call_args.args[6].lookback_points)
                self.assertTrue(row['timing_full_history_override'])
                self.assertEqual(0,plan.call_args.args[-1])
        self.assertEqual(before,self.source.read_bytes())

    def test_live_default_retains_its_original_training_configuration(self):
        from services import plushie_flower_dynamic_planner_v18 as engine
        expected=next(c for c in engine.configs() if c.name=='dyn3')
        with patch.object(engine,'plan',wraps=engine.plan) as plan:
            native_timing_choice(self.source,item_key='arg:Ceibo Flower',generation='v18',
                config='dyn3',now=NOW,min_quantity=31,flight_seconds=1200,delays=[8800])
        self.assertEqual(expected,plan.call_args.args[6])


if __name__=='__main__':unittest.main()
