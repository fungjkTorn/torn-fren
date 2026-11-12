import json
import tempfile
import unittest
from pathlib import Path
from services.travel_read_model import build_board,SnapshotCache
from services.travel_window_policy import project_policy

T=1791910800


def snapshot():
    return {"asof_epoch":T,"source_heartbeat_age_seconds":10,"items":{
        "mex:Jaguar Plushie":{"item_key":"mex:Jaguar Plushie","asof_epoch":T,
            "flight_seconds":1020,"status":"EVENT_TIMELINE_FORECAST_AVAILABLE",
            "observed_current_quantity":200,"last_quantity_change_epoch":T-800,
            "current_stock_window":{"predicted_stock_below_30_epoch":T+1800},
            "restock_events":[{"predicted_restock_epoch":T+2000,
                "restock_early_epoch":T+1800,"restock_late_epoch":T+2400,
                "predicted_stock_below_30_epoch":T+3200}]}}}


def departure_snapshot(departure=T+1200):
    data=snapshot();data['model_sha']='a'*40
    data['item_departure_recommendations']={'mex:Jaguar Plushie':{
        'item_key':'mex:Jaguar Plushie','asof_epoch':T,'model_sha':'a'*40,
        'policy':'zero_path_analog70','model_name':'causal_complete_stock_paths_v1',
        'player_flight_seconds':1020,'target_quantity':30,'depletion_stock_quantity':0,
        'event_timing_prediction_supported':False,'departure_epoch':departure,
        'status':'HISTORICAL_PATH_PROPOSAL'}}
    return data


