import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.full_roster_specialist_shadow import normalize,specialist,store,score,tick,capture


class SpecialistShadowTests(unittest.TestCase):
    def test_startup_wait_is_bounded_even_if_host_never_becomes_available(self):
        current=[0.0]
        def wait(seconds):current[0]+=seconds
        with tempfile.TemporaryDirectory() as td:
            with patch('research.v60_private_snapshot_probe.approved_collector_source',return_value=True), \
                 patch('research.full_roster_specialist_shadow.setup',return_value=Path(td)), \
                 patch('research.full_roster_specialist_shadow.tick',return_value=dict(status='ALL24_SHADOW_DEFERRED_CPU_PRESSURE')), \
                 patch('research.full_roster_specialist_shadow.time.time',side_effect=lambda:1000+int(current[0])):
                result=capture('unused',td,'pin',duration=60,startup_wait=60,clock=lambda:current[0],sleeper=wait)
            self.assertEqual(result['status'],'ALL24_STARTUP_WAIT_EXPIRED')
            self.assertFalse(result['collection_started']);self.assertEqual(current[0],60)

    def test_record_retries_deferral_without_spending_collection_window(self):
        current=[0.0];observed=[]
        def wait(seconds):current[0]+=seconds
        def cycle(*args):
            observed.append(current[0])
            return dict(status='ALL24_SHADOW_DEFERRED_CPU_PRESSURE' if len(observed)==1 else 'ALL24_SPECIALIST_SHADOW_RECORDED')
        with tempfile.TemporaryDirectory() as td:
            with patch('research.v60_private_snapshot_probe.approved_collector_source',return_value=True), \
                 patch('research.full_roster_specialist_shadow.setup',return_value=Path(td)), \
                 patch('research.full_roster_specialist_shadow.tick',side_effect=cycle), \
                 patch('research.full_roster_specialist_shadow.time.time',side_effect=lambda:1000+int(current[0])):
                capture('unused',td,'pin',duration=60,startup_wait=60,clock=lambda:current[0],sleeper=wait)
            self.assertEqual(observed,[0,30]);self.assertEqual(current[0],90)
            with sqlite3.connect(Path(td)/'plans.sqlite') as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM cycles').fetchone()[0],2)

    def test_preflight_deferral_returns_clean_status_without_exception(self):
        with tempfile.TemporaryDirectory() as td:
            with patch('research.v60_private_snapshot_probe.approved_collector_source',return_value=True), \
                 patch('research.full_roster_specialist_shadow.setup',return_value=Path(td)), \
                 patch('research.full_roster_specialist_shadow.tick',return_value=dict(status='ALL24_SHADOW_DEFERRED_CPU_PRESSURE')):
                result=capture('unused',td,'pin',once=True)
            self.assertEqual(result['status'],'ALL24_SHADOW_DEFERRED_CPU_PRESSURE')

    def test_past_targets_not_silently_shifted_to_publication(self):
        r=normalize(dict(departure=100,status='PLAN'),queried=100,published=120,heartbeat=90,flight=20)
        self.assertIsNone(r['departure']);self.assertEqual(r['status'],'DEPARTURE_PASSED_BEFORE_PUBLICATION')

    def test_source_must_be_fresh_at_departure_for_near_term_label(self):
        args=dict(queried=100,published=105,heartbeat=0,flight=20)
        self.assertFalse(normalize(dict(departure=190),**args)['executable_before_next_recheck'])
        self.assertTrue(normalize(dict(departure=150),**args)['executable_before_next_recheck'])
        args['published']=181
        self.assertIsNone(normalize(dict(departure=200),**args)['departure'])

    def test_eight_hour_limit_is_from_query_not_publication(self):
        r=normalize(dict(departure=100+28801),queried=100,published=110,heartbeat=90,flight=20)
        self.assertIsNone(r['departure'])

    def test_legacy_japan_never_invoked_or_disguised_as_zero_model(self):
        r=specialist('never-open-this.sqlite','jap:Xanax',100)
        self.assertIsNone(r['departure']);self.assertIn('INCOMPATIBLE',r['status'])

    def test_record_preserves_abstention_and_source_identity(self):
        with sqlite3.connect(':memory:') as c:
            c.execute('CREATE TABLE plans(issued,item_key,mode,record)')
            store(c,key='jap:Xanax',mode='control',raw=dict(departure=None,status='ABSTAIN'),
                  queried=100,published=105,heartbeat=90,sha='pin')
            r=json.loads(c.execute('SELECT record FROM plans').fetchone()[0])
            self.assertEqual(r['physical_depletion_quantity'],0)
            self.assertEqual(r['arrival_target'],30);self.assertFalse(r['website_publication'])
            self.assertIsNone(r['arrival']);self.assertEqual(r['model_sha'],'pin')

    def test_scoring_keeps_zero_eligibility_denominators_and_unknown_truth(self):
        class E:
            def score(self,t):return 'UNKNOWN',None,None
        with tempfile.TemporaryDirectory() as td:
            with sqlite3.connect(Path(td)/'plans.sqlite') as c:
                c.executescript("CREATE TABLE metadata(key,value);INSERT INTO metadata VALUES('model_sha','pin');CREATE TABLE plans(issued,item_key,mode,record);CREATE TABLE cycles(attempted_at,status,summary);INSERT INTO cycles VALUES(100,'ALL24_SPECIALIST_SHADOW_RECORDED','{}'),(400,'ALL24_SHADOW_DEFERRED_CPU_PRESSURE','{}');")
                for mode,dep in (('soon',130),('future',600)):
                    store(c,key='jap:Xanax',mode=mode,raw=dict(departure=dep,status='PLAN'),
                          queried=100,published=105,heartbeat=90,sha='pin')
            with patch('research.full_roster_specialist_shadow.source_data',return_value=(None,None,None,E(),1000)):
                report=score('not-opened',td,'pin');r=report['first_hourly_near_term_eligible']
            self.assertEqual(report['capture_attempt_statuses']['ALL24_SHADOW_DEFERRED_CPU_PRESSURE'],1)
            self.assertEqual(r['jap:Xanax|future']['proposal_coverage'],0)
            self.assertEqual(r['jap:Xanax|future']['NO_NEAR_TERM_ELIGIBILITY'],1)
            self.assertEqual(r['jap:Xanax|soon']['UNKNOWN'],1)
            self.assertIsNone(r['jap:Xanax|soon']['success_fraction'])

    def test_full_cycle_never_drops_items_or_japan_zero_challengers(self):
        original=specialist
        def worker(db,key,q):
            return original(db,key,q) if key=='jap:Xanax' else dict(departure=None,status='MODEL_ABSTAINED')
        with tempfile.TemporaryDirectory() as td, sqlite3.connect(':memory:') as c:
            c.execute('CREATE TABLE plans(issued,item_key,mode,record)')
            with patch('research.v65_private_mirror_shadow_tick.snapshot_with_retry',return_value=dict(status='PRIVATE_SNAPSHOT_READY',published=True)), \
                 patch('research.v38_capacity_guard.inspect',return_value=dict(allowed=True)), \
                 patch('research.full_roster_specialist_shadow.source_data',return_value=([],[],lambda a,b:False,None,995)), \
                 patch('research.full_roster_specialist_shadow.rate_plan',return_value=dict(departure=None,status='EMPTY')), \
                 patch('research.full_roster_specialist_shadow.time.time',return_value=1000), \
                 patch('research.full_roster_specialist_shadow.specialist',side_effect=worker):
                r=tick('unused',Path(td),'pin',c)
            self.assertEqual(c.execute('SELECT COUNT(DISTINCT item_key),COUNT(*) FROM plans').fetchone(),(24,216))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM plans WHERE item_key='jap:Xanax'").fetchone()[0],9)
            self.assertEqual(r['japan_zero_models_tested'],8)
            raw=c.execute("SELECT record FROM plans WHERE item_key='jap:Xanax' AND mode='specialist_control'").fetchone()[0]
            self.assertIn('INCOMPATIBLE',json.loads(raw)['status'])


if __name__=='__main__':unittest.main()
