"""Full /api/history function safety when V39 cache flags are enabled."""
import os
import unittest
from unittest.mock import patch

from web import app as webapp


class HistoryEndpointSafety(unittest.TestCase):
    def test_flagged_route_reuses_expensive_history_and_prediction(self):
        fresh={"timestamp":1791590000,"quantity":40,"cost":100,"source":"yata"}
        cached_rows=[{"timestamp":1791590000,"quantity":40,"source":"yata","anchor":False}]
        template={"current_stock":40,"events":[],"prediction":None}
        with patch.dict(os.environ,{"TORN_FREN_V38_REVISION_CACHE":"1"}):
            with patch.object(webapp,"get_latest_item_snapshot",return_value=fresh):
                with patch.object(webapp,"v38_source_revision",return_value=("FRESH",("rev",))) as gate:
                    with patch.object(webapp,"_V39_HISTORY_CACHE") as rows:
                        with patch.object(webapp,"_get_analysis_nonblocking",return_value=(template,False)) as graph:
                            with patch.object(webapp,"_get_prediction_nonblocking",
                                              return_value=({"status":"waiting","display_prediction":None},False)) as pred:
                                with patch.object(webapp,"profitability_for_item",return_value=(None,{})):
                                    with patch.object(webapp,"get_recent_active_forecasts",return_value=[]):
                                        rows.get.return_value=cached_rows
                                        result=webapp.api_history(country="uni",item="Heather",minutes=60)
        self.assertEqual(result["rows"],cached_rows)
        rows.get.assert_called_once()
        self.assertEqual(graph.call_args.kwargs["revision"],("rev",))
        self.assertEqual(pred.call_args.kwargs["revision"],("rev",))
        gate.assert_called_once()
        self.assertEqual(result["analysis"]["current_stock"],40)

    def test_stale_collector_never_emits_old_prediction(self):
        with patch.dict(os.environ,{"TORN_FREN_V38_REVISION_CACHE":"1"}):
            with patch.object(webapp,"get_latest_item_snapshot",return_value={"timestamp":1,"quantity":0}):
                with patch.object(webapp,"v38_source_revision",return_value=("COLLECTOR_STALE_OR_NO_HEARTBEAT",None)):
                    with patch.object(webapp,"_V39_HISTORY_CACHE") as history:
                        with patch.object(webapp,"get_item_history_since",return_value=[]) as rows:
                            with patch.object(webapp,"_get_prediction_nonblocking") as pred:
                                with patch.object(webapp,"_get_analysis_nonblocking") as graph:
                                    with patch.object(webapp,"profitability_for_item",return_value=(None,{})):
                                        result=webapp.api_history(country="uni",item="Heather",minutes=60)
        history.get.assert_not_called()
        rows.assert_called_once()
        pred.assert_not_called()
        graph.assert_not_called()
        self.assertIsNone(result["analysis"]["prediction"])
        self.assertTrue(result["analysis"]["prediction_v2_stale"])

    def test_default_v37_route_unchanged_with_opt_in_off(self):
        with patch.dict(os.environ,{},clear=True):
            with patch.object(webapp,"get_latest_item_snapshot",return_value={"quantity":0}):
                with patch.object(webapp,"v38_source_revision") as gate:
                    with patch.object(webapp,"_V39_HISTORY_CACHE") as history:
                        with patch.object(webapp,"get_item_history_since",return_value=[]):
                            with patch.object(webapp,"_get_analysis_nonblocking",return_value=(None,True)):
                                with patch.object(webapp,"profitability_for_item",return_value=(None,{})):
                                    with patch.object(webapp,"_get_prediction_nonblocking",
                                                      return_value=({"status":"warming"},True)):
                                        with patch.object(webapp,"get_recent_active_forecasts",return_value=[]):
                                            result=webapp.api_history(country="uni",item="Heather",minutes=60)
        gate.assert_not_called()
        history.get.assert_not_called()
        self.assertEqual(result["analysis"]["prediction_v2"]["status"],"warming")


if __name__=="__main__":
    unittest.main()
