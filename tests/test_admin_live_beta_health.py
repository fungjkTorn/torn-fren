import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from services.admin_live_beta_health import read_live_beta_health


class AdminBetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.snapshot=self.root/'latest.json';self.ledger=self.root/'forecasts.sqlite'
        self.now=1793000000
        self.data={'schema_version':1,'asof_epoch':self.now-30,'published_epoch':self.now-20,
            'valid_until_epoch':self.now+100,'source_heartbeat_epoch':self.now-40,
            'model_sha':'model','publisher_sha':'publisher','items':{
                'can:Crocus':{'decision':{'status':'MODEL_ABSTAIN'},'country_clock':{
                    'received_epoch':self.now-30,'reported_update_epoch':self.now-40,'clock_status':'REPORTED'}}}}
        with sqlite3.connect(self.ledger) as con:
            con.executescript('CREATE TABLE publications(issued INTEGER PRIMARY KEY,published,snapshot_sha); CREATE TABLE issues(item,issued,model_sha,payload,PRIMARY KEY(item,issued));')
            con.execute('INSERT INTO publications VALUES(?,?,?)',(self.now-30,self.now-20,'digest'))
            con.execute('INSERT INTO issues VALUES(?,?,?,?)',('can:Crocus',self.now-30,'model','{}'))
        self.save()
    def tearDown(self):self.tmp.cleanup()
    def save(self):self.snapshot.write_text(json.dumps(self.data))
    def read(self):return read_live_beta_health(self.now,snapshot=self.snapshot,ledger=self.ledger,expected_items=1)

    def test_fresh_no_advice_is_healthy_and_read_only(self):
        before=self.ledger.read_bytes();result=self.read()
        self.assertEqual('healthy',result['status']);self.assertEqual(0,result['items_with_advice'])
        self.assertEqual('current',result['ledger_status']);self.assertEqual('model',result['model_sha'])
        self.assertEqual('publisher',result['publisher_sha']);self.assertEqual(before,self.ledger.read_bytes())

    def test_expiry_country_staleness_and_incomplete_roster_are_visible(self):
        self.data['valid_until_epoch']=self.now-1
        self.data['items']['can:Crocus']['country_clock']['reported_update_epoch']=self.now-200
        self.save();result=self.read()
        self.assertEqual('delayed',result['status']);self.assertIn('snapshot expired',result['issues'])
        self.assertEqual('stale',result['countries']['can'])
        self.assertEqual('delayed',read_live_beta_health(self.now,snapshot=self.snapshot,ledger=self.ledger,expected_items=10)['status'])

    def test_wrong_ledger_identity_is_not_healthy(self):
        with sqlite3.connect(self.ledger) as con:con.execute("UPDATE issues SET model_sha='wrong'")
        self.assertEqual('behind_or_identity_mismatch',self.read()['ledger_status'])
        self.assertEqual('delayed',self.read()['status'])

    def test_bad_or_future_snapshot_and_missing_ledger_fail_closed(self):
        self.data['published_epoch']=self.now+60;self.save()
        self.assertEqual('unavailable',self.read()['status'])
        self.data['published_epoch']=self.now-20;self.save();self.ledger.unlink()
        self.assertEqual('delayed',self.read()['status']);self.assertFalse(self.ledger.exists())
        self.snapshot.write_text('{broken')
        self.assertEqual('unavailable',self.read()['status'])


if __name__=='__main__':unittest.main()
