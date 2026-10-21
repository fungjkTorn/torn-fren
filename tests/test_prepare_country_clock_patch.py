import ast
import contextlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from deploy.scripts.prepare_country_clock_patch import prepare
from services import country_freshness

SOURCE='''import time
HOST_EDIT = "preserve unrelated host edit"
def init_db():
    with _connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS stocks(quantity INTEGER)")
def save_snapshot_from_export(country,country_data,source):
    timestamp=int(time.time())
    with _connect() as conn:
        if country_data.get('fail'):
            raise ValueError('item save failure')
        if conn.execute('SELECT count(*) FROM stocks').fetchone()[0]==0:
            conn.execute('INSERT INTO stocks VALUES(?)',(country_data['stocks'][0]['quantity'],))
'''


class PrepareClockPatchTests(unittest.TestCase):
    def test_prepared_functions_log_unchanged_polls_and_rollback_with_items(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'history.py';source.write_text(SOURCE)
            helper=root/'helper.py';helper.write_text('VALUE=1\n');exporter=root/'exporter.py';exporter.write_text('VALUE=2\n')
            diff,manifest=prepare(source,helper,exporter)
            self.assertEqual(source.read_text(),SOURCE)
            self.assertFalse(manifest['export_epoch_forwarded'])
            self.assertIn('preserve unrelated host edit',SOURCE)
            # Apply only to isolated temp code; never the supplied host source.
            import subprocess
            target=root/'services';target.mkdir();copy=target/'history_service.py';copy.write_text(SOURCE)
            applied=subprocess.run(['git','-C',str(root),'apply','--unidiff-zero','-'],input=diff,text=True,capture_output=True)
            self.assertEqual(applied.returncode,0,applied.stderr)
            self.assertNotIn('preserve unrelated host edit',diff)
            modified=copy.read_text();self.assertIn('HOST_EDIT = "preserve unrelated host edit"',modified)
            # Execute only the three explicitly whitelisted definitions from
            # our synthetic fixture, with a temporary DB and fake clock.
            tree=ast.parse(modified);body=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
            dbpath=root/'test.sqlite'
            @contextlib.contextmanager
            def connect():
                cx=sqlite3.connect(dbpath)
                try:
                    with cx:yield cx
                finally:cx.close()
            g={'_connect':connect,'country_freshness':country_freshness,'time':SimpleNamespace(time=lambda:1000)}
            exec(compile(ast.Module(body=body,type_ignores=[]),'<synthetic-fixture>','exec'),g)
            g['init_db']()
            for i in range(2):g['save_snapshot_from_export']('jap',dict(update=990,stocks=[dict(quantity=0)]),'yata')
            with self.assertRaises(ValueError):g['save_snapshot_from_export']('jap',dict(update=990,stocks=[dict(quantity=0)],fail=True),'yata')
            with sqlite3.connect(dbpath) as cx:
                self.assertEqual(cx.execute('SELECT count(*) FROM country_stock_observations').fetchone()[0],2)
                self.assertEqual(cx.execute('SELECT count(*) FROM stocks').fetchone()[0],1)
                self.assertEqual(cx.execute('SELECT DISTINCT export_clock_status FROM country_stock_observations').fetchall(),[('MISSING',)])

    def test_existing_instrumentation_or_ambiguous_transaction_refuses_a_guess(self):
        for text in [SOURCE.replace('import time','from services import country_freshness\nimport time'),
                     SOURCE.replace('timestamp=int(time.time())','timestamp=int(time.time())\n    with _connect() as conn:\n        pass')]:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);source=root/'history.py';source.write_text(text)
                helper=root/'helper.py';helper.write_text('VALUE=1\n')
                with self.assertRaises(ValueError):prepare(source,helper,helper)


if __name__=='__main__':unittest.main()
