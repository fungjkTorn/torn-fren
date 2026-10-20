import json
import io
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
from research.full_roster_specialist_shadow import normalize,specialist,store,score,tick,capture,status,capture_inputs,source_data,main


class SpecialistShadowTests(unittest.TestCase):
    def test_frozen_compact_prints_future_forecasts_not_zero_near_term_subset(self):
        from deploy.scripts.v163_readonly_event_first_preview import exact_roster
        groups={k+'|specialist_control':dict(SUCCESS=2,known=3,proposals=4,hourly_opportunities=5,UNKNOWN=1,PENDING=0)
                for k in exact_roster()}
        result=dict(first_hourly_frozen=groups,first_hourly_near_term_eligible={},
            capture_diagnostics=dict(models={k+'|specialist_control':dict(statuses={}) for k in exact_roster()},
                complete24_row_batches=1,incomplete_row_batches=[],active_window_observed_hours=1,active_hours_without_any_capture=[]),
            records=216,truth_cutoff=1000,capture_attempt_statuses={})
        for flag,expected in (('--frozen-compact',' | 2/3 4/5 1/0 | '),('--compact',' | 0/0 0/0 0/0 | ')):
            output=io.StringIO()
            with patch.object(sys,'argv',['shadow','score','--state','unused','--model-sha','pin',flag]), \
                 patch('research.full_roster_specialist_shadow.subprocess.check_output',return_value='new-scorer-pin'), \
                 patch('research.full_roster_specialist_shadow.score',return_value=result),redirect_stdout(output):
                main()
            self.assertIn('chi:Panda Plushie'+expected,output.getvalue())
            if flag=='--frozen-compact':self.assertIn('FROZEN forecast',output.getvalue())

    def test_batch_capture_matches_individual_readers_without_source_writes(self):
        from deploy.scripts.v163_readonly_event_first_preview import exact_roster
        keys=sorted(exact_roster())
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.sqlite'
            with sqlite3.connect(source) as c:
                c.executescript('CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT);'
                    'CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER);'
                    'CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER);')
                c.executemany('INSERT INTO poll_heartbeats VALUES(?,?,1)',[(q,'poll-cycle') for q in range(100,1001,30)])
                c.executemany('INSERT INTO collection_gaps VALUES(?,?)',[(350,400),(900,None),(1100,1200)])
                for key in keys:
                    country,item=key.split(':',1)
                    c.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',
                        [(q,country,item,n,'a') for q,n in ((100,0),(300,100),(500,20),(600,0),(1100,999))])
            before=source.read_bytes()
            batch,crosses,cutoff=capture_inputs(source,keys,now=1000)
            self.assertEqual(cutoff,1000)
            for key in keys:
                rows,polls,old_crosses,_,old_cutoff=source_data(source,now=1000,item_key=key)
                self.assertEqual((batch[key],cutoff),(rows,old_cutoff))
                for a,b in ((100,200),(300,400),(400,500),(900,950),(1000,1100)):
                    self.assertEqual(crosses(a,b),old_crosses(a,b))
            self.assertEqual(source.read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'Exact24'):
                capture_inputs(source,keys[:-1],now=1000)
            with sqlite3.connect(source) as c:
                c.execute("UPDATE stock_history SET quantity=-1 WHERE country='jap'")
            with self.assertRaisesRegex(ValueError,'Invalid stock'):
                capture_inputs(source,keys,now=1000)

    def test_vm_staged_research_cannot_replace_checkout_before_source_data(self):
        root=Path(__file__).resolve().parents[1]
        child='''import os,pathlib
from research import full_roster_specialist_shadow as shadow
# This is the actual tick's import order, BEFORE source_data runs.
from deploy.scripts import v163_readonly_event_first_preview
import research
from research import continuous_departure_replay as replay
root=pathlib.Path(shadow.__file__).resolve().parents[1]
assert list(research.__path__)==[str(root/'research')]
assert pathlib.Path(replay.__file__).resolve()==root/'research/continuous_departure_replay.py'
assert os.environ['TORNFREN_REPLAY_PINNED_RESEARCH']==str(root/'research')
print('CHECKOUT_IMPORTS_OK')
'''
        with tempfile.TemporaryDirectory() as td:
            stale=Path(td)/'research';stale.mkdir()
            env=dict(os.environ,TORNFREN_REPLAY_WORK=td,TORNFREN_REPLAY_PINNED_RESEARCH=str(stale))
            result=subprocess.run([sys.executable,'-B','-c',child],cwd=root,env=env,
                                  capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('CHECKOUT_IMPORTS_OK',result.stdout)

    def test_failed_partial_cycle_never_exposes_an_incomplete_roster(self):
        def interrupted(source,state,sha,db):
            store(db,key='jap:Xanax',mode='rate',raw=dict(departure=130,status='PLAN'),
                  queried=100,published=105,heartbeat=90,sha=sha,commit=False)
            raise ValueError('Source expired before remaining items')
        with tempfile.TemporaryDirectory() as td:
            with patch('research.v60_private_snapshot_probe.approved_collector_source',return_value=True), \
                 patch('research.full_roster_specialist_shadow.setup',return_value=Path(td)), \
                 patch('research.full_roster_specialist_shadow.tick',side_effect=interrupted):
                r=capture('unused',td,'pin',once=True)
            self.assertEqual(r['status'],'FULL_ROSTER_CAPTURE_UNAVAILABLE')
            with sqlite3.connect(Path(td)/'plans.sqlite') as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM plans').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM cycles').fetchone()[0],1)

    def test_status_reads_real_journal_schema_without_modifying_or_admitting_it(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'shadow-source.json').write_text(json.dumps(dict(model_sha='pin')))
            (root/'capture.lock').touch()
            with sqlite3.connect(root/'plans.sqlite') as c:
                c.executescript("CREATE TABLE plans(issued,item_key,mode,record);CREATE TABLE cycles(attempted_at,status,summary);")
                store(c,key='jap:Xanax',mode='rate',raw=dict(departure=130,status='PLAN'),queried=100,published=105,heartbeat=90,sha='pin')
            before=(root/'plans.sqlite').read_bytes()
            with patch('research.v38_idle_admission.inspect',return_value=dict(allowed=True,idle_fraction=.8)):
                r=status(root,'pin')
            self.assertEqual(r['last_publication'],105);self.assertEqual(r['recorded_items'],1)
            self.assertFalse(r['recorder_running']);self.assertEqual(r['measured_cpu_diagnostics_only'],dict(idle_fraction=.8))
            self.assertEqual((root/'plans.sqlite').read_bytes(),before)

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
                for mode,dep in (('paired_recent_peak',130),('sequence_blocks_peak',600)):
                    store(c,key='jap:Xanax',mode=mode,raw=dict(departure=dep,status='PLAN'),
                          queried=100,published=105,heartbeat=90,sha='pin')
            with patch('research.full_roster_specialist_shadow.source_data',return_value=(None,None,None,E(),1000)):
                report=score('not-opened',td,'pin');r=report['first_hourly_near_term_eligible']
            self.assertEqual(report['capture_attempt_statuses']['ALL24_SHADOW_DEFERRED_CPU_PRESSURE'],1)
            self.assertEqual(r['jap:Xanax|sequence_blocks_peak']['proposal_coverage'],0)
            self.assertEqual(r['jap:Xanax|sequence_blocks_peak']['NO_NEAR_TERM_ELIGIBILITY'],1)
            self.assertEqual(r['jap:Xanax|paired_recent_peak']['UNKNOWN'],1)
            self.assertIsNone(r['jap:Xanax|paired_recent_peak']['success_fraction'])
            self.assertFalse(report['capture_diagnostics']['complete_footprints'])

    def test_score_rejects_sql_and_encoded_identity_mismatch_before_truth_reads(self):
        with tempfile.TemporaryDirectory() as td:
            with sqlite3.connect(Path(td)/'plans.sqlite') as c:
                c.executescript("CREATE TABLE metadata(key,value);INSERT INTO metadata VALUES('model_sha','pin');CREATE TABLE plans(issued,item_key,mode,record);")
                store(c,key='jap:Xanax',mode='rate_current_quarter',raw=dict(departure=None,status='ABSTAIN'),
                      queried=100,published=105,heartbeat=90,sha='pin')
                c.execute('UPDATE plans SET issued=200');c.commit()
            with patch('research.full_roster_specialist_shadow.source_data') as truth:
                with self.assertRaisesRegex(ValueError,'identity mismatch'):score('unused',td,'pin')
                truth.assert_not_called()

    def test_full_cycle_never_drops_items_or_japan_zero_challengers(self):
        from deploy.scripts.v163_readonly_event_first_preview import exact_roster
        original=specialist
        def worker(db,key,q):
            return original(db,key,q) if key=='jap:Xanax' else dict(departure=None,status='MODEL_ABSTAINED')
        with tempfile.TemporaryDirectory() as td, sqlite3.connect(':memory:') as c:
            c.execute('CREATE TABLE plans(issued,item_key,mode,record)')
            with patch('research.v65_private_mirror_shadow_tick.snapshot_with_retry',return_value=dict(status='PRIVATE_SNAPSHOT_READY',published=True)), \
                 patch('research.v38_capacity_guard.inspect',return_value=dict(allowed=True)), \
                 patch('research.full_roster_specialist_shadow.capture_inputs',return_value=({k:[] for k in exact_roster()},lambda a,b:False,995)), \
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
