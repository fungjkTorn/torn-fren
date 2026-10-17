import json
import tempfile
import unittest
from pathlib import Path
from research.departure_latency_audit import outcome,assess,audit


class LatencyTests(unittest.TestCase):
    def test_actual_consumer_matches_fixed_late_arm_up_to_thirty_seconds(self):
        from services.departure_recommendation import project_recommendation
        # The actual analog departure grid is 120 seconds. Only original
        # delay-zero points can be missed by a <=30s publication delay.
        for offset in (0,120,240,360,None):
            for age in (0,10,150,170,181):
                for delay in (0,5,15,30):
                    dep=1000+offset if offset is not None else None
                    record={'item_key':'mex:Jaguar Plushie','asof_epoch':1000,'model_sha':'a'*40,
                        'policy':'zero_path_analog70','model_name':'causal_complete_stock_paths_v1',
                        'player_flight_seconds':1020,'target_quantity':30,'depletion_stock_quantity':0,
                        'event_timing_prediction_supported':False,'departure_epoch':dep,
                        'execution_policy':'publication_delay_30s_v1'}
                    d=project_recommendation(record,item_key=record['item_key'],issued=1000,
                        model_sha='a'*40,now=1000+delay,poll_age_seconds=age+delay,
                        player_flight_seconds=1020)
                    kind,wait=outcome(1000,dep,age,delay=delay,flight=1020,
                        score=lambda t:('SUCCESS',None,None),allow_late=True)
                    if kind=='SUCCESS':
                        self.assertEqual(d['estimated_departure_epoch'],1000+wait)
                        self.assertEqual(d['estimated_arrival_epoch'],1000+wait+1020+10)
                    elif kind=='STALE':
                        self.assertTrue(d['estimated_departure_epoch'] is None or
                            d['estimated_departure_epoch']>d['valid_until_epoch'])
                    if offset not in (0,None):self.assertEqual(d['publication_tolerance_seconds'],0)

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
