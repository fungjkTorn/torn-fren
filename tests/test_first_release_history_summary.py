"""Historical UI summaries are descriptive, bounded, causal and read-only."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import os
from deploy.research_runner.export_snapshot import DDL
from web.first_release_bridge import read_history_summary,_history_summary_cached


class HistorySummaryTests(unittest.TestCase):
    def setUp(self):_history_summary_cached.cache_clear()
    def tearDown(self):_history_summary_cached.cache_clear()
    def fixture(self,td):
        path=Path(td)/'history.sqlite'
        with sqlite3.connect(path) as db:
            db.executescript(DDL)
            db.executemany("INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,'can','Crocus',?,'yata')",[(100,0),(200,100),(400,0),(500,200),(800,30),(900,0),(1100,9999)])
            db.execute("INSERT INTO poll_heartbeats(timestamp,mode,success,source) VALUES(990,'poll-cycle',1,'yata')")
        return path
    def test_statistics_use_30_threshold_but_true_depletion_is_zero(self):
        with tempfile.TemporaryDirectory() as td:
            path=self.fixture(td);before=path.read_bytes()
            with patch('web.first_release_bridge.time.time',return_value=1000):s=read_history_summary('can','Crocus',path=path)
            self.assertEqual('AVAILABLE',s['status']);self.assertEqual(2,s['completed_stock_windows'])
            self.assertEqual(250,s['avg_stocked_seconds']);self.assertEqual(250,s['median_stocked_seconds'])
            self.assertEqual(100,s['median_unstocked_seconds']);self.assertEqual(500,s['last_restock_timestamp'])
            self.assertEqual(900,s['last_depletion_timestamp']);self.assertEqual(200,s['last_peak_quantity'])
            self.assertEqual(900,s['sample_end_epoch']);self.assertEqual(before,path.read_bytes())
            self.assertFalse(s['forecast_accuracy_claimed'])
    def test_gap_and_provider_conflict_do_not_become_completed_windows(self):
        for mode in ('gap','provider'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                path=self.fixture(td)
                with sqlite3.connect(path) as db:
                    if mode=='gap':db.execute('INSERT INTO collection_gaps VALUES(350,450)')
                    else:db.execute("UPDATE stock_history SET source='prometheus' WHERE timestamp=400")
                with patch('web.first_release_bridge.time.time',return_value=1000):s=read_history_summary('can','Crocus',path=path)
                self.assertGreater(s['uncertain_boundaries'],0)
                self.assertLess(s['completed_stock_windows'],2)
                _history_summary_cached.cache_clear()
    def test_absent_item_is_unavailable_and_invalid_selection_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            path=self.fixture(td)
            with patch('web.first_release_bridge.time.time',return_value=1000):self.assertEqual('UNAVAILABLE',read_history_summary('jap','Xanax',path=path)['status'])
            with self.assertRaises(ValueError):read_history_summary('../','Crocus',path=path)

    def test_summary_endpoint_reads_the_sample_through_the_website(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.first_release_bridge import install_first_release
        with tempfile.TemporaryDirectory() as td:
            source=self.fixture(td);before=source.read_bytes();app=FastAPI();install_first_release(app)
            with patch.dict(os.environ,{'TORN_FREN_HISTORY_SUMMARY_SOURCE':str(source)}),patch('web.first_release_bridge.time.time',return_value=1000),TestClient(app) as client:
                result=client.get('/api/first-release/history-summary?country=can&item=Crocus').json()
            self.assertEqual('AVAILABLE',result['status']);self.assertTrue(result['source_read_only'])
            self.assertEqual(2,result['completed_stock_windows']);self.assertEqual(before,source.read_bytes())

if __name__=='__main__':unittest.main()
