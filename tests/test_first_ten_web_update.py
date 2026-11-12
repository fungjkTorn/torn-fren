"""Git website update is scoped and restores original files on failed checks."""
import ast
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from deploy.scripts import update_first_ten_web as ui


class WebUpdateTests(unittest.TestCase):
    def exercise(self,fail=False,newer=False):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'site';files={name:('new '+name).encode() for name in ui.ALLOWED};before={name:('old '+name).encode() for name in ui.ALLOWED}
            for name,raw in before.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            manifest={'ui_revision':'travel-windows-v1','model_sha':'a'*40,'expected_publisher_sha':'b'*40,
                      'files':{name:{'previous_sha256':ui.digest(raw),'sha256':ui.digest(files[name])} for name,raw in before.items()}}
            if newer:(root/'web/first_release_bridge.py').write_text('newer work')
            calls=[]
            with patch.object(ui,'ROOT',root),patch.object(ui,'BACKUPS',Path(td)/'backups'),patch.object(ui.os,'geteuid',return_value=0),patch.object(ui,'load_release',return_value=(manifest,files)),patch.object(ui,'get',return_value=json.dumps({'model_sha':'a'*40,'publisher_sha':'b'*40}).encode()),patch.object(ui,'run',side_effect=lambda args:calls.append(args)),patch.object(ui,'health',side_effect=ValueError('synthetic failure') if fail else None,return_value={'routes':'PASS'}),patch.object(ui.time,'sleep'):
                if newer:
                    with self.assertRaisesRegex(ValueError,'refusing to overwrite'):ui.install(Path(td),'c'*40)
                    self.assertEqual('newer work',(root/'web/first_release_bridge.py').read_text());return
                result=ui.install(Path(td),'c'*40)
                self.assertEqual('WEB_UPDATE_STOPPED' if fail else 'WEB_UPDATE_CHECKS_PASSED',result['status'])
                self.assertEqual(before if fail else files,{name:(root/name).read_bytes() for name in ui.ALLOWED})
                self.assertFalse(result['models_changed']);self.assertFalse(result['publisher_changed']);self.assertFalse(result['evidence_changed'])
                ast.parse(Path(result['backup_directory'],'rollback.py').read_text())
                if not fail:self.assertEqual('WEB_ALREADY_INSTALLED',ui.install(Path(td),'c'*40)['status'])
            self.assertTrue(all(args==['systemctl','restart','torn-fren-web.service'] for args in calls))

    def test_successful_git_update_only_restarts_website(self):self.exercise()
    def test_failed_checks_restore_old_website_files(self):self.exercise(fail=True)
    def test_newer_edits_are_not_overwritten(self):self.exercise(newer=True)

if __name__=='__main__':unittest.main()
