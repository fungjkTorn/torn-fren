from copy import deepcopy
import unittest
from research.current_stock_continuation import extend_current_stock,POLICY
from services.first_release_schedule import build_first_release_decision
from research.corrected_challengers import NEXT_SIX_MODELS


class ContinuationTests(unittest.TestCase):
    def base(self):
        return {'item_key':'uni:Xanax','status':'CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS',
            'current_stock_window':None,'observed_current_quantity':2500,
            'arrival_stock_threshold':31,'restock_events':[],'forecast_event_count':0}

    def test_long_phase_can_leave_now_without_native_delay_or_fake_restock(self):
        now=1800000000
        rows=[(now-100*86400+i*600,5000-i*10,'p') for i in range(50)]
        before=deepcopy(rows);f=self.base();f['asof_epoch']=now;old=deepcopy(f)
        f['asof_epoch']=now
        out=extend_current_stock(f,rows,[],now)
        self.assertEqual(POLICY,out['current_stock_continuation']['policy'])
        self.assertEqual(49,out['current_stock_continuation']['depletion_rate_samples'])
        self.assertEqual([],out['restock_events']);self.assertEqual(f,old);self.assertEqual(rows,before)
        d=build_first_release_decision(out,now=now,flight_seconds=6360,poll_age_seconds=0,
            model_roster=NEXT_SIX_MODELS,current_stock_leave_now=True,
            timing_choice=lambda **kw:self.fail('current stock must not wait for native timing'))
        self.assertEqual(now,d['estimated_departure_epoch']);self.assertEqual(now+6360,d['estimated_arrival_epoch'])
        self.assertEqual(0,d['selected_restock_event_index']);self.assertEqual(0,d['arrival_grace_seconds'])

    def test_future_rows_gap_pairs_and_provider_changes_cannot_supply_rate(self):
        f=self.base();now=1000
        rows=[(10,5000,'p'),(20,4000,'q'),(30,3000,'q'),(40,2000,'q'),(1001,1000,'q'),(1002,0,'q')]
        self.assertEqual(f,extend_current_stock(f,rows,[(20,40)],now))
        for q in (0,1,30):
            f=self.base();f['observed_current_quantity']=q
            self.assertEqual(f,extend_current_stock(f,rows,[],now))

    def test_stock_is_not_assumed_to_last_until_arrival(self):
        f=self.base();now=10000;f['asof_epoch']=now
        rows=[(100+i,10000-i*1000,'p') for i in range(6)]
        out=extend_current_stock(f,rows,[],now)
        d=build_first_release_decision(out,now=now,flight_seconds=6360,poll_age_seconds=0,
            model_roster=NEXT_SIX_MODELS,current_stock_leave_now=True)
        self.assertIsNone(d['estimated_departure_epoch'])
        self.assertFalse(out['current_stock_window']['expected_departure_reachable'])

    def test_existing_windows_other_items_and_other_failure_states_unchanged(self):
        for changes in ({'item_key':'sou:Xanax'},{'current_stock_window':{'existing':True}}, {'status':'CURRENT_PHASE_UNKNOWN'}):
            f=self.base();f.update(changes)
            self.assertIs(f,extend_current_stock(f,[],[],1000))

    def test_real_observation_type_and_future_suffix_match_tuple_inputs(self):
        from research.v128_full24_earliest_shadow import StockObservation
        f=self.base();f['asof_epoch']=10000
        rows=[(1000+i*60,5000-i*10,'p') for i in range(10)]
        expected=extend_current_stock(f,rows,[],10000)
        observations=[StockObservation(*r) for r in rows+[(10001,0,'p')]]
        self.assertEqual(expected,extend_current_stock(f,observations,[],10000))
