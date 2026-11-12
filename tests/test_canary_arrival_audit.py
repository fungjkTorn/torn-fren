import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import canary_arrival_audit as m

T=1792198800
SHA='a'*40


def board():
    from deploy.scripts.v163_readonly_event_first_preview import exact_roster
    rows=[]
    for key in sorted(exact_roster()):
        rows.append(dict(item_key=key,policy='zero_path_analog70',model_name='test',
            departure_source='explicit_recommendation',departure_epoch=T+1,arrival_epoch=T+61,
            departure_deadline_epoch=T+30,decision=dict(asof_epoch=T,player_flight_seconds=60,
                target_quantity=30,depletion_stock_quantity=0,arrival_grace_seconds=10,
                execution_policy='publication_delay_30s_v1',valid_until_epoch=T+180,
                model_departure_epoch=T,status='ESTIMATED_DEPARTURE_WINDOW_OPEN')))
    return dict(asof_epoch=T,evaluated_at_epoch=T+1,source_poll_age_seconds=15,rows=rows,item_count=24)


class AuditTests(unittest.TestCase):
    def test_recorder_uses_pinned_health_before_capturing_and_rejects_source_changes(self):
        with tempfile.TemporaryDirectory() as td:
            for good in (True,False):
                path=Path(td)/('good.sqlite' if good else 'wrong.sqlite')
                health={'source_sha':SHA if good else 'b'*40,'status':'PRIVATE_CANARY_READY'}
                with patch.object(m,'fetch',side_effect=[health,board()]) as fetch, \
                     patch.object(m.time,'monotonic',side_effect=[0,0,60]), \
                     patch.object(m.time,'time',return_value=T+3),patch.object(m.time,'sleep'),patch('builtins.print'):
                    m.record(path,SHA,duration=60)
                with sqlite3.connect(path) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM issues').fetchone()[0],24 if good else 0)
                self.assertEqual(fetch.call_count,2 if good else 1)

    def test_first_received_execution_is_frozen_and_duplicates_do_not_replace_it(self):
        with tempfile.TemporaryDirectory() as td:
            db=m.open_journal(Path(td)/'audit.sqlite',SHA)
            try:
                b=board();self.assertEqual(m.capture(db,b,received=T+3),24)
                self.assertEqual(m.capture(db,b,received=T+8),0)
                r=json.loads(db.execute('SELECT record FROM issues LIMIT 1').fetchone()[0])
                self.assertEqual(r['arrival_epoch'],T+63)
                self.assertEqual(r['captured'],T+3)
                self.assertEqual(r['plan_kind'],'immediate')
            finally:db.close()

    def test_expired_freshness_and_wrong_contract_are_not_proposals(self):
        with tempfile.TemporaryDirectory() as td:
            db=m.open_journal(Path(td)/'audit.sqlite',SHA)
            try:
                b=board();b['evaluated_at_epoch']=T+31
                self.assertEqual(m.capture(db,b,received=T+32),24)
                r=json.loads(db.execute('SELECT record FROM issues LIMIT 1').fetchone()[0])
                self.assertFalse(r['actionable_at_capture']);self.assertIsNone(r['arrival_epoch'])
                b=board();b['source_poll_age_seconds']=180
                with self.assertRaises(ValueError):m.capture(db,b,received=T+3)
                b=board();b['rows'][0]['decision']['depletion_stock_quantity']=30
                with self.assertRaises(ValueError):m.capture(db,b,received=T+3)
            finally:db.close()

    def test_journal_pin_and_unrelated_existing_file_are_protected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'audit.sqlite';m.open_journal(path,SHA).close();before=path.read_bytes()
            with self.assertRaises(ValueError):m.open_journal(path,'b'*40)
            self.assertEqual(before,path.read_bytes())
            with self.assertRaises(ValueError):m.open_journal(Path(td)/'source.db',SHA)

    def test_hour_selection_happens_before_actionability_and_unknowns_stay_visible(self):
        records=[dict(item_key='x',issued=T,captured=T+1,actionable_at_capture=False),
            dict(item_key='x',issued=T+20,captured=T+21,actionable_at_capture=True,
                 plan_kind='future',arrival_epoch=T+200)]
        r=m.summarize(records,lambda *_:('UNKNOWN','COLLECTION_GAP',None))
        primary=r['primary_first_observed_item_utc_hour']['x']
        self.assertEqual(primary['issues'],1);self.assertEqual(primary['abstain'],1)
        all_rows=r['all_observed_publications_diagnostic']['x']
        self.assertEqual(all_rows['UNKNOWN'],1);self.assertIsNone(all_rows['success_fraction'])
        self.assertEqual(all_rows['future_UNKNOWN'],1)

    def test_source_is_read_only_and_mature_arrivals_use_existing_poll_evidence(self):
        from test_v160_prospective_v151_shadow import collector_fixture
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=collector_fixture(root,issued=T+600);journal=root/'audit.sqlite'
            with sqlite3.connect(source) as db:
                db.execute('DELETE FROM stock_history');db.execute('DELETE FROM poll_heartbeats')
                for index,row in enumerate(board()['rows']):
                    country,name=row['item_key'].split(':',1)
                    db.execute('INSERT INTO stock_history(timestamp,quantity,source,country,item_name) VALUES(?,?,?,?,?)',
                        (T-10,0 if index==0 else 200,'yata',country,name))
                db.executemany("INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,'poll-cycle',1)",[(t,) for t in range(T,T+601,30)])
            with m.open_journal(journal,SHA) as db:m.capture(db,board(),received=T+3)
            db.close();before=source.read_bytes();ledger=journal.read_bytes()
            r=m.score_journal(source,journal,now=T+600)
            self.assertEqual(r['record_count'],24)
            values=list(r['primary_first_observed_item_utc_hour'].values())
            self.assertEqual(values[0]['FAILURE'],1)
            self.assertTrue(all(v['SUCCESS']==1 for v in values[1:]))
            self.assertEqual(before,source.read_bytes());self.assertEqual(ledger,journal.read_bytes())
            pending=m.score_journal(source,journal,now=T+100)
            self.assertTrue(all(v['PENDING']==1 for v in pending['primary_first_observed_item_utc_hour'].values()))
            with self.assertRaises(ValueError):m.score_journal(source,source,now=T+600)
            with sqlite3.connect(source) as db:
                db.execute('INSERT INTO collection_gaps VALUES(?,?)',(T+60,T+90))
            unknown=m.score_journal(source,journal,now=T+600)
            self.assertTrue(all(v['UNKNOWN']==1 for v in unknown['primary_first_observed_item_utc_hour'].values()))
