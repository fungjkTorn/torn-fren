"""Three view-compatible V166 travel decision contract: no false certainty."""
from __future__ import annotations

import unittest

from services.travel_decision_contract_v166 import (
    build_item_travel_decision, STATUS_ABSTAIN, STATUS_ACTIVE,
    STATUS_NO_WINDOW, STATUS_STALE, STATUS_WAIT,
)

NOW=1791911000


def make_event(center,length=600,early=None,late=None):
    return {
        "predicted_restock_epoch":center,
        "restock_early_epoch":center-100 if early is None else early,
        "restock_late_epoch":center+200 if late is None else late,
        "predicted_stock_below_30_epoch":center+length,
    }


def make_forecast(events,*,flight=1200,status="EVENT_TIMELINE_FORECAST_AVAILABLE"):
    return {
        "item_key":"mex:Jaguar Plushie",
        "asof_epoch":NOW-20,
        "flight_seconds":flight,
        "status":status,
        "restock_events":events,
    }


class TravelDecisionContractTests(unittest.TestCase):
    def decision(self,events,**kwargs):
        return build_item_travel_decision(
            make_forecast(events),now=NOW,poll_age_seconds=12,**kwargs)

    def test_remembers_unreachable_first_event_then_finds_earliest_reachable(self):
        a=make_event(NOW+200,length=200)
        b=make_event(NOW+2600,length=900)
        report=self.decision([a,b])
        self.assertEqual(report["status"],STATUS_WAIT)
        self.assertEqual(report["selected_restock_event_index"],2)
        self.assertEqual(report["forecast_events"][0]["flight_reachable"],False)
        self.assertEqual(report["departure_countdown_seconds"],1400)
        self.assertEqual(report["estimated_departure_epoch"],NOW+1400)
        self.assertEqual(report["estimated_arrival_epoch"],NOW+2600)
        self.assertEqual(report["departure_recommendation_is_estimate"],True)
        self.assertFalse(report["prediction_calibrated"])
        self.assertIsNone(report["verified_arrival_stock_success_probability"])

    def test_active_window_from_current_estimated_stock(self):
        e=make_event(NOW-200,length=1600,early=NOW-300,late=NOW-100)
        report=self.decision([e])
        self.assertEqual(report["status"],STATUS_ACTIVE)
        self.assertEqual(report["estimated_departure_epoch"],NOW)
        self.assertEqual(report["estimated_arrival_epoch"],NOW+1200)
        self.assertEqual(report["departure_countdown_seconds"],0)

    def test_travel_modifier_changes_earliest_viable_departure(self):
        e=make_event(NOW+3600,length=1200)
        base=self.decision([e])
        quicker=self.decision([e],player_flight_seconds=600)
        self.assertEqual(base["estimated_departure_epoch"],NOW+2400)
        self.assertEqual(quicker["estimated_departure_epoch"],NOW+3000)
        self.assertEqual(base["estimated_arrival_epoch"],quicker["estimated_arrival_epoch"])
        self.assertTrue(base["forecast_events"][0]["flight_reachable"])

    def test_unreachable_due_to_long_flight_horizon(self):
        report=self.decision([make_event(NOW+200,length=100)])
        self.assertEqual(report["status"],STATUS_NO_WINDOW)
        self.assertIsNone(report["estimated_departure_epoch"])
        self.assertEqual(report["forecast_events"][0]["reason"],
                         "NOT_REACHABLE_WITH_PLAYER_FLIGHT")

    def test_stale_data_and_forecast_suppress_actionable_clock(self):
        report=build_item_travel_decision(
            make_forecast([make_event(NOW+1500)]),
            now=NOW,poll_age_seconds=400)
        self.assertEqual(report["status"],STATUS_STALE)
        self.assertIsNone(report["estimated_departure_epoch"])
        self.assertEqual(len(report["forecast_events"]),1)
        other=build_item_travel_decision(
            make_forecast([make_event(NOW+1500)]),
            now=NOW+700,poll_age_seconds=10)
        self.assertEqual(other["status"],STATUS_STALE)
        self.assertEqual(other["reason"],"STALE_MODEL_FORECAST")

    def test_insufficient_model_and_unsupported_target_abstain(self):
        e=make_event(NOW+2500)
        bad=build_item_travel_decision(
            make_forecast([e],status="CURRENT_PHASE_UNKNOWN"),
            now=NOW,poll_age_seconds=10)
        self.assertEqual(bad["status"],STATUS_ABSTAIN)
        self.assertIsNone(bad["estimated_departure_epoch"])
        unsupported=self.decision([e],target_qty=75)
        self.assertEqual(unsupported["status"],STATUS_ABSTAIN)
        self.assertEqual(unsupported["reason"],"REQUESTED_THRESHOLD_NOT_SUPPORTED_BY_MODEL")

    def test_arrival_is_real_landing_not_grace_adjusted(self):
        center = NOW + 2600
        decision = self.decision([make_event(center, length=30)])
        self.assertEqual(decision["estimated_departure_epoch"], center - 1200)
        self.assertEqual(decision["estimated_arrival_epoch"], center)
        self.assertEqual(decision["estimated_arrival_plus_grace_epoch"], center + 10)
        self.assertEqual(decision["estimated_departure_deadline_epoch"],
                         center + 30 - 1200 - 10 - 1)
        self.assertIsNone(self.decision([make_event(center, length=10)])["estimated_departure_epoch"])

    def test_unavailable_purchase_model_keeps_all_physical_restocks(self):
        true_events = [make_event(NOW+200), make_event(NOW+2600)]
        forecast = make_forecast([], status="INSUFFICIENT_SEPARATE_PURCHASE_WINDOW_HISTORY")
        forecast["true_restock_events"] = true_events
        report = build_item_travel_decision(forecast, now=NOW, poll_age_seconds=12)
        self.assertEqual(report["status"], STATUS_ABSTAIN)
        self.assertEqual(len(report["forecast_events"]), 2)
        self.assertTrue(report["all_restock_events_preserved"])
        self.assertTrue(all(e["reason"] == "PURCHASE_WINDOW_NOT_ESTABLISHED"
                            for e in report["forecast_events"]))
        self.assertIsNone(report["estimated_departure_epoch"])

    def test_physical_event_ordinals_are_not_reordered_by_purchase_filter(self):
        physical = [make_event(NOW+200), make_event(NOW+2600)]
        purchase = [dict(physical[0]), dict(physical[1])]
        forecast = make_forecast(purchase)
        forecast["true_restock_events"] = physical
        report = build_item_travel_decision(forecast, now=NOW, poll_age_seconds=12)
        self.assertEqual(report["selected_restock_event_index"], 2)
        self.assertEqual([e["index"] for e in report["forecast_events"]], [1,2])
        forecast["restock_events"] = purchase[1:]
        with self.assertRaises(ValueError):
            build_item_travel_decision(forecast, now=NOW, poll_age_seconds=12)

    def test_current_stock_can_beat_future_predicted_restock(self):
        forecast = make_forecast([make_event(NOW+2600)])
        forecast["current_stock_window"] = dict(
            predicted_restock_epoch=NOW-20,
            predicted_stock_below_30_epoch=NOW+1400,
            early_stock_end_epoch=NOW+1300)
        report = build_item_travel_decision(forecast, now=NOW, poll_age_seconds=12)
        self.assertEqual(report["selected_restock_event_index"], 0)
        self.assertEqual(report["estimated_departure_epoch"], NOW)
        self.assertEqual(report["estimated_arrival_epoch"], NOW+1200)
        self.assertEqual(report["forecast_events"][0]["index"], 1)

    def test_conservative_window_and_eight_hour_horizon(self):
        e = make_event(NOW+2600, length=900)
        e["early_stock_end_epoch"] = NOW+2750
        bounded = self.decision([e], arrival_policy="bounded")
        self.assertEqual(bounded["status"], STATUS_NO_WINDOW)
        e["early_stock_end_epoch"] = NOW+3100
        bounded = self.decision([e], arrival_policy="bounded")
        self.assertEqual(bounded["estimated_arrival_epoch"], NOW+2800)
        late = self.decision([make_event(NOW+30000, length=900)])
        self.assertEqual(late["status"], STATUS_NO_WINDOW)
        self.assertEqual(late["forecast_events"][0]["reason"],
                         "AFTER_EIGHT_HOUR_DEPARTURE_HORIZON")

    def test_issue_at_next_five_minute_tick_expires_but_events_remain(self):
        forecast = make_forecast([make_event(NOW+2600)])
        report = build_item_travel_decision(
            forecast, now=forecast["asof_epoch"]+300, poll_age_seconds=10)
        self.assertEqual(report["status"], STATUS_STALE)
        self.assertEqual(len(report["forecast_events"]), 1)
        self.assertIsNone(report["estimated_departure_epoch"])

    def test_rejects_inconsistent_or_unbounded_historical_forecasts(self):
        with self.assertRaises(ValueError):
            self.decision([make_event(NOW+4000),make_event(NOW+3000)])
        with self.assertRaises(ValueError):
            self.decision([make_event(NOW+1500,length=-1)])
        with self.assertRaises(ValueError):
            self.decision([make_event(NOW+1000)]*65)
        with self.assertRaises(ValueError):
            self.decision([make_event(NOW+1000)],player_flight_seconds=-2)

if __name__=="__main__":
    unittest.main()
