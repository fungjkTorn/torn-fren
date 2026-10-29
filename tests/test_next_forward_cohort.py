"""Candidate preparation preserves exact models and the operation sequence."""
from functools import partial
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from research.next_forward_cohort import CANDIDATE_MODELS,preview
from services.first_release_schedule import FIRST_RELEASE_MODELS,build_first_release_decision,native_timing_choice
from test_first_release_schedule import NOW,FirstReleaseNativeTests,forecast,event


class NextCohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FirstReleaseNativeTests.setUpClass();cls.scratch=tempfile.TemporaryDirectory()
        cls.source=Path(cls.scratch.name)/'candidates.sqlite';shutil.copyfile(FirstReleaseNativeTests.source,cls.source)
        with sqlite3.connect(cls.source) as db:
            rows=db.execute("SELECT timestamp,quantity,source FROM stock_history WHERE country='can' AND item_name='Crocus'").fetchall()
            for key in CANDIDATE_MODELS:
                country,item=key.split(':',1)
                db.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',[(t,country,item,q,s) for t,q,s in rows])
    @classmethod
    def tearDownClass(cls):cls.scratch.cleanup();FirstReleaseNativeTests.tearDownClass()

    def test_default_live_roster_stays_ten_and_rejects_candidates(self):
        self.assertEqual(10,len(FIRST_RELEASE_MODELS));self.assertTrue(set(FIRST_RELEASE_MODELS).isdisjoint(CANDIDATE_MODELS))
        with self.assertRaises(ValueError):build_first_release_decision(forecast('chi:Peony',[event(NOW+10000)]),now=NOW,flight_seconds=1200,poll_age_seconds=0)

    def test_first_reachable_event_cannot_be_skipped_for_low_timing_score(self):
        for key in CANDIDATE_MODELS:
            for scorer in (lambda **kw:None,lambda **kw:{'departure':NOW+kw['delays'][0],'score':0}):
                with self.subTest(key=key):
                    d=build_first_release_decision(forecast(key,[event(NOW+100,200),event(NOW+2400),event(NOW+10000)]),now=NOW,flight_seconds=1200,poll_age_seconds=0,timing_choice=scorer,model_roster=CANDIDATE_MODELS)
                    self.assertEqual(2,d['selected_restock_event_index']);self.assertEqual(NOW+1200,d['estimated_departure_epoch'])
                    self.assertEqual(31,d['target_quantity']);self.assertEqual(0,d['arrival_grace_seconds'])

    def test_exact_native_models_and_readonly_pipeline_for_all_four(self):
        before=self.source.read_bytes()
        for key,identity in CANDIDATE_MODELS.items():
            with self.subTest(key=key):
                result=preview(self.source,key,issued=NOW);d=result['decision']
                reachable=[e for e in d['forecast_events'] if e['flight_reachable']]
                self.assertTrue(reachable);self.assertEqual(reachable[0]['index'],d['selected_restock_event_index'])
                self.assertEqual(identity,(d['timing_model_generation'],d['timing_model_config']))
                self.assertFalse(result['live_roster_changed']);self.assertFalse(result['accuracy_evidence'])
                self.assertEqual(31,result['forecast']['arrival_stock_threshold'])
        self.assertEqual(before,self.source.read_bytes())

    def test_peony_v20_uses_gap_aware_timeline_and_features(self):
        from services import plushie_flower_dynamic_planner_v20 as engine
        real=engine.Timeline
        with patch.object(engine,'Timeline',wraps=real) as timeline:
            native_timing_choice(self.source,model_roster=CANDIDATE_MODELS,item_key='chi:Peony',generation='v20',config='traj12',now=NOW,min_quantity=31,flight_seconds=1200,delays=[8800])
            self.assertIn('gaps',timeline.call_args.kwargs)

if __name__=='__main__':unittest.main()
