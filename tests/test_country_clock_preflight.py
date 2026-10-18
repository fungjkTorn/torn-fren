import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy.scripts import country_clock_preflight as m


class ClockPreflightTests(unittest.TestCase):
    def test_snapshot_only_scope_never_opens_live_database(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);snapshot=self.database(root/'copy.db')
            with patch.object(m,'database_report',wraps=m.database_report) as reads:
                r=m.preflight(collector_root=root,source=None,snapshot=snapshot,exporter=root/'missing',payload_root=root,now=1000)
            self.assertEqual(len(reads.call_args_list),1)
            self.assertEqual(reads.call_args.args[0],snapshot)
            self.assertEqual(r['scope'],'SNAPSHOT_AND_STATIC_CODE_ONLY')
            self.assertEqual(r['live_database']['status'],'NOT_REQUESTED')
            self.assertEqual(r['diagnosis'],'SNAPSHOT_CLOCK_EXPORT_INSTRUMENTATION_UNCONFIRMED')

    def database(self,path,clocks=True,meta=False):
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER,source TEXT,error TEXT)')
            db.execute("INSERT INTO poll_heartbeats VALUES(990,'poll-cycle',1,'yata','do not expose heartbeat error')")
            if clocks:
                db.execute('''CREATE TABLE country_stock_observations(id INTEGER PRIMARY KEY,received_epoch INTEGER,
                    country TEXT,source TEXT,country_update_epoch INTEGER,clock_status TEXT)''')
                db.executemany('INSERT INTO country_stock_observations VALUES(?,?,?,?,?,?)',[
                    (1,950,'jap','yata',930,'REPORTED'),(2,980,'jap','prometheus',None,'MISSING'),
                    (3,1001,'jap','yata',1000,'REPORTED')])
            if meta:
                db.execute('CREATE TABLE research_metadata(key TEXT,value TEXT)')
                db.executemany('INSERT INTO research_metadata VALUES(?,?)',[
                    ('country_clock_schema_available','true'),('country_clock_rows','3'),('secret','never expose')])
        return path

    def test_live_clocks_and_absent_export_metadata_are_distinguished_without_db_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);live=self.database(root/'live.db');snapshot=self.database(root/'copy.db')
            before=(live.read_bytes(),snapshot.read_bytes())
            r=m.preflight(collector_root=root,source=live,snapshot=snapshot,exporter=root/'missing',payload_root=root,now=1000)
            self.assertEqual(r['diagnosis'],'CLOCK_ROWS_PRESENT_EXPORT_INSTRUMENTATION_UNCONFIRMED')
            self.assertEqual(r['live_database']['japan_sampled_rows'],2)
            self.assertEqual(r['live_database']['successful_poll_age_seconds'],10)
            self.assertEqual(before,(live.read_bytes(),snapshot.read_bytes()))
            self.assertNotIn('do not expose heartbeat error',json.dumps(r))
            self.assertFalse(r['production_modified']);self.assertFalse(r['service_restarted'])

    def test_missing_source_is_never_created(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'missing.sqlite'
            self.assertEqual(m.database_report(path,1000)['status'],'UNAVAILABLE')
            self.assertFalse(path.exists())

    def test_readonly_database_metadata_is_allowlisted(self):
        with tempfile.TemporaryDirectory() as td:
            path=self.database(Path(td)/'snapshot.db',meta=True)
            r=m.database_report(path,1000,snapshot=True)
            self.assertTrue(r['clock_export_metadata_present'])
            self.assertNotIn('never expose',json.dumps(r));self.assertNotIn('secret',r['metadata'])
            self.assertEqual(r['japan_providers']['yata']['min_report_age_seconds'],20)
            self.assertEqual(r['japan_providers']['prometheus']['statuses'],{'MISSING':1})

    def test_missing_table_does_not_trigger_schema_creation(self):
        with tempfile.TemporaryDirectory() as td:
            path=self.database(Path(td)/'source.db',clocks=False);before=path.read_bytes()
            r=m.database_report(path,1000)
            self.assertFalse(r['clock_table_present']);self.assertEqual(path.read_bytes(),before)

    def test_static_checks_parse_code_without_executing_or_believing_comments(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'services').mkdir()
            history=root/'services/history_service.py';marker=root/'EXECUTED'
            history.write_text("raise RuntimeError('would execute if imported')\n# country_freshness.record(...)\ndef save_snapshot_from_export():\n    pass\n")
            r=m.inspect_code(root,root/'missing')
            self.assertFalse(r['country_record_call_present']);self.assertFalse(marker.exists())
            history.write_text('def save_snapshot_from_export():\n    country_freshness.record(None)\n')
            self.assertTrue(m.inspect_code(root,root/'missing')['country_record_call_present'])

    def test_patch_preflight_only_checks_and_preserves_local_code(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);target=root/'target.py';target.write_text('original\n')
            payload=root/'payload';folder=payload/'deploy/research_runner';folder.mkdir(parents=True)
            (folder/'country_clock_activation.patch').write_text('--- a/target.py\n+++ b/target.py\n@@ -1 +1 @@\n-original\n+patched\n')
            r=m.patch_check(root,payload)
            self.assertEqual(r['status'],'APPLICABLE');self.assertEqual(target.read_text(),'original\n')

    def test_invalid_clock_schema_stays_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=self.database(root/'live.db',clocks=False)
            with sqlite3.connect(source) as db:db.execute('CREATE TABLE country_stock_observations(id INTEGER)')
            r=m.preflight(collector_root=root,source=source,snapshot=root/'missing',exporter=root/'missing',payload_root=root,now=1000)
            self.assertEqual(r['diagnosis'],'LIVE_CLOCK_SCHEMA_UNSUPPORTED')


if __name__=='__main__':unittest.main()
