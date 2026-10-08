"""Production-branch-specific contract for private canary adoption.

Do not modify profitability graph routes, Discord collector, or existing V2.
"""
from __future__ import annotations
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from web.app import app

TOKEN="0123456789abcdef"*3

class ProfitabilityCanaryTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)

    def test_both_live_routes_retained_and_canary_registered(self):
        paths={getattr(r,"path",None) for r in app.routes}
        for path in ("/api/history","/api/catalog","/api/admin/health",
                     "/api/research/champion-shadow","/admin"):
            self.assertIn(path,paths)
        from web.app import api_history
        symbols=set(api_history.__code__.co_names)
        for symbol in ("profitability_for_item","get_latest_item_snapshot",
                       "_get_prediction_nonblocking","_get_analysis_nonblocking",
                       "get_recent_active_forecasts"):
            self.assertIn(symbol,symbols)
        self.assertNotIn("research_candidate",symbols)

    def test_disabled_private_route_does_not_expose_catalog(self):
        with patch.dict(os.environ,{
            "TORN_FREN_CHAMPION_SHADOW_ENABLED":"0",
            "TORN_FREN_CHAMPION_SHADOW_TOKEN":TOKEN,
            "TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED":"0"
        }):
            resp=self.client.get("/api/research/champion-shadow",
                params={"country":"can","item":"Fire Hydrant"},
                headers={"X-Torn-Fren-Shadow-Token":TOKEN})
        self.assertEqual(resp.status_code,404)

    def test_private_route_requires_authentication(self):
        with patch.dict(os.environ,{
            "TORN_FREN_CHAMPION_SHADOW_ENABLED":"1",
            "TORN_FREN_CHAMPION_SHADOW_TOKEN":TOKEN,
            "TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED":"0"
        }):
            for headers in ({},{"X-Torn-Fren-Shadow-Token":"incorrect"}):
                resp=self.client.get("/api/research/champion-shadow",
                    params={"country":"can","item":"Fire Hydrant"},headers=headers)
                self.assertEqual(resp.status_code,403)

    def test_existing_history_still_includes_v2_and_profitability(self):
        rows=[{"timestamp":1790000000,"quantity":54}]
        v2={"display_prediction":{"estimate_timestamp":1790001200,
            "recommended_arrival_timestamp":1790001200,
            "travel_reliability":"research-safe"},
            "model_evidence_tier":"test"}
        from web import app as web_module
        with patch.object(web_module,"get_item_history_since",return_value=rows), \
             patch.object(web_module,"get_latest_item_snapshot",
               return_value={"cost":350,"timestamp":1790000000,"source":"test"}), \
             patch.object(web_module,"_get_analysis_nonblocking",
               return_value=({"current_stock":54,"events":[],"prediction":None},False)), \
             patch.object(web_module,"profitability_for_item",
               return_value=({"net_profit":4567},{"error":None})), \
             patch.object(web_module,"_get_prediction_nonblocking",
               return_value=(v2,False)), \
             patch.object(web_module,"get_recent_active_forecasts",return_value=[]):
            resp=self.client.get("/api/history",params={
              "country":"can","item":"Fire Hydrant","minutes":1440})
        self.assertEqual(resp.status_code,200,resp.text)
        data=resp.json()
        self.assertEqual(data["analysis"]["prediction_v2"],v2)
        self.assertEqual(data["analysis"]["profitability"],{"net_profit":4567})
        self.assertEqual(data["analysis"]["current_cost"],350)
        self.assertEqual(data["analysis"]["prediction"]["estimate_timestamp"],1790001200)
        self.assertNotIn("challenger",data["analysis"])

if __name__=="__main__":
    unittest.main()
