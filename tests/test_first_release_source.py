"""Causal lightweight refresh keeps stale exports out of live advice."""
from contextlib import closing
import shutil
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from deploy.research_runner.export_snapshot import DDL
from services.first_release_source import refresh_tail
from services.first_release_schedule import FIRST_RELEASE_MODELS
from services.first_release_live import publish
from services.frozen_candidate_worker_v31 import inspect_live_source

NOW=1790000000


class TailRefreshTests(unittest.TestCase):
    def fixture(self,td,*,age=170,live_age=5):
        snap=Path(td)/'snapshot.sqlite';live=Path(td)/'collector.sqlite'
        with sqlite3.connect(snap) as db:
            db.executescript(DDL)
            db.execute("INSERT INTO poll_heartbeats(timestamp,mode,success,source) VALUES(?,'poll-cycle',1,'yata')",(NOW-age,))
            db.execute("INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,'uae','Tribulus Omanense',100,'yata')",(NOW-age,))
            db.execute('INSERT INTO collection_gaps VALUES(?,NULL)',(NOW-150,))
        shutil.copyfile(snap,live)
        with sqlite3.connect(live) as db:
            db.execute("CREATE TABLE api_secrets(secret TEXT)")
            db.execute("INSERT INTO api_secrets VALUES('not-an-actual-key')")
            db.execute('UPDATE collection_gaps SET end_timestamp=?',(NOW-120,))
            for t in (NOW-live_age,NOW+30):
                db.execute("INSERT INTO poll_heartbeats(timestamp,mode,success,source) VALUES(?,'poll-cycle',1,'yata')",(t,))
                db.execute("INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,'uae','Tribulus Omanense',50,'yata')",(t,))
                db.execute("INSERT INTO country_stock_observations(received_epoch,country,source,country_update_epoch,export_epoch,clock_status,export_clock_status,item_count) VALUES(?,'uae','yata',?,?,'REPORTED','REPORTED',1)",(t,t,t))
        return snap,live

    def test_fresh_causal_tail_preserves_gaps_and_does_not_write_collector(self):
        with tempfile.TemporaryDirectory() as td:
            snap,live=self.fixture(td);before=live.read_bytes()
            info=refresh_tail(snap,live,cutoff=NOW)
            self.assertEqual('READ_ONLY_COLLECTOR_TAIL_APPLIED',info['status'])
            self.assertEqual(NOW-5,info['collector_heartbeat_epoch'])
            self.assertEqual(before,live.read_bytes())
            with sqlite3.connect(snap) as db:
                self.assertEqual(NOW-5,db.execute('SELECT MAX(timestamp) FROM stock_history').fetchone()[0])
                self.assertEqual(NOW-5,db.execute('SELECT MAX(received_epoch) FROM country_stock_observations').fetchone()[0])
                self.assertEqual((NOW-150,NOW-120),db.execute('SELECT * FROM collection_gaps').fetchone())
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='api_secrets'").fetchone())
            self.assertEqual('FRESH',inspect_live_source(snap,NOW)['status'])

    def test_stale_full_history_and_dead_collector_are_refused(self):
        for age,live_age,message in ((601,5,'too old'),(170,190,'fresh successful')):
            with self.subTest(age=age),tempfile.TemporaryDirectory() as td:
                snap,live=self.fixture(td,age=age,live_age=live_age)
                # The live fixture inherits the old snapshot heartbeat. Remove
                # that one too so the stale-collector branch is unambiguous.
                if live_age==190:
                    with sqlite3.connect(live) as db:db.execute('DELETE FROM poll_heartbeats WHERE timestamp=?',(NOW-age,))
                before=snap.read_bytes()
                with self.assertRaisesRegex(ValueError,message):refresh_tail(snap,live,cutoff=NOW)
                self.assertEqual(before,snap.read_bytes())

    def test_failed_partial_tail_rolls_back_inference_copy(self):
        with tempfile.TemporaryDirectory() as td:
            snap,live=self.fixture(td)
            with sqlite3.connect(live) as db:db.execute('DROP TABLE country_stock_observations')
            before=snap.read_bytes()
            with self.assertRaisesRegex(ValueError,'country stock clocks'):refresh_tail(snap,live,cutoff=NOW)
            self.assertEqual(before,snap.read_bytes())

    def test_future_gap_recovery_is_censored_at_the_issue_cutoff(self):
        with tempfile.TemporaryDirectory() as td:
            snap,live=self.fixture(td)
            with sqlite3.connect(live) as db:db.execute('INSERT INTO collection_gaps VALUES(?,?)',(NOW-10,NOW+20))
            refresh_tail(snap,live,cutoff=NOW)
            with sqlite3.connect(snap) as db:
                self.assertIsNone(db.execute('SELECT end_timestamp FROM collection_gaps WHERE start_timestamp=?',(NOW-10,)).fetchone()[0])
            self.assertEqual('COLLECTION_GAP_CROSSES_RECENT_POLL',inspect_live_source(snap,NOW)['status'])

    def test_bounded_refresh_restores_normal_lifetime_and_preserves_model_series(self):
        from test_first_release_schedule import FirstReleaseNativeTests
        FirstReleaseNativeTests.setUpClass()
        try:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);state=root/'state';state.mkdir()
                export=root/'export.sqlite';live=root/'live.sqlite'
                shutil.copyfile(FirstReleaseNativeTests.source,live)
                with sqlite3.connect(live) as db:
                    for country in {k.split(':')[0] for k in FIRST_RELEASE_MODELS}:
                        db.execute("INSERT INTO country_stock_observations(received_epoch,country,source,country_update_epoch,export_epoch,clock_status,export_clock_status,item_count) VALUES(?,?,'yata',?,?,'REPORTED','REPORTED',1)",(NOW,country,NOW,NOW))
                shutil.copyfile(live,export)
                with sqlite3.connect(export) as db:
                    db.execute('DELETE FROM poll_heartbeats WHERE timestamp>?',(NOW-200,))
                    db.execute('DELETE FROM stock_history WHERE timestamp>?',(NOW-200,))
                    db.execute('DELETE FROM country_stock_observations')
                # The original exported heartbeat is expired (>180s); a fresh
                # collector tail is required, rather than extending its expiry.
                before=live.read_bytes()
                result=publish(export,state,model_sha='a'*40,publisher_sha='b'*40,live_source=live,clock=lambda:NOW)
                self.assertEqual('TEN_ITEM_SNAPSHOT_PUBLISHED',result['status'])
                import json
                s=json.loads((state/'latest.json').read_text())
                self.assertEqual(NOW+180,s['valid_until_epoch'])
                self.assertEqual('a'*40,s['model_sha']);self.assertEqual('b'*40,s['publisher_sha'])
                self.assertEqual(before,live.read_bytes())
                self.assertTrue(all(r['decision']['status']!='STALE_COUNTRY_DATA' for r in s['items'].values()))
                with sqlite3.connect(state/'forecasts.sqlite') as ledger:
                    row=json.loads(ledger.execute('SELECT payload FROM issues LIMIT 1').fetchone()[0])
                    self.assertEqual('b'*40,row['publisher_sha'])
                    self.assertFalse(row['source_refresh']['collector_written'])
        finally:FirstReleaseNativeTests.tearDownClass()

if __name__=='__main__':unittest.main()
