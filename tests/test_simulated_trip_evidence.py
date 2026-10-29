from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from services.restock_signatures import learn,events
from services.simulated_trip_evidence import advance,grade_trip,summary,initialize
from services import first_release_evidence as old


def recommendation(t,dep,anchor=100,end=1000):
    return {'item_key':'uni:Xanax','asof_epoch':t,'published_epoch':t,'_availability_anchor':anchor,
        'decision':{'estimated_departure_epoch':dep,'estimated_arrival_epoch':dep+100,
        'selected_restock_event_index':0,'valid_until_epoch':t+180},
        'forecast':{'current_stock_window':{'predicted_restock_epoch':anchor,'predicted_stock_below_30_epoch':end}}}


class SimulationTests(unittest.TestCase):
    def test_historical_refill_band_excludes_tiny_sales_and_learns_resets(self):
        rows=[]
        for i,q in enumerate([1,2,1,2200,2300,2400,2500,2500,2500]):rows.extend([(i*20+1,0,'a'),(i*20+2,q,'a')])
        for i in range(3):rows.extend([(300+i*20,3000,'a'),(301+i*20,2500,'a')])
        profile=learn(rows,[],400)
        self.assertEqual(2200,profile['normal_min']);self.assertEqual(2500,profile['reset_base'])
        detected=events(rows+[(500,4000,'a'),(501,2500,'a')],[],profile)
        self.assertEqual(4,sum(e['kind']=='SURPLUS_TO_BASE_RESET' for e in detected))
        self.assertFalse(any(e['quantity'] in (1,2) for e in detected))
        # Later refill values cannot affect the original training profile.
        self.assertEqual(profile,learn(rows+[(500,0,'a'),(501,9999,'a')],[],400))

    def test_revise_then_freeze_and_do_not_retest_each_leave_now(self):
        state={'active':None,'completed':[]};observed=[{'epoch':100}]
        state,frozen,_=advance(state,recommendation(110,200),observed,110);self.assertEqual([],frozen)
        state,frozen,changes=advance(state,recommendation(150,220),observed,150)
        self.assertIn('REVISED_BEFORE_DEPARTURE',[c['kind'] for c in changes])
        state,frozen,_=advance(state,recommendation(230,230),observed,230)
        self.assertEqual(220,frozen[0]['departure_epoch']);self.assertEqual(320,frozen[0]['arrival_epoch'])
        state,new,_=advance(state,recommendation(240,240),observed,240);self.assertEqual([],new)
        state,new,_=advance(state,recommendation(400,400,anchor=390),observed+[{'epoch':390}],400)
        self.assertEqual(1,len(new))

    def test_withdrawal_and_stale_plan_do_not_disappear(self):
        state={'active':None,'completed':[]}
        state,_,_=advance(state,recommendation(100,250),[],100)
        empty={'asof_epoch':200,'published_epoch':200,'decision':{}}
        state,frozen,changes=advance(state,empty,[],200)
        self.assertEqual([],frozen);self.assertEqual('WITHDRAWN_NO_ADVICE',changes[0]['kind'])
        state,_,_=advance(state,recommendation(300,600),[],300)
        state,frozen,changes=advance(state,None,[],700)
        self.assertEqual([],frozen);self.assertEqual('WITHDRAWN_STALE_BEFORE_DEPARTURE',changes[0]['kind'])

    def test_completed_identity_survives_expiry_and_another_tested_target(self):
        state={'active':None,'completed':[]};observed=[{'epoch':90}]
        state,frozen,_=advance(state,recommendation(100,100,anchor=90,end=130),observed,100)
        self.assertEqual(1,len(frozen))
        future=recommendation(200,200,anchor=500,end=800)
        future['_availability_anchor']=90
        future['decision']['selected_restock_event_index']=1
        future['decision']['forecast_events']=[{'index':1,'predicted_restock_epoch':500,'predicted_stock_below_30_epoch':800}]
        state,frozen,_=advance(state,future,observed,200);self.assertEqual(1,len(frozen))
        state,_,_=advance(state,{'asof_epoch':250,'decision':{}},observed,250)
        # Native forecasts can extend an expired stock window after forecasting
        # a future target. That does not create another current-restock trip.
        state,frozen,_=advance(state,recommendation(300,300,anchor=90,end=900),observed,300)
        self.assertEqual([],frozen)
        self.assertEqual(2,len(state['completed']))
        self.assertTrue(all('forecast' not in plan for plan in state['completed']))

    def test_restock_during_publication_does_not_shift_native_future_ordinal(self):
        with tempfile.TemporaryDirectory() as td:
            db=old.connect(Path(td)/'ledger.db');src=sqlite3.connect(':memory:')
            src.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
                CREATE TABLE poll_heartbeats(timestamp,mode,success);
                CREATE TABLE country_stock_observations(id INTEGER PRIMARY KEY,received_epoch,country,country_update_epoch,clock_status);''')
            src.executemany("INSERT INTO stock_history VALUES(?,?,'uni','Xanax',?,'a')",[(1,10,0),(2,110,100)])
            src.executemany("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",[(t,) for t in range(10,501,10)])
            src.executemany("INSERT INTO country_stock_observations(received_epoch,country,country_update_epoch,clock_status) VALUES(?,'uni',?,'REPORTED')",[(t,t) for t in range(10,501,10)])
            future=recommendation(100,120,anchor=110,end=900)
            future['published_epoch']=120;future['decision']['selected_restock_event_index']=1
            future['decision']['forecast_events']=[{'index':1,'predicted_restock_epoch':110,'predicted_stock_below_30_epoch':900}]
            for row in (future,recommendation(130,130,anchor=110,end=900)):
                old.record(db,row,model_sha='sha');db.execute('INSERT INTO publications VALUES(?,?,?)',(row['asof_epoch'],row['published_epoch'],'digest'))
            result=summary(db,src,item_key='uni:Xanax',model_sha='sha',cutoff=500)
            self.assertEqual(1,result['simulated_trips_total'])
            self.assertEqual(0,result['trips'][0]['origin_opening'])
            state=json.loads(db.execute('SELECT payload FROM simulation_cursors').fetchone()[0])
            self.assertEqual(110,state['completed'][0]['resolved_opening'])

    def test_future_target_becoming_current_is_not_a_second_test_after_a_miss(self):
        state={'active':None,'completed':[]}
        future=recommendation(100,100,anchor=500,end=900)
        future['decision']['selected_restock_event_index']=1
        future['decision']['forecast_events']=[{'index':1,'predicted_restock_epoch':500,'predicted_stock_below_30_epoch':900}]
        future['_availability_anchor']=0;future['_availability_openings']=[]
        state,frozen,_=advance(state,future,[],100);self.assertEqual(1,len(frozen))
        current=recommendation(700,700,anchor=650,end=1200);current['_availability_openings']=[650]
        state,frozen,_=advance(state,current,[{'epoch':650}],700)
        self.assertEqual([],frozen)  # Late observed target cannot overwrite/retry frozen trip.

    def test_variable_normal_band_is_not_split_and_positive_bulk_refill_counts(self):
        rows=[]
        for i,q in enumerate([1000,1200,1500,1800,2100,2500]*3):rows.extend([(i*20+1,0,'a'),(i*20+2,q,'a')])
        sig=learn(rows,[],500);self.assertEqual(1000,sig['normal_min'])
        detected=events([(600,1,'a'),(601,2000,'a'),(602,2001,'a')],[],sig)
        self.assertEqual(1,len(detected));self.assertEqual('IN_STOCK_BULK_REFILL',detected[0]['kind'])

    def test_arrival_does_not_require_restock_boundary_or_single_provider(self):
        receipt=[(990,990,'REPORTED')]
        for q,status in [(31,'SUCCESS'),(30,'FAILURE'),(0,'FAILURE')]:
            self.assertEqual(status,grade_trip(1000,[(900,q,'a'),(1010,q,'b')],[990,1010],[],1300,receipt)['status'])
        self.assertEqual('UNKNOWN',grade_trip(1000,[(900,100,'a')],[],[],1300,receipt)['status'])
        self.assertEqual('UNKNOWN',grade_trip(1000,[(900,100,'a')],[990,1010],[],1300,[])['status'])

    def test_backfill_restart_idempotency_and_immutable_frozen_trip(self):
        with tempfile.TemporaryDirectory() as td:
            db=old.connect(Path(td)/'ledger.db');src=sqlite3.connect(':memory:')
            src.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
            CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
            CREATE TABLE poll_heartbeats(timestamp,mode,success);
            CREATE TABLE country_stock_observations(id INTEGER PRIMARY KEY,received_epoch,country,country_update_epoch,clock_status);''')
            src.execute("INSERT INTO stock_history VALUES(1,10,'uni','Xanax',100,'a')")
            src.executemany("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",[(t,) for t in range(10,1001,10)])
            src.executemany("INSERT INTO country_stock_observations(received_epoch,country,country_update_epoch,clock_status) VALUES(?,'uni',?,'REPORTED')",[(t,t) for t in range(10,1001,10)])
            for t,dep in [(100,200),(150,220),(230,230)]:
                r=recommendation(t,dep);old.record(db,r,model_sha='sha');db.execute('INSERT INTO publications VALUES(?,?,?)',(t,t,'digest'))
            before=db.execute('SELECT * FROM issues').fetchall()
            result=summary(db,src,item_key='uni:Xanax',model_sha='sha',cutoff=1000)
            self.assertEqual(1,result['simulated_trips_total']);self.assertEqual(1,result['successes'])
            self.assertEqual('UNCONFIRMED_SEPARATE_FROM_ARRIVAL',result['trips'][0]['restock_identity_status'])
            self.assertEqual(result,summary(db,src,item_key='uni:Xanax',model_sha='sha',cutoff=1000))
            self.assertEqual(before,db.execute('SELECT * FROM issues').fetchall())
            with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE simulated_trips SET payload=\'{}\'')


if __name__=='__main__':unittest.main()
