import sqlite3
import unittest

from research.physical_restock_identity import match, audit, archived_audit


class PhysicalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.rows=[(0,100,'yata'),(100,0,'yata'),(200,5,'yata'),
                   (250,0,'yata'),(400,100,'yata'),(450,0,'yata')]
        self.polls=list(range(0,601,10))

    def label(self, **kw):
        args=dict(rows=self.rows,polls=self.polls,gaps=[],issued=110,
                  ordinal=1,cutoff=600,estimate=395,window_start=390,window_end=410)
        args.update(kw)
        return match(**args)

    def test_small_physical_refill_is_not_skipped_to_make_forecast_hit(self):
        r=self.label()
        self.assertEqual(r['restock_by_epoch'],200)
        self.assertEqual(r['observed_restock_quantity'],5)
        self.assertEqual(r['window_result'],'MISS')
        self.assertEqual(self.label(ordinal=2)['window_result'],'HIT')

    def test_residual_stock_is_not_physical_depletion(self):
        rows=[(0,100,'yata'),(100,29,'yata'),(200,200,'yata')]
        self.assertEqual(self.label(rows=rows)['status'],'PENDING')

    def test_gap_cannot_skip_unknown_event_and_match_later_drop(self):
        self.assertEqual(self.label(gaps=[(150,210)])['status'],'UNKNOWN')

    def test_provider_switch_and_return_invalidates_ordinal(self):
        rows=self.rows[:2]+[(120,0,'other'),(150,0,'yata')]+self.rows[2:]
        self.assertEqual(self.label(rows=rows)['reason'],'PROVIDER_SWITCH_OR_MISSING')

    def test_poll_bracket_partly_inside_window_is_unknown(self):
        r=self.label(window_start=195,window_end=205)
        self.assertEqual(r['window_result'],'UNKNOWN_EVENT_TIME_WITHIN_POLL_BRACKET')
        self.assertEqual((r['restock_after_epoch'],r['restock_by_epoch']),(190,200))

    def test_event_bracket_straddling_issue_is_not_a_future_event_label(self):
        self.assertEqual(self.label(issued=195)['reason'],'RESTOCK_BRACKET_STRADDLES_ISSUE')

    def test_no_future_evidence_and_no_backwards_poll_filling(self):
        self.assertEqual(self.label(cutoff=180)['status'],'PENDING')
        self.assertEqual(self.label(polls=[0,400,600])['reason'],'SPARSE_POLL_COVERAGE')

    def test_missing_evidence_never_creates_tables(self):
        with sqlite3.connect(':memory:') as db:
            self.assertEqual(audit(db,[],600)['status'],'MISSING_PHYSICAL_EVIDENCE_TABLES')
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0],0)

    def test_archive_integration_freezes_first_issue_and_ignores_stored_labels(self):
        with sqlite3.connect(':memory:') as db:
            db.executescript('''
                CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                CREATE TABLE poll_heartbeats(id INTEGER PRIMARY KEY,timestamp,mode,success,source);
                CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
                CREATE TABLE forecast_audit_runs(id,country,item_name,created_at,active_prediction_number);
                CREATE TABLE forecast_audit_points(id,run_id,prediction_number,estimate_timestamp,
                    window_start_timestamp,window_end_timestamp,window_hit);
                INSERT INTO forecast_audit_runs VALUES(1,'arg','Monkey Plushie',110,1),(2,'arg','Monkey Plushie',120,1);
                INSERT INTO forecast_audit_points VALUES(1,1,1,395,390,410,1),(2,2,1,195,190,210,1);
            ''')
            db.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,\'arg\',\'Monkey Plushie\',?,?)',self.rows)
            db.executemany('INSERT INTO poll_heartbeats(timestamp,mode,success,source) VALUES(?,\'poll-cycle\',1,\'yata\')',[(t,) for t in self.polls])
            db.commit()
            db.execute('PRAGMA query_only=ON')
            out=archived_audit(db,cutoff=600,days=1)
            self.assertEqual(out['overall'],dict(RESOLVED=1,MISS=1))
            self.assertFalse(out['legacy_normal_cycle_identity_certified'])
            # A later provider switch must not mask an earlier collection gap
            # that already made target identity unresolvable.
            db.execute('PRAGMA query_only=OFF')
            db.execute('INSERT INTO collection_gaps VALUES(150,160)')
            db.execute("UPDATE poll_heartbeats SET source='other' WHERE timestamp>=500")
            db.commit()
            db.execute('PRAGMA query_only=ON')
            out=archived_audit(db,cutoff=600,days=1)
            self.assertEqual(out['overall'],dict(UNKNOWN=1,COLLECTION_GAP=1))


if __name__=='__main__':unittest.main()
