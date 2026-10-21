import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.shadow_scorecard import build,report


def row(issued,mode,wait=0,status='SHADOW_ESTIMATE'):
    published=issued+15;dep=published+wait if wait is not None else None
    return dict(issued=issued,item_key='jap:Xanax',mode=mode,published=published,
        departure=dep,arrival=dep+8940 if dep is not None else None,flight_seconds=8940,status=status)


class ScorecardTests(unittest.TestCase):
    def test_accuracy_never_hides_low_coverage_pending_unknown_or_future_plans(self):
        rows=[]
        for i in range(4):
            t=3600*i
            rows.extend([row(t,'leave_now_control'),row(t,'challenger',600 if i<3 else None)])
        outcomes={row(0,'challenger',600)['arrival']:'SUCCESS',row(3600,'challenger',600)['arrival']:'UNKNOWN',row(7200,'challenger',600)['arrival']:'PENDING'}
        result=build(rows,lambda key,arrival:(outcomes.get(arrival,'FAILURE'),'TEST',None))
        item=result['items']['jap:Xanax'];m=item['models']['challenger']
        self.assertEqual(m['known_success_fraction'],1);self.assertEqual(m['proposal_coverage'],.75)
        self.assertEqual((m['known'],m['unknown'],m['pending'],m['abstentions']),(1,1,1,1))
        self.assertEqual(m['immediate']['proposals'],0);self.assertEqual(m['future']['proposals'],3)
        p=item['paired_vs_controls']['leave_now_control']['challenger']
        self.assertEqual((p['challenger_wins'],p['both_known'],p['unresolved']),(1,1,3))
        self.assertFalse(result['automatic_promotion']);self.assertFalse(result['future_departure_reconfirmation'])

    def test_different_issue_in_same_hour_is_not_a_paired_comparison(self):
        result=build([row(0,'leave_now_control'),row(300,'challenger')],lambda k,a:('SUCCESS','TEST',None))
        item=result['items']['jap:Xanax']
        self.assertEqual(item['models']['challenger']['missing_issues'],1)
        self.assertEqual(item['models']['challenger']['proposal_coverage'],0)
        self.assertEqual(item['paired_vs_controls']['leave_now_control']['challenger']['both_known'],0)

    def test_reject_duplicate_mixed_flight_and_unpublished_departure(self):
        score=lambda k,a:('SUCCESS','TEST',None)
        r=row(0,'challenger')
        with self.assertRaises(ValueError):build([r,r],score)
        with self.assertRaises(ValueError):build([dict(r,arrival=r['arrival']+1)],score)
        with self.assertRaises(ValueError):build([dict(r,departure=0)],score)

    def test_report_checks_recorded_pin_and_reads_both_files_without_changes(self):
        class Evidence:
            cutoff=20000
            def score(self,arrival):return ('SUCCESS','TEST',None)
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.db';source.write_bytes(b'untouched')
            journal=Path(td)/'journal.sqlite';sha='a'*40
            r=dict(row(0,'challenger'),model_sha=sha)
            with sqlite3.connect(journal) as db:
                db.executescript('CREATE TABLE metadata(key TEXT,value TEXT);CREATE TABLE plans(issued INTEGER,item_key TEXT,mode TEXT,record TEXT);')
                db.execute('INSERT INTO metadata VALUES(?,?)',('model_sha',sha))
                db.execute('INSERT INTO plans VALUES(?,?,?,?)',(0,'jap:Xanax','challenger',json.dumps(r)))
            before=journal.read_bytes()
            with patch('research.japan_xanax.renewal_shadow.source_data',return_value=([],[],None,Evidence(),20000)):
                result=report(source,journal,expected_model_sha=sha)
            self.assertEqual(result['items']['jap:Xanax']['models']['challenger']['successes'],1)
            self.assertEqual(journal.read_bytes(),before);self.assertEqual(source.read_bytes(),b'untouched')
            with self.assertRaises(ValueError):report(source,journal,expected_model_sha='b'*40)
            with self.assertRaises(ValueError):report(journal,journal,expected_model_sha=sha)


if __name__=='__main__':unittest.main()
