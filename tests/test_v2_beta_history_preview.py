"""Opt-in bridge in existing /api/history: no extra model work or live source."""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from web import app as web
from services import prediction_v2_live as v2
from research.plushie_champions.common import TRAVEL_SECONDS

N = 1791800000

def cycle(number,restock,target,depletion,lifetime):
    return {
        "prediction_number":number,"estimate_timestamp":N+restock,
        "window_start_timestamp":N+restock-150,
        "window_end_timestamp":N+restock+150,
        "recommended_arrival_timestamp":N+target,
        "target_depletion_timestamp":N+depletion,
        "expected_stock_lifetime_seconds":lifetime,
        "travel_seconds":TRAVEL_SECONDS["can"],
        "model_name":"Prediction V2","travel_reliability":"marginal",
    }

P1=cycle(1,600,750,900,300)
P2=cycle(2,3000,3300,4200,1200)

def api(*,enabled=False,at=N,stale=False,result=None):
    forecast=result if result is not None else {
        "forecast_model_computed_at": N-10,
        "predictions":[P1,P2],"display_prediction":P2,
    }
    with ExitStack() as stack:
        stack.enter_context(patch.dict("os.environ",{
            "TORN_FREN_V38_REVISION_CACHE":"0",
            "TORN_FREN_V2_BETA_TIMELINE":"1" if enabled else "0",
        }))
        for name,value in {
            "get_item_history_since":[{"timestamp":N-20,"quantity":200}],
            "get_latest_item_snapshot":{"cost":10},
            "_get_analysis_nonblocking":({
                "prediction":None,"events":[],
                "collector_last_success_timestamp":N-20
            },False),
            "profitability_for_item":({"net_profit":20},{}),
            "get_recent_active_forecasts":[],
            "_get_prediction_nonblocking":(forecast,stale),
        }.items():
            stack.enter_context(patch.object(web,name,return_value=value))
        stack.enter_context(patch.object(web.time,"time",return_value=at))
        return web.api_history("can","Crocus",1440)

class BetaHistoryEndpointTests(unittest.TestCase):
    def test_selected_shared_departure_is_additive_and_uses_original_issue(self):
        record={'status':'RESEARCH_PREVIEW','asof_epoch':N-10,
            'row':{'item_key':'can:Crocus','departure_epoch':N+1200}}
        with patch.dict('os.environ',{'TORN_FREN_TRAVEL_DECISIONS_BETA':'1'}),patch(
                'web.travel_decisions_router.shared_item',return_value=record) as reader:
            response=api()
        self.assertEqual(response['analysis']['shared_departure_preview'],record)
        self.assertEqual(reader.call_args.kwargs['now'],N)
        self.assertEqual(response['analysis']['prediction']['prediction_number'],2)
        self.assertEqual(response['rows'][0]['quantity'],200)

    def test_disabled_by_default_does_not_change_existing_history_response(self):
        response=api()
        self.assertNotIn("beta_item_timeline",response["analysis"])
        self.assertEqual(response["rows"][0]["quantity"],200)

    def test_enabled_delivers_first_reachable_p2_from_existing_v2(self):
        response=api(enabled=True)
        analysis=response["analysis"]
        self.assertEqual(analysis["prediction"]["prediction_number"],2)
        beta=analysis["beta_item_timeline"]
        self.assertEqual(beta["status"],"V2_FIRST_REACHABLE_PROVISIONAL")
        self.assertEqual(beta["first_reachable"]["prediction_number"],2)
        self.assertEqual(beta["first_reachable"]["earliest_departure_epoch"],N+1680)
        self.assertEqual(beta["next_predicted_restock"]["cycle"],1)
        self.assertEqual(beta["forecast_issued_epoch"],N-10)
        self.assertEqual(analysis["prediction_v2_checked_at"],N)
        self.assertFalse(beta["stock_at_arrival_at_least_30_verified"])
        self.assertIsNone(beta["first_reachable"]["estimated_stock_at_arrival_30_or_more"])

    def test_future_http_checks_do_not_extend_computed_model_ttl(self):
        expired=api(enabled=True,at=N+300)["analysis"]["beta_item_timeline"]
        self.assertEqual(expired["status"],"MODEL_ISSUE_EXPIRED")
        self.assertIsNone(expired["first_reachable"])

    def test_warming_keeps_graph_but_has_no_beta_recommendation(self):
        response=api(enabled=True,stale=True)
        beta=response["analysis"]["beta_item_timeline"]
        self.assertEqual(beta["status"],"V2_WARMING_OR_STALE")
        self.assertIsNone(beta["first_reachable"])
        self.assertEqual(len(response["rows"]),1)

    def test_missing_issuance_never_mints_time_from_http_check(self):
        result={"predictions":[P1,P2],"display_prediction":P2}
        beta=api(enabled=True,result=result)["analysis"]["beta_item_timeline"]
        self.assertEqual(beta["status"],"ISSUANCE_OR_SOURCE_UNKNOWN")

    def test_malformed_history_model_does_not_break_stock_graph(self):
        response=api(enabled=True,result={
            "forecast_model_computed_at":N-10,
            "predictions":[{"bad":"data"}]})
        beta=response["analysis"]["beta_item_timeline"]
        self.assertEqual(beta["status"],"INVALID_V2_CYCLE_IDENTITIES")
        self.assertEqual(response["rows"][0]["quantity"],200)

    def test_model_compute_timestamp_exists_even_when_audit_disabled(self):
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                v2,"_build_live_prediction_v2_impl",
                return_value={"status":"no_forecast","predictions":[]}))
            stack.enter_context(patch.object(v2.time,"time",return_value=N))
            result=v2.build_live_prediction_v2("can","Crocus",record_audit=False)
        self.assertEqual(result["forecast_model_computed_at"],N)
        self.assertEqual(result["predictions"],[])

if __name__=="__main__":
    unittest.main()
