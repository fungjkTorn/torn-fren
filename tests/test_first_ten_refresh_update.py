"""Git-based refresh repair preserves model identity and rolls code back safely."""
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch
from deploy.scripts import update_first_ten_refresh as updater


class RefreshUpdateTests(unittest.TestCase):
    def test_git_staging_refuses_changes_to_the_approved_model_source(self):
        for changed in (False,True):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as td:
                root=Path(td);original=root/'releases'/updater.MODEL_SHA
                files={'services/model.py':b'# frozen model\n','research/phases.py':b'# frozen phases\n',
                       'deploy/scripts/v163_readonly_event_first_preview.py':b'# frozen scheduler\n'}
                for name,raw in files.items():
                    p=original/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                files['services/first_release_live.py']=b'# new publisher only\n'
                if changed:files['services/model.py']=b'# unapproved model change\n'
                stream=io.BytesIO()
                with tarfile.open(fileobj=stream,mode='w:') as archive:
                    for name,raw in files.items():
                        member=tarfile.TarInfo(name);member.size=len(raw);archive.addfile(member,io.BytesIO(raw))
                with patch.object(updater,'BASE',root),patch.object(updater,'run',return_value=stream.getvalue()):
                    if changed:
                        with self.assertRaisesRegex(ValueError,'frozen model source changed'):updater.stage(root,'b'*40)
                    else:
                        release,staged,count=updater.stage(root,'b'*40)
                        self.assertEqual(3,count);self.assertEqual(files,staged)
                        self.assertEqual(b'# frozen model\n',(release/'services/model.py').read_bytes())

    def exercise(self,fail=False):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);paths=[root/name for name in ('publisher.service','bridge.py','beta.js')]
            for p in paths:p.write_text('original '+p.name)
            originals={p:p.read_bytes() for p in paths}
            release=root/'release';release.mkdir();repo=root/'repo';repo.mkdir()
            files={'web/first_release_bridge.py':b'# updated bridge\n','web/first_release_assets/beta.js':b'// updated UI\n'}
            calls=[]
            def run(args,**kw):
                calls.append(args)
                if args[:3]==['systemctl','show',updater.TIMER]:return 'ActiveState=active\nUnitFileState=enabled\n'
                if args[0]=='flock':return json.dumps({'status':'TEN_ITEM_SNAPSHOT_PUBLISHED','model_sha':updater.MODEL_SHA})
                if fail and args==['systemctl','start',updater.SERVICE]:raise RuntimeError('synthetic service failure')
                return 'Result=success\nExecMainStatus=0\n'
            out=io.StringIO()
            with contextlib.ExitStack() as stack:
                for name,value in {'SERVICE_PATH':paths[0],'BRIDGE':paths[1],'JS':paths[2],
                    'EXPECTED':{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                    'BASE':root/'state','BACKUPS':root/'backups'}.items():stack.enter_context(patch.object(updater,name,value))
                stack.enter_context(patch.object(updater,'run',side_effect=run))
                stack.enter_context(patch.object(updater,'stage',return_value=(release,files,300)))
                stack.enter_context(patch.object(updater,'health',return_value={'model_sha':updater.MODEL_SHA,'publisher_sha':'b'*40}))
                stack.enter_context(patch.object(updater.os,'geteuid',return_value=0))
                stack.enter_context(patch('sys.argv',['updater','--repo',str(repo),'--commit','b'*40]))
                stack.enter_context(contextlib.redirect_stdout(out));stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                code=updater.main()
            result=json.loads(out.getvalue())
            self.assertEqual(1 if fail else 0,code)
            self.assertFalse(result['collector_modified'])
            self.assertEqual('REFRESH_REPAIR_STOPPED' if fail else 'REFRESH_REPAIR_INITIAL_CHECKS_PASSED',result['status'])
            if fail:
                self.assertTrue(result['code_rolled_back'])
                self.assertEqual(originals,{p:p.read_bytes() for p in paths})
            else:
                self.assertTrue(result['evidence_series_preserved'])
                self.assertEqual(updater.MODEL_SHA,result['model_sha'])
                service=paths[0].read_text()
                self.assertIn('--publisher-sha '+'b'*40,service)
                self.assertIn('--model-sha '+updater.MODEL_SHA,service)
                self.assertIn('--live-source /opt/torn-fren/data/stock_history.db',service)
                ast.parse(Path(result['backup_directory'],'rollback.py').read_text())
            # No existing project jobs are disabled, and the same timer is
            # restarted even when a publication/service check fails.
            self.assertIn(['systemctl','start',updater.TIMER],calls)
            self.assertFalse(any(a[:2]==['systemctl','disable'] for a in calls))

    def test_git_update_preserves_frozen_model_series(self):self.exercise()
    def test_failed_service_restores_previous_code_and_timer(self):self.exercise(fail=True)

if __name__=='__main__':unittest.main()
