from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from deploy.scripts import update_admin_health as update


class AdminDeploymentTests(unittest.TestCase):
    def test_plan_and_failed_api_roll_back_exact_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);web=root/'webroot';state=root/'state';state.mkdir();web.mkdir()
            (state/'latest.json').write_text(json.dumps({'model_sha':'frozen'}))
            for name in ('services','web/static'):(web/name).mkdir(parents=True)
            (web/'web/app.py').write_text('build_admin_health')
            (web/'services/admin_health.py').write_text('old=True\n')
            (web/'web/static/admin.html').write_text('old admin')
            archive=root/'update.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('services/admin_health.py','new=True\n')
                z.writestr('services/admin_live_beta_health.py','new_helper=True\n')
                z.writestr('web/static/admin.html','new admin')
            with patch.object(update,'ROOT',web),patch.object(update,'BACKUP_ROOT',root/'backup'),patch.object(update.os,'geteuid',return_value=0),patch.object(update.subprocess,'run') as restart:
                plan=update.deploy(archive,state=state)
                self.assertEqual('ADMIN_HEALTH_PLAN',plan['status']);restart.assert_not_called()
                with patch.object(update,'urlopen',return_value=BytesIO(b'{}')):
                    result=update.deploy(archive,True,state=state)
                self.assertEqual('ADMIN_HEALTH_ROLLED_BACK',result['status'])
                self.assertEqual('old=True\n',(web/'services/admin_health.py').read_text())
                self.assertEqual('old admin',(web/'web/static/admin.html').read_text())
                self.assertFalse((web/'services/admin_live_beta_health.py').exists())
                self.assertEqual(2,restart.call_count)


if __name__=='__main__':unittest.main()
