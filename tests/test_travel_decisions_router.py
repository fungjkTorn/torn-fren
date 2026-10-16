import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from web.travel_decisions_router import router
from test_travel_read_model import snapshot,departure_snapshot,T
from web.travel_decisions_router import shared_item


class RouterTests(unittest.TestCase):
    def test_graph_and_travel_board_consume_identical_selected_recommendation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'selected.json';p.write_text(json.dumps(departure_snapshot()))
            with patch.dict(os.environ,{'TORN_FREN_TRAVEL_DECISIONS_BETA':'1',
                    'TORN_FREN_TRAVEL_EVENT_SNAPSHOT':str(p)}),patch('web.travel_decisions_router.time.time',return_value=T):
                graph=shared_item('mex','Jaguar Plushie',now=T)
                api=self.client.get('/api/travel-decisions').json()
                self.assertEqual(graph['row'],api['rows'][0])
                self.assertEqual(graph['row']['departure_epoch'],T+1200)
                p.write_text('{invalid')
                self.assertIsNone(shared_item('mex','Jaguar Plushie',now=T)['row'])

    def setUp(self):
        app=FastAPI();app.include_router(router);self.client=TestClient(app)

    def test_routes_disabled_by_default(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(self.client.get('/travel-decisions').status_code,404)
            self.assertEqual(self.client.get('/api/travel-decisions').status_code,404)

    def test_read_only_snapshot_personal_flight_and_failure(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'events.json';p.write_text(json.dumps(snapshot()));before=p.read_bytes()
            with patch.dict(os.environ,{"TORN_FREN_TRAVEL_DECISIONS_BETA":"1","TORN_FREN_TRAVEL_EVENT_SNAPSHOT":str(p)}),patch('web.travel_decisions_router.time.time',return_value=T):
                page=self.client.get('/travel-decisions')
                self.assertEqual(page.status_code,200)
                self.assertIn('Research preview',page.text)
                api=self.client.get('/api/travel-decisions?country=mex&flight_seconds=1500')
                self.assertEqual(api.status_code,200)
                self.assertEqual(api.json()['rows'][0]['decision']['player_flight_seconds'],1500)
                self.assertEqual(self.client.get('/api/travel-decisions?country=mex').status_code,400)
                self.assertEqual(self.client.get('/api/travel-decisions?flight_seconds=10').status_code,422)
                self.assertEqual(self.client.get('/api/travel-decisions?country=xxx&flight_seconds=1500').status_code,503)
                self.assertEqual(p.read_bytes(),before)
                p.write_text('{invalid')
                self.assertEqual(self.client.get('/api/travel-decisions').status_code,503)
            self.assertNotEqual(p.read_bytes(),before) # Only our intentional fixture edit.


if __name__=='__main__':unittest.main()
