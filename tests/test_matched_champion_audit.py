import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research import matched_champion_audit as m


class MatchedTests(unittest.TestCase):
    def test_future_observations_receipts_and_gap_end_hidden_from_native(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.sqlite';target=Path(td)/'causal.sqlite'
            with sqlite3.connect(source) as c:
                c.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                CREATE TABLE poll_heartbeats(timestamp,mode,success);
                CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
                INSERT INTO stock_history VALUES(1,90,'can','Xanax',0,'a'),(2,110,'can','Xanax',900,'a');
                INSERT INTO poll_heartbeats VALUES(99,'poll-cycle',1),(111,'poll-cycle',1);
                INSERT INTO collection_gaps VALUES(80,105),(110,120);''')
            before=source.read_bytes();m.causal_copy(source,target,100)
            with sqlite3.connect(target) as c:
                self.assertEqual(c.execute('SELECT timestamp,quantity FROM stock_history').fetchall(),[(90,0)])
                self.assertEqual(c.execute('SELECT MAX(timestamp) FROM poll_heartbeats').fetchone()[0],99)
                self.assertEqual(c.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps').fetchall(),[(80,None)])
            self.assertEqual(source.read_bytes(),before)

    def test_missing_native_not_substituted_and_worker_only_sees_slice(self):
        self.assertEqual(m.native_plan('causal.sqlite','jap:Xanax',100)['status'],'NATIVE_ADAPTER_UNVERIFIED')
        result=type('Result',(),{'stdout':json.dumps(dict(status='RESEARCH_PROPOSAL_ONLY',recommended_departure_timestamp=120))})()
        with patch.object(m.subprocess,'run',return_value=result) as child:
            self.assertEqual(m.native_plan('causal.sqlite','can:Xanax',100)['departure'],120)
        self.assertIn('causal.sqlite',child.call_args.args[0])
        self.assertNotIn('truth.sqlite',child.call_args.args[0])

    def test_actual_native_worker_needs_no_http_library_or_provider(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.sqlite'
            with sqlite3.connect(source) as c:
                c.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                CREATE TABLE poll_heartbeats(timestamp,mode,success);
                CREATE TABLE collection_gaps(start_timestamp,end_timestamp,reason);
                INSERT INTO stock_history VALUES(1,90,'can','Xanax',0,'a');
                INSERT INTO poll_heartbeats VALUES(99,'poll-cycle',1);''')
            before=source.read_bytes();r=m.native_plan(source,'can:Xanax',100)
            self.assertEqual(r['status'],'INSUFFICIENT_HISTORICAL_FEATURES',r)
            self.assertEqual(source.read_bytes(),before)

    def test_true_zero_and_availability_loss_are_distinct(self):
        rows=[(0,0,'a'),(20,100,'a'),(40,20,'a'),(50,0,'a'),(60,100,'b')]
        r=m.supply_audit(rows,lambda a,b:False,70)
        self.assertEqual(r['events']['observed_availability_losses'],1)
        self.assertEqual(r['events']['observed_true_zero_transitions'],1)
        self.assertEqual(r['strict_completed_cycles'],[]) # first zero was left censored
        self.assertEqual(r['observed_interval_seconds']['ambiguous_seconds'],10)

    def test_historical_supply_window_ignores_future_transitions(self):
        rows=[(0,10,'a'),(20,0,'a'),(40,100,'a'),(60,0,'a'),(100,100,'a')]
        r=m.supply_audit(rows,lambda a,b:False,70,start_epoch=10)
        self.assertEqual(r['strict_completed_cycles'][0]['end'],60)
        self.assertEqual(r['latest_strict_cycle_age_hours'],10/3600)
        self.assertEqual(r['events']['observed_restock_transitions'],1)

    def test_exact_predeclared_nine_hours_and_explicit_coverage(self):
        self.assertEqual(len(m.ISSUES),9)
        self.assertEqual(len(set(m.ISSUES)),9)
        records=[dict(mode='x',outcome='SUCCESS',departure=120,issued=100,status='PLAN'),
                 dict(mode='x',outcome='ABSTAIN',departure=None,issued=200,status='TIMEOUT')]
        r=m.summarize(records)['x']
        self.assertEqual(r['success_fraction'],1);self.assertEqual(r['proposal_coverage'],.5)
        self.assertEqual(r['statuses']['TIMEOUT'],1)

    def test_comparison_uses_only_same_issue_both_known(self):
        records=[dict(mode='native_specialist',issued=100,outcome='FAILURE'),
                 dict(mode='native_specialist',issued=200,outcome='ABSTAIN'),
                 dict(mode='x',issued=100,outcome='SUCCESS'),
                 dict(mode='x',issued=200,outcome='SUCCESS')]
        r=m.paired_native(records)['x']
        self.assertEqual(r['both_known'],1)
        self.assertEqual(r['challenger_only_success'],1)

    def test_reconfirmation_generates_plans_only_from_past_rows(self):
        t=1792255500;seen=[]
        class History:
            def __init__(self,crosses):self.last=None
            def add(self,row):self.last=row
            def plans(self,issued,**kwargs):
                seen.append((issued,self.last[0]))
                return {'leave_now_control':dict(departure=issued,status='CONTROL')}
        class Evidence:
            def score(self,arrival):return ('SUCCESS','TEST',None)
        data=([(t-10,0,'a'),(t+300,100,'a'),(t+10000,99999,'future')],
              [t,t+300,t+600,t+900],lambda a,b:False,Evidence(),t+50000)
        with patch.object(m,'ISSUES',(t,)),patch.object(m,'WAIT',600), \
             patch.object(m,'History',History),patch.object(m,'source_data',return_value=data), \
             patch.object(m,'rate_plan',return_value=dict(departure=None,status='NONE')):
            r=m.xanax_reconfirmation('truth.sqlite',model_sha='a'*40)
        self.assertTrue(all(observed<=issued for issued,observed in seen))
        self.assertEqual(seen[0],(t,t-10))
        self.assertEqual(r['items']['can:Xanax']['replanned']['leave_now_control']['known'],1)
        self.assertEqual(r['items']['can:Xanax']['frozen_records'][0]['departure'],t+15)
