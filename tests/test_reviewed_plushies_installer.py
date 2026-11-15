"""Installer regressions: staging traversal and actionable child failures."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('installer',Path(__file__).resolve().parents[1]/'deploy/scripts/install_reviewed_plushies.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class InstallerTests(unittest.TestCase):
    def test_staging_does_not_depend_on_private_backup_traversal_or_umask(self):
        with tempfile.TemporaryDirectory() as private:
            old=os.umask(0o077)
            stage=None
            try:
                stage=installer.stage_directory()
                cohort=installer.stage_cohort(stage,'first-ten-beta')
                self.assertNotIn(Path(private),stage.parents)
                self.assertEqual(stage.parent,Path('/tmp'))
                self.assertEqual(stage.stat().st_mode & 0o777,0o755)
                self.assertEqual(cohort.stat().st_mode & 0o777,0o755)
                shim=cohort/'stage.py';shim.write_text('print("stage-readable")');shim.chmod(0o644)
                r=installer.cmd([sys.executable,'-B',str(shim)])
                self.assertEqual(r.stdout.strip(),'stage-readable')
            finally:
                os.umask(old)
                if stage:shutil.rmtree(stage)

    def test_staging_uses_only_publisher_replay_overrides(self):
        configured='OPENBLAS_NUM_THREADS=1 "TORNFREN_REPLAY_PINNED_RESEARCH=/var/lib/torn-fren-live-beta/no-legacy-stage" "TORNFREN_REPLAY_WORK=/path with spaces" UNRELATED_TOKEN=never-forward'
        with patch.object(installer,'show',return_value=configured) as show:
            args=installer.replay_environment('publisher.service')
        self.assertEqual(args,['TORNFREN_REPLAY_PINNED_RESEARCH=/var/lib/torn-fren-live-beta/no-legacy-stage','TORNFREN_REPLAY_WORK=/path with spaces'])
        show.assert_called_once_with('publisher.service','Environment')

    def test_missing_publisher_replay_configuration_fails_before_cutover(self):
        with patch.object(installer,'show',return_value='OPENBLAS_NUM_THREADS=1'):
            with self.assertRaisesRegex(ValueError,'no changes applied'):
                installer.replay_environment('publisher.service')

    def test_exit_two_preserves_underlying_python_error(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                installer.cmd([sys.executable,'/definitely-missing-reviewed-stage.py'])
        self.assertEqual(raised.exception.returncode,2)
        detail=json.loads(output.getvalue())
        self.assertEqual(detail['exit_code'],2)
        self.assertIn("can't open file",detail['stderr'])
        self.assertIn('definitely-missing-reviewed-stage.py',detail['stderr'])

if __name__=='__main__':unittest.main()
