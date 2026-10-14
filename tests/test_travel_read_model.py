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


class BoardTests(unittest.TestCase):
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
            'policy':'median','player_flight_seconds':1020,'model_sha':'source-a'}}
        self.assertTrue(build_board(data,now=T)['rows'][0]['evidence']['applies_to_selected_trip'])
        override=build_board(data,now=T,flight_overrides={'mex':1500})
        self.assertFalse(override['rows'][0]['evidence']['applies_to_selected_trip'])
        data['model_sha']='source-b'
        self.assertFalse(build_board(data,now=T)['rows'][0]['evidence']['applies_to_selected_trip'])


if __name__=="__main__":unittest.main()