class BoardTests(unittest.TestCase):
    def test_publication_tolerance_has_fixed_deadline_and_actual_landing(self):
        data=departure_snapshot(T)
        record=data['item_departure_recommendations']['mex:Jaguar Plushie']
        record['execution_policy']='publication_delay_30s_v1'
        before=json.dumps(data,sort_keys=True)
        for delay in (0,5,15,30):
            row=build_board(data,now=T+delay)['rows'][0]
            self.assertEqual(row['departure_epoch'],T+delay)
            self.assertEqual(row['arrival_epoch'],T+delay+1020)
            self.assertEqual(row['departure_deadline_epoch'],T+30)
            self.assertEqual(row['decision']['model_departure_epoch'],T)
            self.assertEqual(row['decision']['publication_tolerance_seconds'],30)
            self.assertEqual(len(row['event_timeline']),1)
        self.assertEqual(json.dumps(data,sort_keys=True),before)
        self.assertIsNone(build_board(data,now=T+31)['rows'][0]['departure_epoch'])
        data['source_heartbeat_age_seconds']=170
        row=build_board(data,now=T+5)['rows'][0]
        self.assertEqual(row['departure_deadline_epoch'],T+10)
        self.assertIsNone(build_board(data,now=T+11)['rows'][0]['departure_epoch'])

    def test_tolerance_never_extends_future_points_stale_data_or_custom_flights(self):
        for departure,now,age,override in ((T+120,T+121,10,None),
                (T,T+20,161,None),(T,T+300,0,None),
                (T,T+10,10,{'mex':1500})):
            data=departure_snapshot(departure);data['source_heartbeat_age_seconds']=age
            data['item_departure_recommendations']['mex:Jaguar Plushie']['execution_policy']='publication_delay_30s_v1'
            row=build_board(data,now=now,flight_overrides=override)['rows'][0]
            self.assertIsNone(row['departure_epoch'])
            self.assertIsNone(row['arrival_epoch'])

    def test_point_evidence_is_not_reused_for_publication_tolerance(self):
        data=departure_snapshot(T)
        data['item_departure_recommendations']['mex:Jaguar Plushie']['execution_policy']='publication_delay_30s_v1'
        data['item_evidence']={'mex:Jaguar Plushie':{'successes':99,'resolved_arrivals':100,
            'policy':'zero_path_analog70','player_flight_seconds':1020,'model_sha':'a'*40,
            'departure_model':'causal_complete_stock_paths_v1','evidence_role':'departure'}}
        self.assertFalse(build_board(data,now=T+10)['rows'][0]['evidence']['applies_to_selected_trip'])
        data['item_evidence']['mex:Jaguar Plushie']['execution_policy']='publication_delay_30s_v1'
        self.assertTrue(build_board(data,now=T+10)['rows'][0]['evidence']['applies_to_selected_trip'])
        data['item_departure_recommendations']['mex:Jaguar Plushie']['execution_policy']='arbitrary_10_minutes'
        with self.assertRaises(ValueError):build_board(data,now=T)

    def test_explicit_departure_keeps_independent_event_graph_and_exact_landing(self):
        data=departure_snapshot();before=json.dumps(data,sort_keys=True)
        row=build_board(data,now=T)['rows'][0]
        self.assertEqual(row['departure_epoch'],T+1200)
        self.assertEqual(row['arrival_epoch'],T+1200+1020)
        self.assertEqual(row['decision']['estimated_arrival_epoch'],T+1200+1020+10)
        self.assertEqual(row['departure_deadline_epoch'],T+1200)
        self.assertEqual(row['decision']['forecast_events'],[])
        self.assertEqual(len(row['event_timeline']),1)
        self.assertEqual(row['decision']['depletion_stock_quantity'],0)
        self.assertEqual(row['departure_source'],'explicit_recommendation')
        self.assertEqual(json.dumps(data,sort_keys=True),before)

    def test_departure_abstention_override_expiry_never_falls_back_to_event_adapter(self):
        for data,now,overrides in ((departure_snapshot(None),T,None),
                (departure_snapshot(T+10),T+11,None),
                (departure_snapshot(),T,{'mex':1500}),
                (departure_snapshot(),T+171,None)):
            row=build_board(data,now=now,flight_overrides=overrides)['rows'][0]
            self.assertIsNone(row['departure_epoch'])
            self.assertIsNone(row['arrival_epoch'])
            self.assertEqual(len(row['event_timeline']),1)
        # Even a very recent global poll cannot renew a frozen model issue.
        data=departure_snapshot();data['source_heartbeat_age_seconds']=0
        row=build_board(data,now=T+300)['rows'][0]
        self.assertEqual(row['decision']['status'],'STALE_DATA')

    def test_mixed_departure_identity_source_issue_and_anchor_rejected(self):
        for field,value in (('item_key','uni:Nessie Plushie'),('asof_epoch',T-300),
                ('model_sha','b'*40),('depletion_stock_quantity',30),
                ('departure_epoch',T-1),('event_timing_prediction_supported',True)):
            data=departure_snapshot();data['item_departure_recommendations']['mex:Jaguar Plushie'][field]=value
            with self.assertRaises(ValueError):build_board(data,now=T)

    def test_event_evidence_cannot_be_borrowed_for_departure_model(self):
        data=departure_snapshot();data['item_evidence']={'mex:Jaguar Plushie':{
            'successes':90,'resolved_arrivals':100,'policy':'zero_path_analog70',
            'player_flight_seconds':1020,'model_sha':'a'*40,
            'forecast_model':'v163','cycle_window':'all'}}
        self.assertFalse(build_board(data,now=T)['rows'][0]['evidence']['applies_to_selected_trip'])
        data['item_evidence']['mex:Jaguar Plushie'].update(
            departure_model='causal_complete_stock_paths_v1',evidence_role='departure')
        self.assertTrue(build_board(data,now=T)['rows'][0]['evidence']['applies_to_selected_trip'])
        self.assertFalse(build_board(data,now=T,flight_overrides={'mex':1500})['rows'][0]['evidence']['applies_to_selected_trip'])

    def test_shared_buffer_flight_geometry_and_current_stock(self):
        f=snapshot()["items"]["mex:Jaguar Plushie"]
        q=project_policy(f,now=T,poll_age_seconds=10,kind="quarter")
        self.assertEqual(q["estimated_departure_epoch"],T+2000+300-1020-10)
        self.assertEqual(q["departure_countdown_seconds"],1270)
        c=project_policy(f,now=T,poll_age_seconds=10,kind="current_quarter")
        self.assertEqual(c["estimated_departure_epoch"],T)
        self.assertEqual(c["selected_restock_event_index"],0)
        stale=project_policy(f,now=T,poll_age_seconds=190,kind="current_quarter")
        self.assertIsNone(stale["estimated_departure_epoch"])

    def test_player_landing_clock_excludes_scoring_grace_and_delta_age_not_stale(self):
        data=snapshot();data["item_policies"]={"mex:Jaguar Plushie":"quarter"}
        r=build_board(data,now=T)["rows"][0]
        self.assertEqual(r["arrival_epoch"],r["departure_epoch"]+1020)
        self.assertEqual(r["decision"]["estimated_arrival_epoch"],r["arrival_epoch"]+10)
        self.assertEqual(r["observed_quantity"],200)
        self.assertNotEqual(r["decision"]["status"],"STALE_DATA")
        self.assertEqual(r["category"],"Plushies")
        self.assertIn('country=mex',r["graph_url"])
        changed=build_board(data,now=T,flight_overrides={"mex":1500})["rows"][0]
        self.assertEqual(changed["arrival_epoch"],changed["departure_epoch"]+1500)

    def test_source_age_increases_and_evidence_never_calibrated(self):
        data=snapshot();data["item_evidence"]={"mex:Jaguar Plushie":{"successes":85,"resolved_arrivals":100,"policy":"median"}}
        board=build_board(data,now=T+200);r=board["rows"][0]
        self.assertEqual(board["source_poll_age_seconds"],210)
        self.assertIsNone(r["departure_epoch"])
        self.assertFalse(r["evidence"]["prospective_certified"])
        self.assertFalse(board["calibrated_arrival_probability_available"])

    def test_cache_refreshes_and_rejects_mixed_issue_and_overlarge_roster(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'events.json';p.write_text(json.dumps(snapshot()));cache=SnapshotCache()
            a=cache.read(p);self.assertIs(a,cache.read(p))
            data=snapshot();data["source_heartbeat_age_seconds"]=9
            nextfile=p.with_suffix('.next');nextfile.write_text(json.dumps(data));nextfile.replace(p)
            self.assertEqual(cache.read(p)["source_heartbeat_age_seconds"],9)
        data=snapshot();data["items"]["mex:Jaguar Plushie"]["asof_epoch"]=T-300
        with self.assertRaises(ValueError):build_board(data,now=T)
        with self.assertRaises(ValueError):build_board({"asof_epoch":T,"items":dict.fromkeys(range(251),{})},now=T)

    def test_default_flight_results_never_borrowed_for_custom_flight_or_new_model(self):
        data=snapshot();data['model_sha']='source-a'
        data['item_evidence']={'mex:Jaguar Plushie':{'successes':85,'resolved_arrivals':100,
            'policy':'median','player_flight_seconds':1020,'model_sha':'source-a',
            'forecast_model':'v163','cycle_window':'all'}}
        self.assertTrue(build_board(data,now=T)['rows'][0]['evidence']['applies_to_selected_trip'])
        override=build_board(data,now=T,flight_overrides={'mex':1500})
        self.assertFalse(override['rows'][0]['evidence']['applies_to_selected_trip'])
        data['items']['mex:Jaguar Plushie']['cycle_window']=8
        self.assertFalse(build_board(data,now=T)['rows'][0]['evidence']['applies_to_selected_trip'])
        data['items']['mex:Jaguar Plushie']['cycle_window']='all'
        data['model_sha']='source-b'
        self.assertFalse(build_board(data,now=T)['rows'][0]['evidence']['applies_to_selected_trip'])


if __name__=="__main__":unittest.main()
