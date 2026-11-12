"""Arrival evidence: 30 units qualifies, changed poll brackets stay unknown."""
import unittest
from services.simulated_trip_evidence import grade_trip


class SimulatedTripThresholdTests(unittest.TestCase):
    def grade(self, rows, *, receipts=None, gaps=None):
        if receipts is None:
            receipts = [(990, 990, "REPORTED", "yata")]
        return grade_trip(
            arrival=1000,
            rows=rows,
            polls=[980, 1020],
            gaps=[] if gaps is None else gaps,
            cutoff=1180,
            country_receipts=receipts,
        )

    def test_30_units_count_as_success(self):
        result = self.grade([(970, 30)])
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIsNone(result["failure_class"])

    def test_29_units_fail(self):
        result = self.grade([(970, 29)])
        self.assertEqual(result["status"], "FAILURE")
        self.assertEqual(result["failure_class"], "LOW_STOCK_1_TO_30")

    def test_changed_stock_inside_poll_bracket_is_unknown(self):
        result = self.grade([(970, 29), (1000, 30)])
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["reason"], "AVAILABILITY_CHANGED_INSIDE_POLL_BRACKET")

    def test_missing_country_clock_is_unknown(self):
        result = self.grade([(970, 30)], receipts=[])
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["reason"], "COUNTRY_EVIDENCE_UNAVAILABLE_AT_ARRIVAL")


if __name__ == "__main__":
    unittest.main()
