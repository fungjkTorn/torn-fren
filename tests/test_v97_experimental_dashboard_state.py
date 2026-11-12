"""V97 screenshot regression: far-future candidate is WATCH not READY."""
import unittest
from research import v97_experimental_dashboard_state as m

NOW=1791650000


def row(dep,*,issued=NOW-20,stock=NOW-25,valid=NOW+280,actionable=True,
        status="RESEARCH_PROPOSAL_ONLY"):
    return {"item_key":"cay:Banana Orchid", "model_family":"dyn7",
            "model_config":"dyn7","status":status,
            "actionable":actionable,"computed_at":issued,
            "stock_as_of":stock,
            "valid_until":valid,"departure":dep,
            "arrival":dep+1380 if dep is not None else None,
            "prediction_accuracy_verified":False,
            "experimental":True}


class DashboardStateTests(unittest.TestCase):
    def test_six_hour_ready_backend_becomes_watch_not_ready(self):
        result=m.classify_prediction(row(NOW+21600),now=NOW)
        self.assertEqual(result["display_state"],m.STATUS_WATCH)
        self.assertEqual(result["leave_in_seconds"],21600)
        self.assertFalse(result["can_be_presented_as_verified_advice"])
        self.assertIn("replan",result["display_explanation"])

    def test_depart_immediately_and_few_minutes_distinct(self):
        current=m.classify_prediction(row(NOW+12),now=NOW)
        soon=m.classify_prediction(row(NOW+180),now=NOW)
        self.assertEqual(current["display_state"],m.STATUS_READY_NOW)
        self.assertEqual(soon["display_state"],m.STATUS_READY_SOON)
        self.assertTrue(current["unvalidated"])

    def test_no_ready_for_passed_departure(self):
        r=m.classify_prediction(row(NOW-1),now=NOW)
        self.assertEqual(r["display_state"],m.STATUS_PASSED)
        self.assertIsNone(r["departure_time"])

    def test_research_preview_not_falsely_actionable(self):
        r=m.classify_prediction(
            row(NOW+30,status="RESEARCH_PREVIEW_UNVALIDATED"),
            now=NOW)
        self.assertEqual(r["display_state"],m.STATUS_PREVIEW)
        self.assertEqual(r["departure_time"],NOW+30)
        self.assertFalse(r["can_be_presented_as_verified_advice"])

    def test_research_preview_expired_hidden(self):
        r=m.classify_prediction(
            row(NOW+30,valid=NOW-1,status="RESEARCH_PREVIEW_UNVALIDATED"),
            now=NOW)
        self.assertEqual(r["display_state"],m.STATUS_PREVIEW)
        self.assertIsNone(r["departure_time"])

    def test_expired_overrides_far_future_actionable_bool(self):
        r=m.classify_prediction(row(NOW+21000,valid=NOW-1),now=NOW)
        self.assertEqual(r["display_state"],m.STATUS_EXPIRED)

    def test_missing_or_old_stock_provenance_cannot_be_ready(self):
        r=m.classify_prediction(row(NOW+10,stock=NOW-600),now=NOW)
        self.assertEqual(r["display_state"],m.STATUS_FRESHNESS_UNKNOWN)
        self.assertIsNone(r["leave_in_seconds"])

    def test_backend_abstention_never_assigned_departure(self):
        r=m.classify_prediction(
            row(None,actionable=False,status="NO_RECOMMENDATION"),now=NOW)
        self.assertEqual(r["display_state"],m.STATUS_UNAVAILABLE)

    def test_negative_ttl_fails_closed(self):
        r=m.classify_prediction(row(NOW+10,valid=None),now=NOW)
        self.assertEqual(r["display_state"],m.STATUS_EXPIRED)

    def test_adjustable_urgency_does_not_change_forecast(self):
        original=row(NOW+600)
        a=m.classify_prediction(original,now=NOW,soon_seconds=300)
        b=m.classify_prediction(original,now=NOW,soon_seconds=900)
        self.assertEqual(a["display_state"],m.STATUS_WATCH)
        self.assertEqual(b["display_state"],m.STATUS_READY_SOON)
        self.assertEqual(b["departure_time"],original["departure"])
        self.assertEqual(original["actionable"],True)


if __name__=="__main__":
    unittest.main()
