import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from research.rescore_saved_challengers import digest,load_archive,rescore


class SavedChallengerRescoreTests(unittest.TestCase):
    def fixture(self,root,*,miss=False):
        source=root/'source.sqlite';archive=root/'archive';archive.mkdir()
        with sqlite3.connect(source) as db:
            db.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                CREATE TABLE poll_heartbeats(id INTEGER PRIMARY KEY,timestamp,mode,success);
                CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
                CREATE TABLE country_stock_observations(id INTEGER PRIMARY KEY,received_epoch,country,country_update_epoch,clock_status);''')
            stock=[(-110+i*15,0) for i in range(6)]
            stock+=[(-109+i*15,1000) for i in range(6)]
            stock+=[(10,1000)]+([(250,0),(320,1),(330,0),(400,1000)] if miss else [])
            db.executemany("INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,'mex','Dahlia',?,'p')",sorted(stock))
            for t in range(0,701,10):
                db.execute("INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,'poll-cycle',1)",(t,))
                db.execute("INSERT INTO country_stock_observations(received_epoch,country,country_update_epoch,clock_status) VALUES(?,'mex',?,'REPORTED')",(t,t))
        manifest={'start':100,'end':700,'step':200,'pilot':False,'models':{'mex:Dahlia':['v20','traj3']},
            'policy':'CORRECTED_CHALLENGERS_FIRST_REACHABLE_V1','training_policy':'ALL_AVAILABLE_CAUSAL_HISTORY_NO_ROLLING_LOOKBACK',
            'source_sha256':digest(source),'code_sha256':{'native':'unchanged'}}
        (archive/'manifest.json').write_text(json.dumps(manifest))
        records=[]
        for t in range(100,701,200):
            r={'item':'mex:Dahlia','issued':t,'status':'STALE_COUNTRY_DATA'}
            if t==100 or (not miss and t>=500):
                dep,arr,valid=(200,300,280) if miss else (250,350,180) if t==100 else (t,t+20,t+180)
                r['status']='FIRST_REACHABLE_WINDOW_SELECTED'
                r['row']={'item_key':'mex:Dahlia','asof_epoch':t,
                    'decision':{'estimated_departure_epoch':dep,'estimated_arrival_epoch':arr,'valid_until_epoch':valid,
                        'selected_restock_event_index':1 if miss else 0,
                        'forecast_events':[{'index':1,'predicted_restock_epoch':400,'predicted_stock_below_30_epoch':1000}] if miss else []},
                    'forecast':{'current_stock_window':{'predicted_restock_epoch':10,'predicted_stock_below_30_epoch':1000}}}
            records.append(r)
        path=archive/'mex__Dahlia.jsonl';path.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
        return source,archive,path

    def test_expiry_and_missing_stale_clocks_are_preserved_without_refreshes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source,archive,path=self.fixture(root)
            original=path.read_bytes();result=rescore(source,archive,root/'out');m=result['items']['mex:Dahlia']
            self.assertEqual(1,m['simulated_trips']);self.assertEqual(1,m['successes'])
            self.assertEqual(1,m['revision_counts']['WITHDRAWN_STALE_BEFORE_DEPARTURE'])
            self.assertEqual(1,m['no_advice_clock_statuses']['STALE_COUNTRY_DATA'])
            trips=json.loads((root/'out/trips.json').read_text());self.assertEqual(500,trips[0]['departure_epoch'])
            self.assertEqual(520,trips[0]['arrival_epoch']);self.assertEqual(original,path.read_bytes())
            self.assertTrue(result['saved_geometry_preserved']);self.assertTrue(result['original_inputs_unchanged'])
            with self.assertRaises(ValueError):rescore(source,archive,root/'out')

    def test_nearest_restock_boundary_excludes_tiny_sellback(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source,archive,_=self.fixture(root,miss=True)
            result=rescore(source,archive,root/'out');m=result['items']['mex:Dahlia']
            self.assertEqual(1,m['failures'])
            miss=json.loads((root/'out/trips.json').read_text())[0]['miss']
            self.assertEqual('LATE',miss['classification']);self.assertEqual(400,miss['next_restock_epoch'])
            self.assertAlmostEqual(50/60,miss['minutes_after_zero'])

    def test_missing_or_duplicate_clock_and_changed_source_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source,archive,path=self.fixture(root);lines=path.read_text().splitlines()
            path.write_text('\n'.join(lines+[lines[0]]))
            with self.assertRaises(ValueError):load_archive(archive)
            path.write_text('\n'.join(lines))
            with sqlite3.connect(source) as db:db.execute("UPDATE stock_history SET quantity=999 WHERE quantity=1000")
            with self.assertRaises(ValueError):rescore(source,archive,root/'out')


if __name__=='__main__':unittest.main()
