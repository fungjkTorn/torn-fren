import unittest

from deploy.scripts.v163_readonly_event_first_preview import predict_events
from services.travel_decision_contract_v166 import build_item_travel_decision
from research.v167_event_candidate_scoring import CHAMPION_KIND


class Obs:
    def __init__(self,epoch,quantity=0,source="p"):
        self.epoch=epoch
        self.quantity=quantity
        self.source=source


class V167HorizonFreeContractTests(unittest.TestCase):
    def test_champion_roster_is_exact_24(self):
        self.assertEqual(24,len(CHAMPION_KIND))
        self.assertIn("jap:Xanax",CHAMPION_KIND)

    def test_v163_can_project_days_ahead_without_time_horizon(self):
        asof=1_000_000
        phases={
            "phase":"LOW",
            "phase_onset":asof-3600,
            "last_observation":Obs(asof,0),
            "stocked_durations":[7200,7500,7800,8100],
            "depleted_durations":[2*86400,3*86400,4*86400,3*86400],
        }
        result=predict_events(
            "uni:Nessie Plushie",phases,asof=asof,horizon=None,max_events=4)
        self.assertEqual("EVENT_TIMELINE_FORECAST_AVAILABLE",result["status"])
        self.assertEqual(4,len(result["restock_events"]))
        self.assertGreater(
            result["restock_events"][-1]["predicted_restock_epoch"]-asof,
            8*3600)
        self.assertIsNone(result["event_horizon_seconds"])

    def test_travel_contract_accepts_departure_beyond_eight_hours(self):
        now=1_000_000
        restock=now+2*86400
        forecast={
            "item_key":"uni:Nessie Plushie",
            "asof_epoch":now,
            "flight_seconds":5400,
            "status":"EVENT_TIMELINE_FORECAST_AVAILABLE",
            "physical_depletion_quantity":0,
            "restock_timer_anchor":"TEST",
            "restock_events":[{
                "predicted_restock_epoch":restock,
                "restock_early_epoch":restock-600,
                "restock_late_epoch":restock+600,
                "predicted_stock_below_30_epoch":restock+7200,
                "early_stock_end_epoch":restock+6600,
                "predicted_true_depletion_epoch":restock+9000,
            }],
            "true_restock_events":[{
                "predicted_restock_epoch":restock,
                "restock_early_epoch":restock-600,
                "restock_late_epoch":restock+600,
                "predicted_true_depletion_epoch":restock+9000,
            }],
            "current_stock_window":None,
        }
        decision=build_item_travel_decision(
            forecast,now=now,poll_age_seconds=0,arrival_policy="expected")
        self.assertEqual("WAIT_FOR_ESTIMATED_DEPARTURE",decision["status"])
        self.assertGreater(decision["estimated_departure_epoch"]-now,8*3600)
        self.assertEqual(1,decision["selected_restock_event_index"])


if __name__=="__main__":
    unittest.main()
