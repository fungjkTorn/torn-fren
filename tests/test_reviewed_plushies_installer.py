"""Installer regressions: staging traversal and actionable child failures."""
import ast
from collections import namedtuple
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
import pwd
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
                cohort=installer.stage_cohort(stage,'first-ten-beta',os.getuid(),os.getgid())
                self.assertNotIn(Path(private),stage.parents)
                self.assertEqual(stage.parent,Path('/tmp'))
                self.assertEqual(stage.stat().st_mode & 0o777,0o755)
                self.assertEqual(cohort.stat().st_mode & 0o777,0o700)
                self.assertEqual((cohort.stat().st_uid,cohort.stat().st_gid),(os.getuid(),os.getgid()))
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

    @unittest.skipIf(os.geteuid()==0,'root bypasses directory DAC permissions')
    def test_writable_db_in_nonwritable_directory_reproduces_readonly_error(self):
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td);db_path=directory/'input.sqlite'
            with sqlite3.connect(db_path) as db:
                db.execute('CREATE TABLE stock_history(quantity)')
                db.execute('INSERT INTO stock_history VALUES(2500)')
            db_path.chmod(0o600);directory.chmod(0o555)
            try:
                self.assertTrue(os.access(db_path,os.W_OK))
                with sqlite3.connect(db_path) as db:
                    with self.assertRaisesRegex(sqlite3.OperationalError,'readonly'):
                        db.execute('DELETE FROM stock_history')
            finally:directory.chmod(0o700)

    def test_inference_owned_directory_allows_sqlite_journal_transaction(self):
        stage=installer.stage_directory()
        try:
            cohort=installer.stage_cohort(stage,'challengers-beta',os.getuid(),os.getgid())
            db_path=cohort/'input.sqlite'
            with sqlite3.connect(db_path) as db:
                db.execute('PRAGMA journal_mode=DELETE')
                db.execute('CREATE TABLE stock_history(quantity)')
                db.execute('INSERT INTO stock_history VALUES(2500)')
            db_path.chmod(0o600)
            with sqlite3.connect(db_path) as db:
                db.execute('DELETE FROM stock_history')
                self.assertTrue(Path(str(db_path)+'-journal').is_file())
                db.execute('INSERT INTO stock_history VALUES(30)')
            self.assertFalse(Path(str(db_path)+'-journal').exists())
            db_path.chmod(0o400)
            with sqlite3.connect(db_path.as_uri()+'?mode=ro',uri=True) as db:
                self.assertEqual(db.execute('SELECT quantity FROM stock_history').fetchall(),[(30,)])
        finally:shutil.rmtree(stage)

    @unittest.skipUnless(shutil.which('sudo') and shutil.which('runuser'),'requires CI sudo and runuser for split-user test')
    def test_root_created_stage_can_be_refreshed_by_inference_user(self):
        if subprocess.run(['sudo','-n','true'],capture_output=True).returncode:
            self.skipTest('passwordless CI sudo unavailable')
        root_code="""
import importlib.util,os,sqlite3,subprocess,sys,shutil
from pathlib import Path
spec=importlib.util.spec_from_file_location('installer',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
stage=m.stage_directory()
try:
 cohort=m.stage_cohort(stage,'split-user',int(sys.argv[2]),int(sys.argv[3]))
 db_path=cohort/'input.sqlite'
 with sqlite3.connect(db_path) as db:
  db.execute('CREATE TABLE stock_history(quantity)')
  db.execute('INSERT INTO stock_history VALUES(2500)')
 os.chown(db_path,int(sys.argv[2]),int(sys.argv[3]));db_path.chmod(0o600)
 child="import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute('DELETE FROM stock_history'); db.execute('INSERT INTO stock_history VALUES(30)'); db.commit(); db.close()"
 subprocess.run(['runuser','-u',sys.argv[4],'--',sys.executable,'-c',child,str(db_path)],check=True,capture_output=True,text=True)
 with sqlite3.connect(db_path) as db:assert db.execute('SELECT quantity FROM stock_history').fetchall()==[(30,)]
finally:shutil.rmtree(stage)
"""
        result=subprocess.run(['sudo','-n',sys.executable,'-c',root_code,str(Path(installer.__file__).resolve()),str(os.getuid()),str(os.getgid()),pwd.getpwuid(os.getuid()).pw_name],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_history_capacity_keeps_all_rows_and_preserves_guard(self):
        source=(Path(installer.__file__).resolve().parents[2]/'research/v128_full24_earliest_shadow.py').read_text()
        tree=ast.parse(source)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_read_item')
        ns={'MAX_ITEM_ROWS':installer.HISTORY_ROWS,'StockObservation':namedtuple('StockObservation','epoch quantity source')}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'history-reader','exec'),ns)
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source)')
            db.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',((i,'can','Wolverine Plushie',2500,'yata') for i in range(60001)))
            rows,error=ns['_read_item'](db,'can:Wolverine Plushie',60001)
            self.assertIsNone(error);self.assertEqual(len(rows),60001)
            self.assertEqual((rows[0].epoch,rows[-1].epoch),(0,60000))
            db.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',((i,'can','Wolverine Plushie',2500,'yata') for i in range(60001,200001)))
            self.assertEqual(ns['_read_item'](db,'can:Wolverine Plushie',200001),(None,'MAX_SOURCE_ROWS_EXCEEDED'))
        old=source.replace('MAX_ITEM_ROWS=200000','MAX_ITEM_ROWS=50000')
        self.assertEqual(installer.patch_reader(old),source)
        self.assertEqual(installer.patch_reader(source),source)
        bad=old.replace('return rows,None','return rows[:10],None')
        with self.assertRaisesRegex(ValueError,'Unrecognized history reader'):
            installer.patch_reader(bad)

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
