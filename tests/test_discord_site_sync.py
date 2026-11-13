import unittest
from unittest.mock import patch
from bot import site_feed


class SiteFeedContractTests(unittest.TestCase):
    NOW = 2_000_000_000

    def row(self, **overrides):
        data = {
            "item_key": "sou:Lion Plushie",
            "valid_until_epoch": self.NOW + 120,
            "decision": {
                "status": "WAIT_FOR_ESTIMATED_DEPARTURE",
                "estimated_departure_epoch": self.NOW + 30,
                "estimated_departure_deadline_epoch": self.NOW + 100,
                "estimated_arrival_epoch": self.NOW + 330,
                "player_flight_seconds": 300,
                "selected_restock_event_index": 1,
            },
            "live": {"known": 2, "successes": 1, "pending": 1,
                     "unknown": 0, "success_fraction": 0.5,
                     "rate_status": "KNOWN_SIMULATED_TRIPS",
                     "target_identity_audit": {"duplicate_target_groups": 0}},
        }
        data.update(overrides)
        return data

    def test_approved_forecast_is_usable(self):
        row = self.row()
        self.assertEqual(site_feed.row_status(row, now=self.NOW),
                         "WAIT_FOR_ESTIMATED_DEPARTURE")
        self.assertIn("more than 30", site_feed.format_prediction(
            "sou", "Lion Plushie", row, now=self.NOW))
        self.assertEqual(site_feed.known_rate(row), "50% (1/2 known simulated trips)")

    def test_unapproved_items_show_no_departure(self):
        self.assertEqual(site_feed.row_status(None), "UNDER_REVIEW")
        self.assertNotIn("Depart:", site_feed.format_prediction("jap", "Xanax", None))

    def test_stale_and_invalid_departure_suppressed(self):
        row = self.row(valid_until_epoch=self.NOW - 1)
        self.assertEqual(site_feed.row_status(row, now=self.NOW), "STALE_DATA")
        self.assertNotIn("Depart:", site_feed.format_prediction("sou", "Lion Plushie", row, now=self.NOW))
        row = self.row()
        row["decision"]["estimated_arrival_epoch"] += 10
        self.assertEqual(site_feed.row_status(row, now=self.NOW), "UNAVAILABLE")

    def test_old_or_duplicate_evidence_not_displayed_as_success(self):
        row = self.row()
        row["live"]["target_identity_audit"]["duplicate_target_groups"] = 1
        self.assertIsNone(site_feed.known_rate(row))
        row["live"]["target_identity_audit"]["duplicate_target_groups"] = 0
        row["live"]["success_fraction"] = None
        self.assertIsNone(site_feed.known_rate(row))

    def test_history_is_descriptive_not_predictive(self):
        summary = {"status": "AVAILABLE", "last_restock_timestamp": self.NOW - 300,
                   "median_stocked_seconds": 600, "median_unstocked_seconds": 350,
                   "completed_stock_windows": 4, "uncertain_boundaries": 2,
                   "sample_end_epoch": self.NOW - 60}
        text = site_feed.format_history("sou", "Lion Plushie", summary, self.row())
        self.assertIn("descriptive, not forecast accuracy", text)
        self.assertNotIn("Historical trip success", text)

    def test_precomputed_url_encodes_item(self):
        self.assertEqual(
            site_feed.site_url("https://example.test", country="sou", item="Lion Plushie"),
            "https://example.test/?country=sou&item=Lion+Plushie",
        )
        with self.assertRaises(site_feed.FeedUnavailable):
            site_feed.fetch_board("http://insecure.example")

    def test_item_identity_casefold(self):
        board = {"rows": [self.row()]}
        self.assertIsNotNone(site_feed.item_row(board, "SOU", "lion plushie"))


if __name__ == "__main__":
    unittest.main()
