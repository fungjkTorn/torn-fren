import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from research.corrected_challenger_replay import run, country_state
from research.export_challenger_history import export, DDL, ITEMS


class ReplayTests(unittest.TestCase):
    def source(self,path):
        now=1793000100
        with sqlite3.connect(path) as con:
            con.executescript(DDL)
            for k in ITEMS:
                c,n=k.split(':',1)
                con.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',
                    [(now-16*86400,c,n,0,'yata'),(now-7*86400+600,c,n,100,'yata'),(now-7*86400+1200,c,n,30,'yata')])
            con.executemany("INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,'poll-cycle',1)",
                [(t,) for t in range(now-16*86400,now+1,60)])
            for c in {k.split(':')[0] for k in ITEMS}:
                con.executemany("INSERT INTO country_stock_observations(received_epoch,country,source,country_update_epoch,clock_status) VALUES(?,?,'yata',?,'REPORTED')",
                    [(t,c,t) for t in range(now-16*86400,now+1,60)])
        return now

    def test_export_sanitized_consistent_nonreplacement(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'source.db';out=root/'export.db';now=self.source(source)
            with sqlite3.connect(source) as con:
                con.execute('CREATE TABLE secrets(api_key TEXT)');con.execute("INSERT INTO secrets VALUES('never-export')")
            before=source.read_bytes()
            with patch('research.export_challenger_history.time.time',return_value=now):
                report=export(source,out,days=28)
            self.assertEqual(before,source.read_bytes());self.assertEqual(7,len(report['items']))
            with sqlite3.connect(out) as con:
                self.assertIsNone(con.execute("SELECT 1 FROM sqlite_master WHERE name='secrets'").fetchone())
            with self.assertRaises(ValueError):export(source,out)

    def test_future_departure_is_scored_without_five_minute_or_agreement_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'source.db';now=self.source(source);calls=[]
            def worker(args,**kw):
                db=args[args.index('--worker')+1];issued=int(args[args.index('--issued')+1]);calls.append(issued)
                with sqlite3.connect(db) as con:
                    self.assertLessEqual(con.execute('SELECT MAX(timestamp) FROM stock_history').fetchone()[0],issued)
                    self.assertLessEqual(con.execute('SELECT MAX(timestamp) FROM poll_heartbeats').fetchone()[0],issued)
                row={'item_key':ITEMS[0],'asof_epoch':issued,'decision':{'status':'WAIT',
                    'estimated_departure_epoch':issued+600,'estimated_arrival_epoch':issued+900,
                    'selected_restock_event_index':1,'forecast_events':[{'index':1,'predicted_restock_epoch':issued+600}]}}
                return SimpleNamespace(stdout=json.dumps(row))
            before=source.read_bytes()
            with patch('research.corrected_challenger_replay.subprocess.run',side_effect=worker):
                run(source,root/'result',pilot=True,items=[ITEMS[0]])
                run(source,root/'result',pilot=True,items=[ITEMS[0]])
            self.assertEqual(1,len(calls))  # Resume does not change an issued forecast.
            summary=json.loads(next((root/'result').glob('*.summary.json')).read_text())
            self.assertEqual({'SUCCESS':1},summary['distinct_opportunity_counts'])
            self.assertEqual(before,source.read_bytes())

    def test_exactly_thirty_fails_and_missing_country_evidence_is_unknown(self):
        from services.first_release_evidence import grade
        result=grade(1000,[(800,30,'yata')],[900,1100],[],cutoff=2000)
        self.assertEqual('FAILURE',result['status'])
        with sqlite3.connect(':memory:') as con:
            self.assertEqual('UNVERIFIED',country_state(con,'can',1000))


if __name__=='__main__':unittest.main()
