"""Guarded UI updates preserve live models and recover on failed smoke checks."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from deploy.scripts import update_first_ten_ui as ui


class UIUpdateTests(unittest.TestCase):
    def fixture(self,td):
        root=Path(td);assets=root/'assets';assets.mkdir()
        before={name:('original '+name).encode() for name in ui.NAMES}
        after={name:('updated '+name).encode() for name in ui.NAMES}
        for name,raw in before.items():(assets/name).write_bytes(raw)
        package=root/'update.zip';manifest={'ui_revision':ui.REVISION,'expected_model_sha':'a'*40,'files':{name:{'sha256':ui.digest(after[name]),'expected_installed_sha256':ui.digest(raw)} for name,raw in before.items()}}
        with zipfile.ZipFile(package,'w') as z:
            z.writestr('manifest.json',json.dumps(manifest))
            for name,raw in after.items():z.writestr('assets/'+name,raw)
        return assets,package,before,after

    def exercise(self,fail=False,newer=False):
        with tempfile.TemporaryDirectory() as td:
            assets,package,before,after=self.fixture(td)
            if newer:(assets/'beta.js').write_bytes(b'newer edit')
            with patch.object(ui,'ASSETS',assets),patch.object(ui,'BACKUPS',Path(td)/'backups'),patch.object(ui.os,'geteuid',return_value=0),patch.object(ui,'get',return_value=json.dumps({'model_sha':'a'*40}).encode()),patch.object(ui,'health',side_effect=ValueError('synthetic health failure') if fail else None,return_value={'assets':'PASS'}):
                if newer:
                    with self.assertRaisesRegex(ValueError,'refusing to overwrite'):ui.install(package)
                    self.assertEqual(b'newer edit',(assets/'beta.js').read_bytes())
                    return
                result=ui.install(package)
                expected=before if fail else after
                self.assertEqual(expected,{name:(assets/name).read_bytes() for name in ui.NAMES})
                self.assertEqual('UI_UPDATE_STOPPED' if fail else 'UI_UPDATE_CHECKS_PASSED',result['status'])
                self.assertFalse(result['models_changed']);self.assertFalse(result['evidence_database_changed']);self.assertFalse(result['services_restarted'])
                self.assertTrue(Path(result['backup_directory'],'rollback.py').is_file())
                if fail:self.assertTrue(result['ui_rolled_back'])
                else:self.assertEqual('UI_ALREADY_INSTALLED',ui.install(package)['status'])

    def test_assets_only_update_and_safe_rerun(self):self.exercise()
    def test_failed_smoke_check_restores_all_assets(self):self.exercise(fail=True)
    def test_newer_user_changes_are_preserved(self):self.exercise(newer=True)

    def test_wrong_package_checksum_does_not_change_installed_files(self):
        with tempfile.TemporaryDirectory() as td:
            assets,package,before,after=self.fixture(td)
            with zipfile.ZipFile(package,'a') as z:
                manifest=json.loads(z.read('manifest.json'));manifest['files']['beta.js']['sha256']='0'*64
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore');z.writestr('manifest.json',json.dumps(manifest))
            with patch.object(ui,'ASSETS',assets),patch.object(ui.os,'geteuid',return_value=0):
                with self.assertRaisesRegex(ValueError,'checksum mismatch'):ui.install(package)
            self.assertEqual(before,{name:(assets/name).read_bytes() for name in ui.NAMES})

if __name__=='__main__':unittest.main()
