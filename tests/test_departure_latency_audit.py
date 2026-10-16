import json
import tempfile
import unittest
from pathlib import Path
from research.departure_latency_audit import outcome,assess,audit


class LatencyTests(unittest.TestCase):
    def test_strict_point_expires_while_late_arm_is_measured_at_actual_arrival(self):
        seen=[]
        def score(t):seen.append(t);return ('SUCCESS',None,None)
        self.assertEqual(outcome(1000,1000,10,delay=30,flight=600,score=score),('MISSED_POINT',None))
        self.assertEqual(seen,[])
        self.assertEqual(outcome(1000,1000,10,delay=30,flight=600,score=score,allow_late=True),('SUCCESS',30))
        self.assertEqual(seen,[1630])

    def test_old_source_expiry_future_plan_abstention_and_unknown_are_separate(self):
        score=lambda t:('UNKNOWN',None,None)
        for dep,age,delay,late,status in ((None,10,0,False,'ABSTAIN'),
                (1400,10,0,False,'FUTURE_RECHECK'),(1000,160,30,True,'STALE'),
                (1120,10,30,False,'UNKNOWN'),(1000,0,300,True,'STALE')):
            self.assertEqual(outcome(1000,dep,age,delay=delay,flight=600,score=score,allow_late=late)[0],status)

    def test_latency_does_not_hide_losses_or_count_unknown_as_failure(self):
        score=lambda t:('SUCCESS' if t==1600 else 'FAILURE',None,None)
        r=assess([(1000,1000,10)],flight=600,score=score)
        self.assertEqual(r['arms']['strict_30s']['MISSED_POINT'],1)
        self.assertEqual(r['arms']['late_counterfactual_30s']['FAILURE'],1)
        self.assertEqual(r['paired_late_vs_zero_latency']['30']['baseline_only_success'],1)
        self.assertIsNone(r['arms']['strict_30s']['success_fraction'])
        self.assertEqual(r['arms']['strict_30s']['actionable_fraction'],0)

    def test_real_readonly_replay_preserves_data_and_does_not_promote(self):
        import test_continuous_departure_replay as fixtures
        from unittest.mock import patch
        from research.causal_stock_paths import CausalStockPaths
        with tempfile.TemporaryDirectory() as td:
            db=fixtures.ContinuousTests().fixture(Path(td));before=db.read_bytes()
            assignments={k:{'departure_policy':'disabled'} for k in fixtures.m.model.exact_roster()}
            assignments['mex:Jaguar Plushie']={'departure_policy':'zero_path_analog70'}
            original=CausalStockPaths.plans
            def causal(instance,issued,tracker,*,poll_age):
                self.assertLessEqual(tracker.last.epoch,issued)
                return original(instance,issued,tracker,poll_age=poll_age)
            with patch.object(CausalStockPaths,'plans',causal):r=audit(source=db,assignments=assignments,model_sha='a'*40,days=1)
            self.assertEqual(db.read_bytes(),before)
            self.assertFalse(r['automatic_promotion'])
            item=r['items']['mex:Jaguar Plushie']
            self.assertTrue(all(x['issues']==288 for x in item['arms'].values()))
            self.assertEqual(r['physical_depletion_quantity'],0)
