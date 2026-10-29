"""Graph compatibility must distinguish current stock from a predicted restock."""
import copy
import unittest
from web.first_release_bridge import attach_history
from test_first_release_schedule import NOW,event,forecast
from services.first_release_schedule import build_first_release_decision


class GraphWindowContractTests(unittest.TestCase):
    def build(self,current=False):
        key='can:Crocus';f=forecast(key,[event(NOW+2400)],current=event(NOW-600,7200) if current else None)
        f['current_stock_window']=f.pop('current_stock_window',None)
        d=build_first_release_decision(f,now=NOW,flight_seconds=1200,poll_age_seconds=0)
        row={'item_key':key,'forecast':f,'decision':d,'live':{},'valid_until_epoch':NOW+180}
        board={'status':'LIVE_BETA','rows':[row]}
        payload={'country':'can','item':'Crocus','rows':[{'timestamp':NOW,'quantity':500}],
                 'analysis':{'current_stock':500,'current_cost':100,'profitability':{'roi':.2}}}
        before=copy.deepcopy(row)
        result=attach_history(payload,board)
        self.assertEqual(before,row)
        self.assertEqual(500,result['analysis']['current_stock'])
        self.assertEqual({'roi':.2},result['analysis']['profitability'])
        return result['analysis']['prediction'],d,f

    def test_current_stock_is_not_a_new_drop_at_calculation_time(self):
        p,d,f=self.build(current=True)
        self.assertEqual(0,d['selected_restock_event_index'])
        self.assertEqual('CURRENT_STOCK',p['opportunity_kind'])
        self.assertEqual('ARRIVAL_REFERENCE',p['estimate_kind'])
        self.assertIsNone(p['restock_estimate_timestamp'])
        self.assertIsNone(p['restock_window_start_timestamp'])
        self.assertEqual(d['estimated_arrival_epoch'],p['estimate_timestamp'])
        self.assertNotEqual(f['asof_epoch'],p['estimate_timestamp'])

    def test_future_restock_remains_an_explicit_estimate(self):
        p,d,f=self.build()
        self.assertEqual(1,d['selected_restock_event_index'])
        self.assertEqual('PREDICTED_STOCK_WINDOW',p['opportunity_kind'])
        self.assertEqual(NOW+2400,p['restock_estimate_timestamp'])
        self.assertEqual(NOW+2340,p['restock_window_start_timestamp'])
        self.assertEqual(NOW+2460,p['restock_window_end_timestamp'])

    def test_travel_windows_use_the_exact_server_flight_geometry(self):
        for current in (False,True):
            with self.subTest(current=current):
                p,d,f=self.build(current)
                self.assertEqual(d['estimated_departure_epoch'],p['departure_window_start_timestamp'])
                self.assertEqual(d['estimated_departure_deadline_epoch'],p['departure_window_end_timestamp'])
                self.assertEqual(p['departure_window_start_timestamp']+1200,p['arrival_window_start_timestamp'])
                self.assertEqual(p['departure_window_end_timestamp']+1200,p['arrival_window_end_timestamp'])
                self.assertEqual(p['arrival_window_end_timestamp'],p['window_end_timestamp'])
                self.assertLess(p['arrival_window_end_timestamp'],p['target_depletion_timestamp'])

    def test_unavailable_model_preserves_observed_history_without_inventing_windows(self):
        row={'item_key':'can:Crocus','forecast':{},'decision':{'estimated_departure_epoch':None,'status':'STALE_DATA'},'live':{}}
        result=attach_history({'country':'can','item':'Crocus','rows':[{'quantity':50}],'analysis':{'current_stock':50}}, {'status':'STALE_DATA','rows':[row]})
        self.assertIsNone(result['analysis']['prediction'])
        self.assertEqual(50,result['analysis']['current_stock'])
        self.assertEqual([{'quantity':50}],result['rows'])

if __name__=='__main__':unittest.main()
