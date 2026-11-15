"""Installer regressions: staging traversal and actionable child failures."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import hashlib
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

    def test_configured_publisher_source_instead_of_collector(self):
        first='{ path=/usr/bin/flock ; argv[]=/usr/bin/flock -n /state/lock /venv/python entry.py publish --source /var/lib/torn-fren-research/stock_history_forward.db --state /var/lib/torn-fren-live-beta --live-source /opt/torn-fren/data/stock_history.db ; ignore_errors=no ; }'
        other='{ path=/venv/python ; argv[]=/venv/python -m services.challenger_live --collector /opt/torn-fren/data/stock_history.db --state /var/lib/torn-fren-live-beta/challengers ; ignore_errors=no ; }'
        self.assertEqual(installer.configured_source(first),Path('/var/lib/torn-fren-research/stock_history_forward.db'))
        self.assertEqual(installer.configured_source(other),Path('/var/lib/torn-fren-live-beta/challengers/stock_history.sqlite'))
        explicit=other.replace('--collector','--source /var/lib/torn-fren-live-beta/challengers/custom.sqlite --collector')
        self.assertEqual(installer.configured_source(explicit),Path('/var/lib/torn-fren-live-beta/challengers/custom.sqlite'))

    def test_unrecognized_launch_does_not_guess_source(self):
        with self.assertRaisesRegex(ValueError,'no changes applied'):
            installer.configured_source('not-systemd-launch-properties')

    def test_freeze_preserves_input_and_confines_changes_to_private_copy(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.sqlite';snapshot=Path(td)/'copy.sqlite'
            with sqlite3.connect(source) as db:
                db.execute('CREATE TABLE stock_history(quantity)')
                db.executemany('INSERT INTO stock_history VALUES(?)',[(30,),(2500,)])
            before=hashlib.sha256(source.read_bytes()).hexdigest()
            installer.freeze_input(source,snapshot)
            with sqlite3.connect(snapshot) as db:
                self.assertEqual(db.execute('SELECT quantity FROM stock_history').fetchall(),[(30,),(2500,)])
                db.execute('INSERT INTO stock_history VALUES(99)')
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)

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
