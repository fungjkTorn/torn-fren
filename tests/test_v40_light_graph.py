"""V40 lightweight observed-history mode never schedules prediction work.

All tests use mocked services; no network, live database, or systemd changes.
"""
import os
import unittest
from unittest.mock import patch
from web import app as webapp


class V40LiteWeb(unittest.TestCase):
    def serve(self, *,legacy=False, lite=True):
        state={"timestamp":1791590000,"quantity":30,"cost":500,"source":"yata"}
        rows=[{"timestamp":1791590000,"quantity":30,"source":"yata","anchor":False}]
        flags={"TORN_FREN_V40_LIGHT_GRAPH":"1" if lite else "0",
               "TORN_FREN_V38_REVISION_CACHE":"1"}
        with patch.dict(os.environ,flags):
            with (
                patch.object(webapp,"get_latest_item_snapshot",return_value=state),
                patch.object(webapp,"v38_source_revision",return_value=("FRESH",("v40","rev"))),
                patch.object(webapp,"_V39_HISTORY_CACHE") as cached,
                patch.object(webapp,"_get_analysis_nonblocking") as analysis,
                patch.object(webapp,"_get_prediction_nonblocking") as predict,
                patch.object(webapp,"profitability_for_item",return_value=({"net_profit_per_item":123},{})),
                patch.object(webapp,"get_recent_active_forecasts",return_value=[]) as audits
            ):
                cached.get.return_value=rows
                analysis.return_value=({"current_stock":30,"events":[],"prediction":None},False)
                predict.return_value=({"status":"waiting_for_restock","display_prediction":None},False)
                result=webapp.api_history(country="uni",item="Heather",minutes=60,legacy_v2=legacy)
                return result,analysis.call_count,predict.call_count,audits.call_count,cached.get.call_count

    def test_default_lite_preserves_history_and_profit_without_v2_threads(self):
        response,graph,pred,audits,cached=self.serve()
        self.assertEqual(response["rows"][0]["quantity"],30)
        self.assertEqual(response["analysis"]["profitability"]["net_profit_per_item"],123)
        self.assertEqual(response["analysis"]["current_stock"],30)
        self.assertEqual(response["analysis"]["prediction_v2"]["status"],"backup_available")
        self.assertIsNone(response["analysis"]["prediction"])
        self.assertEqual(response["analysis"]["forecast_history"],[])
        self.assertFalse(response["analysis"]["analysis_warming"])
        self.assertEqual((graph,pred,audits,cached),(0,0,0,1))
        self.assertTrue(response["analysis"]["light_graph_mode"])
        self.assertTrue(response["analysis"]["legacy_v2_backup_available"])

    def test_explicit_legacy_request_restores_original_analysis_v2_and_audits(self):
        result,graph,pred,audits,_=self.serve(legacy=True)
        self.assertEqual((graph,pred,audits),(1,1,1))
        self.assertFalse(result["analysis"]["light_graph_mode"])
        self.assertTrue(result["analysis"]["legacy_v2_backup_available"])

    def test_opt_in_off_preserves_original_v39_route(self):
        result,graph,pred,audits,_=self.serve(lite=False)
        self.assertEqual((graph,pred,audits),(1,1,1))
        self.assertFalse(result["analysis"]["light_graph_mode"])
        self.assertFalse(result["analysis"]["legacy_v2_backup_available"])

    def test_html_backup_button_is_explicit_and_expires(self):
        from pathlib import Path
        source=(Path(__file__).parents[1]/"web/static/index.html").read_text()
        self.assertIn('id="legacyV2Button"',source)
        self.assertIn('legacyV2UntilMs = 0',source)
        self.assertIn('10 * 60 * 1000',source)
        self.assertIn('&legacy_v2=true',source)
        self.assertIn('backup_available',source)

if __name__=="__main__": unittest.main()
