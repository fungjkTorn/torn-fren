from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
import zipfile

from research.export_planner_evidence import bundle,ITEMS


class PlannerExportTests(unittest.TestCase):
    def test_bundle_contains_consistent_copies_and_preserves_originals(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ledger=root/'live.sqlite';collector=root/'collector.sqlite'
            with sqlite3.connect(ledger) as db:
                db.execute('CREATE TABLE issues(item,issued,payload)')
                db.executemany('INSERT INTO issues VALUES(?,1000,?)',[(key,'{"fixed":"original"}') for key in ITEMS])
            with sqlite3.connect(collector) as src:
                src.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                    CREATE TABLE poll_heartbeats(id INTEGER PRIMARY KEY,timestamp,mode,success);
                    CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
                    CREATE TABLE country_stock_observations(id INTEGER PRIMARY KEY,received_epoch,country,source,country_update_epoch,clock_status);''')
                for key in ITEMS:
                    country,item=key.split(':',1)
                    src.execute("INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(999,?,?,100,'p')",(country,item))
                src.execute("INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(1000,'poll-cycle',1)")
            before={p:p.read_bytes() for p in (ledger,collector)}
            output=root/'diagnostics.zip'
            result=bundle(ledger,collector,output,Path('research/export_challenger_history.py').read_text())
            self.assertEqual('PLANNER_DIAGNOSTICS_READY',result['status'])
            self.assertFalse(result['service_changes']);self.assertFalse(result['model_inference_run'])
            for p,raw in before.items():self.assertEqual(raw,p.read_bytes())
            with zipfile.ZipFile(output) as z:
                self.assertEqual({'forecasts.sqlite','stock_history.sqlite','manifest.json'},set(z.namelist()))
                manifest=json.loads(z.read('manifest.json'));self.assertEqual(10,len(manifest['items']))
                self.assertEqual(10,manifest['forecast_rows'])
                z.extract('forecasts.sqlite',root/'verify')
            with sqlite3.connect(root/'verify'/'forecasts.sqlite') as db:
                self.assertEqual(10,db.execute('SELECT COUNT(*) FROM issues').fetchone()[0])
            with self.assertRaises(ValueError):bundle(ledger,collector,output,'')


if __name__=='__main__':unittest.main()
