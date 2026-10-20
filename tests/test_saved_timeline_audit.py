import json
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from research.saved_timeline_audit import timeline,read_journal,data_inventory,main


def row(q,dep,**changes):
    r=dict(item_key='uni:Nessie Plushie',mode='specialist_control',issued=q,published=q+10,
        departure=dep,source_cutoff=q,valid_until=q+180,status='RESEARCH_PROPOSAL_ONLY',
        model_sha='pin',physical_depletion_quantity=0,arrival_target=30,grace_seconds=10)
    r.update(changes);return r


class TimelineAuditTests(unittest.TestCase):
    def test_actual_owner_cli_completes_and_saves_readonly_audit_when_archives_absent(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);journal=home/'plans.sqlite';source=home/'source.sqlite';out=home/'report.json'
            with sqlite3.connect(journal) as c:
                c.executescript("CREATE TABLE metadata(key,value);INSERT INTO metadata VALUES('model_sha','pin');CREATE TABLE plans(issued,item_key,mode,record);CREATE TABLE cycles(status);")
                r=row(0,600);c.execute('INSERT INTO plans VALUES(?,?,?,?)',(0,r['item_key'],r['mode'],json.dumps(r)))
            with sqlite3.connect(source) as c:
                c.executescript("CREATE TABLE stock_history(country,item_name,timestamp,quantity);INSERT INTO stock_history VALUES('uni','Nessie Plushie',0,100);")
            before=(journal.read_bytes(),source.read_bytes());printed=io.StringIO()
            with patch('sys.argv',['audit','--journal',str(journal),'--source',str(source),'--model-sha','pin','--out',str(out)]), \
                 patch('research.saved_timeline_audit.Path.home',return_value=home), \
                 patch('research.saved_timeline_audit.recovery_inventory',return_value=dict(local_pages=[],home_project_directories=[])),redirect_stdout(printed):
                main()
            self.assertIn('AUDIT_REPORT_SAVED',printed.getvalue())
            self.assertEqual(json.loads(out.read_text())['original_v2_archived']['status'],'ORIGINAL_V2_FORECAST_AUDIT_TABLES_NOT_PRESENT')
            self.assertEqual((journal.read_bytes(),source.read_bytes()),before)

    def test_future_timing_is_distinct_from_five_minute_source_expiry(self):
        result=timeline([row(0,600),row(300,550),row(600,None)])['uni:Nessie Plushie|specialist_control']
        self.assertEqual(result['timed_proposals'],2)
        self.assertEqual(result['timing_causes']['target_after_next_model_recheck'],1)
        self.assertEqual(result['timing_causes']['within_five_minutes_but_source_expires_before_target'],1)
        self.assertEqual(result['timing_causes']['no_saved_departure'],1)
        self.assertEqual(result['target_changes']['advanced_before_old_target'],1)

    def test_postponement_and_capture_gap_are_not_conflated(self):
        r=timeline([row(0,600),row(300,900),row(1200,1800)])['uni:Nessie Plushie|specialist_control']
        self.assertEqual(r['target_changes']['postponed_before_old_target'],1)
        self.assertEqual(r['target_changes']['old_target_elapsed_between_captures'],1)
        self.assertEqual(r['query_gap_seconds']['over_330_seconds'],1)

    def test_readonly_journal_and_identity_validation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'plans.sqlite'
            with sqlite3.connect(p) as c:
                c.executescript("CREATE TABLE metadata(key,value);INSERT INTO metadata VALUES('model_sha','pin');CREATE TABLE plans(issued,item_key,mode,record);CREATE TABLE cycles(status);")
                r=row(0,600);c.execute('INSERT INTO plans VALUES(?,?,?,?)',(0,r['item_key'],r['mode'],json.dumps(r)))
            before=p.read_bytes();report=read_journal(p,'pin')
            self.assertEqual(report['records'],1)
            self.assertIsNone(report['restock_timing_accuracy'])
            self.assertEqual(p.read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'Wrong journal'):read_journal(p,'wrong')

    def test_inventory_reports_real_span_without_creating_missing_archives(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.sqlite'
            with sqlite3.connect(p) as c:
                c.executescript("CREATE TABLE stock_history(country,item_name,timestamp,quantity);INSERT INTO stock_history VALUES('uni','Nessie Plushie',100,0),('uni','Nessie Plushie',2592100,100);")
            before=p.read_bytes();r=data_inventory(p)
            self.assertEqual(r['items']['uni:Nessie Plushie']['observed_span_days'],30)
            self.assertIsNone(r['original_v2_archive_inventory'])
            self.assertEqual(p.read_bytes(),before)


if __name__=='__main__':unittest.main()
