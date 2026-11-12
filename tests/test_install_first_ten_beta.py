"""Installer mutation/rollback tests in a temporary fake VM; no real services."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from deploy.scripts import install_first_ten_beta as installer


class FakeProcess:
    pid=999999
    def poll(self):return None
    def wait(self,timeout=None):return 0


class InstallerTests(unittest.TestCase):
    def exercise(self,fail_service=False):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            def mapped(value='.'):
                p=Path(value)
                return root/str(p).lstrip('/') if str(p).startswith(('/opt/','/var/','/etc/','/home/')) else p
            mapped.cwd=Path.cwd
            app=mapped('/opt/torn-fren/web/app.py')
            app.parent.mkdir(parents=True); original=b'app = object()\n'
            app.write_bytes(original)
            for p in (installer.PYTHON,installer.WEB_PYTHON,installer.SOURCE):
                q=mapped(p);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b'fixture')
            package=root/'release.zip'
            files={'web/first_release_bridge.py':b'def install_first_release(app): pass\n',
                   'web/first_release_assets/board.html':b'<html>beta.js</html>'}
            manifest={'model_sha':'a'*40,'files':{'source/'+name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
            with zipfile.ZipFile(package,'w') as z:
                z.writestr('manifest.json',json.dumps(manifest))
                for name,raw in files.items():z.writestr('source/'+name,raw)
            calls=[]
            def fake_run(args,**kw):
                calls.append(args)
                if args[:3]==['systemctl','show',installer.WEB]:
                    return 'User=ubuntu\nWorkingDirectory=/opt/torn-fren\nActiveState=active\n'
                if args[0]=='runuser':return json.dumps({'status':'TEN_ITEM_SNAPSHOT_PUBLISHED'})
                if fail_service and args[:3]==['systemctl','start',installer.SERVICE]:
                    raise RuntimeError('synthetic service failure')
                return 'Result=success\nExecMainStatus=0\n'
            stdout=io.StringIO()
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(installer,'Path',mapped))
                for attr,value in {'BASE':mapped(installer.BASE),'APP':app,
                    'PYTHON':mapped(installer.PYTHON),'WEB_PYTHON':mapped(installer.WEB_PYTHON),
                    'SOURCE':mapped(installer.SOURCE),'DROPIN':mapped(installer.DROPIN),
                    'EXPECTED_APP':hashlib.sha256(original).hexdigest()}.items():
                    stack.enter_context(patch.object(installer,attr,value))
                stack.enter_context(patch.object(installer,'run',side_effect=fake_run))
                stack.enter_context(patch.object(installer,'health',return_value={'items':10,'model_sha':'a'*40}))
                stack.enter_context(patch.object(installer.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid())))
                stack.enter_context(patch.object(installer.subprocess,'Popen',return_value=FakeProcess()))
                stack.enter_context(patch.object(installer.subprocess,'run',return_value=SimpleNamespace(returncode=0)))
                stack.enter_context(patch.object(installer.os,'killpg'))
                stack.enter_context(patch.object(installer.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps({'analysis':{'first_release':{'item_key':'mex:Dahlia'}}}).encode())))
                stack.enter_context(patch('sys.argv',['installer','--package',str(package)]))
                stack.enter_context(contextlib.redirect_stdout(stdout))
                stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                code=installer.main()
            result=json.loads(stdout.getvalue())
            if fail_service:
                self.assertEqual(1,code)
                self.assertEqual('DEPLOYMENT_STOPPED',result['status'])
                self.assertTrue(result['web_changes_rolled_back'])
                self.assertEqual(original,app.read_bytes())
                self.assertFalse(mapped('/opt/torn-fren/web/first_release_bridge.py').exists())
                self.assertFalse(mapped('/etc/systemd/system/torn-fren-first-ten-beta.timer').exists())
            else:
                self.assertEqual(0,code)
                self.assertEqual('FIRST_TEN_BETA_LIVE_INITIAL_CHECKS_PASSED',result['status'])
                self.assertEqual(original+installer.HOOK,app.read_bytes())
                self.assertTrue(Path(result['backup_directory'],'app.py.original').is_file())
            # Existing production jobs are never disabled or modified.
            self.assertFalse(any(a[:2]==['systemctl','disable'] and 'torn-fren-poller.service' in a for a in calls))

    def test_successful_release_preserves_original_app_and_checks_routes(self):
        self.exercise()

    def test_failed_systemd_publication_restores_website_and_removes_new_units(self):
        self.exercise(fail_service=True)


if __name__=='__main__':unittest.main()
