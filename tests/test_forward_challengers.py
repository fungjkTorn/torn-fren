import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from services.forward_beta_roster import CHALLENGER_MODELS
from services.first_release_schedule import FIRST_RELEASE_MODELS
from services.first_release_live import publish
from services.challenger_live import bootstrap
from web.first_release_bridge import read_board
from deploy.scripts import add_forward_challengers as installer


class ForwardChallengerTests(unittest.TestCase):
    def snapshot(self,roster,sha='a'*40,now=None):
        now=int(time.time()) if now is None else now
        return {'schema_version':1,'status':'LIVE_BETA','model_sha':sha,'asof_epoch':now,'published_epoch':now,
            'valid_until_epoch':now+180,'source_heartbeat_epoch':now,'stock_success_rule':'quantity > 30 at calculated landing',
            'flight_profile':'PI + pilot','historical_accuracy_included':False,
            'items':{key:{'item_key':key,'timing_full_history_override':True,'decision':{'estimated_departure_epoch':now,'estimated_arrival_epoch':now+100,'timing_model_generation':roster[key][0],'timing_model_config':roster[key][1]}} for key in roster},
            'live_metrics':{key:{'evidence_policy':'RECOMMENDED_DEPARTURE_FREEZE_V5','target_identity_audit':{'duplicate_target_groups':0},'success_fraction':None,'trips':[]} for key in roster}}

    def test_combined_feed_keeps_versions_rates_and_expiry_separate(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);original=self.snapshot(FIRST_RELEASE_MODELS,now=1000);extra=self.snapshot(CHALLENGER_MODELS,'b'*40,now=1000)
            extra['valid_until_epoch']=1050
            (p/'main.json').write_text(json.dumps(original));(p/'extra.json').write_text(json.dumps(extra))
            board=read_board(now=1100,path=p/'main.json',challenger_path=p/'extra.json')
            self.assertEqual(16,len(board['rows']));self.assertEqual('LIVE_BETA',board['status'])
            for row in board['rows']:
                added=row['item_key'] in CHALLENGER_MODELS
                self.assertEqual(('b' if added else 'a')*40,row['model_sha'])
                self.assertEqual(None if added else 1000,row['decision']['estimated_departure_epoch'])
                self.assertIsNone(row['live']['success_fraction'])
            extra['items'].pop(next(iter(extra['items'])))
            (p/'extra.json').write_text(json.dumps(extra))
            board=read_board(now=1100,path=p/'main.json',challenger_path=p/'extra.json')
            self.assertEqual(10,len(board['rows']));self.assertEqual('UNAVAILABLE',board['cohorts']['challengers']['status'])

    def test_source_bootstrap_has_all_history_only_for_six_and_preserves_collector(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);source=p/'collector.sqlite';now=int(time.time())
            with sqlite3.connect(source) as db:
                db.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                    CREATE TABLE poll_heartbeats(id INTEGER PRIMARY KEY,timestamp,mode,success);
                    CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
                    CREATE TABLE country_stock_observations(id INTEGER PRIMARY KEY,received_epoch,country,source,country_update_epoch,clock_status);
                    CREATE TABLE api_secrets(secret); INSERT INTO api_secrets VALUES('fixture-only');''')
                for key in CHALLENGER_MODELS:
                    country,item=key.split(':',1)
                    for t in (now-200*86400,now-10):
                        db.execute('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,1000,\'p\')',(t,country,item))
                    db.execute("INSERT INTO country_stock_observations(received_epoch,country,source,country_update_epoch,clock_status) VALUES(?,?,'p',?,'REPORTED')",(now-10,country,now-10))
                db.execute("INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,'uni','Xanax',2500,'p')",(now-10,))
                db.execute("INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,'poll-cycle',1)",(now-10,))
            before=source.read_bytes();result=bootstrap(source,p/'private.sqlite')
            self.assertFalse(result['history_truncated']);self.assertEqual(before,source.read_bytes())
            with sqlite3.connect(p/'private.sqlite') as db:
                self.assertEqual(12,db.execute('SELECT COUNT(*) FROM stock_history').fetchone()[0])
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='api_secrets'").fetchone())
                self.assertEqual(0,db.execute("SELECT COUNT(*) FROM stock_history WHERE country='uni'").fetchone()[0])

    def test_six_worker_arguments_retain_full_history_and_existing_ten_identity(self):
        self.assertEqual(10,len(FIRST_RELEASE_MODELS));self.assertEqual(6,len(CHALLENGER_MODELS))
        self.assertFalse(set(FIRST_RELEASE_MODELS)&set(CHALLENGER_MODELS))
        self.assertEqual(('v20','traj12'),CHALLENGER_MODELS['sou:Lion Plushie'])
        from test_first_release_schedule import FirstReleaseNativeTests
        FirstReleaseNativeTests.setUpClass()
        try:
            source=FirstReleaseNativeTests.source
            # The normal native fixture includes all challenger histories.
            # This verifies the child receives the approved cohort flag while
            # keeping inference isolated in the real subprocess.
            import services.first_release_live as live
            original_run=live.subprocess.run;commands=[]
            def child(args,**kwargs):commands.append(args);return original_run(args,**kwargs)
            with tempfile.TemporaryDirectory() as td,patch.object(live.subprocess,'run',side_effect=child):
                result=publish(source,Path(td),model_sha='c'*40,clock=lambda:1790000000,
                    model_roster=CHALLENGER_MODELS,challenger_cohort=True,time_budget_seconds=90,item_timeout_seconds=45)
                data=json.loads((Path(td)/'latest.json').read_text())
                self.assertEqual(6,result['items']);self.assertEqual(6,len(commands))
                self.assertTrue(all('--challenger-cohort' in command for command in commands))
                self.assertTrue(all(row['timing_full_history_override'] for row in data['items'].values()))
                for key,row in data['items'].items():
                    self.assertEqual(CHALLENGER_MODELS[key],(row['decision']['timing_model_generation'],row['decision']['timing_model_config']))
        finally:FirstReleaseNativeTests.tearDownClass()

    def test_accelerated_six_forecasts_equal_uncached_native_outputs(self):
        from contextlib import nullcontext
        from test_first_release_schedule import FirstReleaseNativeTests
        from services.first_release_schedule import forecast_first_release_item
        from research.plushie_champions.common import TRAVEL_SECONDS
        FirstReleaseNativeTests.setUpClass()
        try:
            for key in CHALLENGER_MODELS:
                args=dict(now=1790000000,flight_seconds=TRAVEL_SECONDS[key.split(':')[0]],
                    model_roster=CHALLENGER_MODELS,timing_full_history=True)
                with patch('services.native_history_acceleration.immutable_history_queries',side_effect=lambda h:nullcontext()):
                    baseline=forecast_first_release_item(FirstReleaseNativeTests.source,key,**args)
                accelerated=forecast_first_release_item(FirstReleaseNativeTests.source,key,**args)
                self.assertEqual(baseline,accelerated,key)
        finally:FirstReleaseNativeTests.tearDownClass()

    def deployment_fixture(self,p):
        state=p/'state';state.mkdir();root=p/'app';root.mkdir();base=p/'base';base.mkdir()
        unit=p/'new.service';timer=p/'new.timer';primary=p/'primary.service';primary.write_text('original ten unit')
        originals={};expected={}
        for name in installer.EXPECTED:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('old '+name+'\nsecond line\n')
            originals[name]=path.read_bytes();expected[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        (base/'latest.json').write_text(json.dumps(self.snapshot(FIRST_RELEASE_MODELS)))
        with sqlite3.connect(state/'stock_history.sqlite') as db:
            db.execute('CREATE TABLE poll_heartbeats(timestamp,mode,success)');db.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(int(time.time()),))
        archive=p/'release.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name in expected:z.writestr(name,'new '+name)
            z.writestr('services/example.py','X=1\n')
        def run(args,timeout=30):
            if args[0]=='systemd-run':
                target=Path(args[args.index('--state')+1]);(target/'latest.json').write_text(json.dumps(self.snapshot(CHALLENGER_MODELS,'b'*40)))
                return json.dumps({'elapsed_seconds':10,'items':6})
            if args==['systemctl','start',unit.name]:(state/'latest.json').write_text(json.dumps(self.snapshot(CHALLENGER_MODELS,'b'*40)))
            return ''
        patches=[patch.object(installer,name,value) for name,value in dict(BASE=base,STATE=state,ROOT=root,UNIT=unit,TIMER=timer,PRIMARY=primary,EXPECTED=expected,BACKUPS=p/'backups').items()]
        return archive,originals,patches,run,primary,root,unit,timer

    def test_failed_web_verification_restores_website_and_leaves_original_ten_unit(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
            p=Path(td);archive,originals,patches,run,primary,root,unit,timer=self.deployment_fixture(p)
            for item in patches:stack.enter_context(item)
            stack.enter_context(patch.object(installer,'run',side_effect=run))
            stack.enter_context(patch.object(installer,'verify_web',side_effect=ValueError('fixture failed smoke test')))
            # Tests run as root in this environment; account ownership is a
            # deployment detail and uses the current account for temporary paths.
            import pwd
            account=pwd.getpwuid(os.getuid());stack.enter_context(patch.object(installer.pwd,'getpwnam',return_value=account))
            stack.enter_context(patch.object(installer.os,'geteuid',return_value=0))
            result=installer.deploy(archive,'b'*40,True)
            self.assertEqual('SIX_CHALLENGERS_ROLLED_BACK',result['status'])
            for name,raw in originals.items():self.assertEqual(raw,(root/name).read_bytes())
            self.assertEqual('original ten unit',primary.read_text());self.assertFalse(unit.exists());self.assertFalse(timer.exists())

    def test_success_adds_only_new_service_and_checks_combined_feed(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
            p=Path(td);archive,originals,patches,run,primary,root,unit,timer=self.deployment_fixture(p)
            for item in patches:stack.enter_context(item)
            calls=[]
            def trace(args,timeout=30):calls.append(args);return run(args,timeout)
            stack.enter_context(patch.object(installer,'run',side_effect=trace))
            stack.enter_context(patch.object(installer,'verify_web',return_value={'items':16}))
            import pwd
            account=pwd.getpwuid(os.getuid());stack.enter_context(patch.object(installer.pwd,'getpwnam',return_value=account))
            stack.enter_context(patch.object(installer.os,'geteuid',return_value=0))
            result=installer.deploy(archive,'b'*40,True)
            self.assertEqual('SIX_CHALLENGERS_APPLIED',result['status'])
            self.assertEqual('original ten unit',primary.read_text())
            self.assertIn(['systemctl','enable','--now',timer.name],calls)
            self.assertTrue(unit.exists());self.assertTrue(timer.exists())
            for name in originals:self.assertEqual('new '+name,(root/name).read_text())

    def test_slow_preflight_blocks_before_new_units_or_website_changes(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
            p=Path(td);archive,originals,patches,run,primary,root,unit,timer=self.deployment_fixture(p)
            for item in patches:stack.enter_context(item)
            def slow(args,timeout=30):
                result=run(args,timeout)
                return json.dumps({'elapsed_seconds':56,'items':6}) if args[0]=='systemd-run' else result
            stack.enter_context(patch.object(installer,'run',side_effect=slow))
            import pwd
            account=pwd.getpwuid(os.getuid());stack.enter_context(patch.object(installer.pwd,'getpwnam',return_value=account))
            stack.enter_context(patch.object(installer.os,'geteuid',return_value=0))
            with self.assertRaisesRegex(installer.CadenceBudgetError,'cadence budget') as stopped:installer.deploy(archive,'b'*40,True)
            self.assertEqual(56,stopped.exception.preflight['elapsed_seconds'])
            self.assertFalse(unit.exists());self.assertFalse(timer.exists())
            for name,raw in originals.items():self.assertEqual(raw,(root/name).read_bytes())

    def test_crlf_equivalent_installed_files_pass_without_weakening_review(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
            p=Path(td);archive,originals,patches,run,primary,root,unit,timer=self.deployment_fixture(p)
            for item in patches:stack.enter_context(item)
            installed={name:raw.replace(b'\n',b'\r\n') for name,raw in originals.items()}
            for name,raw in installed.items():(root/name).write_bytes(raw)
            stack.enter_context(patch.object(installer,'run',side_effect=run))
            import pwd
            account=pwd.getpwuid(os.getuid());stack.enter_context(patch.object(installer.pwd,'getpwnam',return_value=account))
            stack.enter_context(patch.object(installer.os,'geteuid',return_value=0))
            result=installer.deploy(archive,'b'*40,False)
            self.assertEqual('SIX_CHALLENGER_PLAN',result['status'])
            self.assertTrue(all(value=='CRLF_EQUIVALENT' for value in result['reviewed_website_files'].values()))
            for name,raw in installed.items():self.assertEqual(raw,(root/name).read_bytes())
            self.assertFalse(unit.exists());self.assertFalse(timer.exists())

    def test_real_edit_to_crlf_installation_still_stops_before_preflight(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as td,ExitStack() as stack:
            p=Path(td);archive,originals,patches,run,primary,root,unit,timer=self.deployment_fixture(p)
            for item in patches:stack.enter_context(item)
            name=next(iter(originals));modified=originals[name].replace(b'\n',b'\r\n')+b'changed code\r\n'
            (root/name).write_bytes(modified)
            runner=stack.enter_context(patch.object(installer,'run'))
            stack.enter_context(patch.object(installer.os,'geteuid',return_value=0))
            with self.assertRaisesRegex(ValueError,'website changed; refuse overwrite'):installer.deploy(archive,'b'*40,True)
            runner.assert_not_called();self.assertEqual(modified,(root/name).read_bytes())
            self.assertFalse(unit.exists());self.assertFalse(timer.exists())


if __name__=='__main__':unittest.main()
