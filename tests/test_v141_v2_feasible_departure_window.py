"""V141: V2 window collapse and stocked-threshold display regression."""
import unittest
from research import v141_v2_feasible_departure_window as m

NOW = 1791800000
def forecast(**changes):
    p = {
        "estimate_timestamp": NOW+7200,
        "window_end_timestamp": NOW+7800,
        "recommended_arrival_timestamp": NOW+8100,
        "target_depletion_timestamp": NOW+10000,
        "expected_stock_lifetime_seconds": 3600,
        "travel_seconds": 1620,
    }
    p.update(changes)
    return p

class V2FeasibleWindowTests(unittest.TestCase):
    def test_positive_window_departure_and_arrival(self):
        r = m.assess(forecast(),now=NOW)
        self.assertEqual(r["window_class"],"TOO_EARLY")
        self.assertEqual(r["earliest_arrival_epoch"],NOW+8100)
        self.assertEqual(r["latest_arrival_epoch"],NOW+9700)
        self.assertEqual(r["earliest_departure_epoch"],NOW+6480)
        self.assertEqual(r["latest_departure_epoch"],NOW+8080)
        self.assertFalse(r["arrival_stock_at_least_30_verified"])
    def test_window_enters_provisional_status_not_verified_go(self):
        r = m.assess(forecast(),now=NOW+6480)
        self.assertEqual(r["window_class"],"PROVISIONAL_DEPARTURE_WINDOW")
        self.assertEqual(r["depart_in_seconds"],0)
        self.assertFalse(r["supports_certified_go"])
    def test_window_passed(self):
        r = m.assess(forecast(),now=NOW+8081)
        self.assertEqual(r["window_class"],"DEPARTURE_WINDOW_EXPIRED")
        self.assertIsNone(r["latest_departure_epoch"])
    def test_depletion_earlier_than_conservative_arrival_is_no_window(self):
        r = m.assess(forecast(target_depletion_timestamp=NOW+8100),now=NOW)
        self.assertEqual(r["window_class"],"NO_FEASIBLE_STOCKED_INTERVAL")
        self.assertIsNone(r["earliest_departure_epoch"])
    def test_equal_edges_are_not_fake_zero_width_opportunity(self):
        # Estimated depletion minus 300-second buffer equals earliest arrival.
        r = m.assess(forecast(target_depletion_timestamp=NOW+8400),now=NOW)
        self.assertEqual(r["window_class"],"NO_FEASIBLE_STOCKED_INTERVAL")
    def test_no_actual_lifetime_bound_is_not_silently_inferred(self):
        r = m.assess(forecast(target_depletion_timestamp=None),now=NOW)
        self.assertEqual(r["window_class"],"NO_STOCK_LIFETIME_BOUND")
    def test_unknown_flight_not_displayed(self):
        self.assertEqual(m.assess(forecast(travel_seconds=None),now=NOW)
                         ["window_class"],"INSUFFICIENT_V2_FORECAST")
    def test_current_stock_does_not_imply_30_at_arrival(self):
        self.assertEqual(m.current_stock_threshold_note(observed_quantity=29),"BELOW_30_NOW")
        self.assertEqual(m.current_stock_threshold_note(observed_quantity=800),
                         "ABOVE_30_NOW_BUT_LANDING_UNVERIFIED")
        self.assertEqual(m.current_stock_threshold_note(observed_quantity=800,
                         arrival_stock_lower_bound=12),"PREDICTED_BELOW_30_AT_ARRIVAL")
        self.assertEqual(m.current_stock_threshold_note(observed_quantity=800,
                         arrival_stock_lower_bound=35),
                         "LOWER_BOUND_AT_ARRIVAL_30_OR_MORE_RESEARCH_ONLY")
    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            m.assess(None,now=NOW)
        self.assertEqual(m.assess(forecast(travel_seconds=-10),now=NOW)
                         ["window_class"],"INSUFFICIENT_V2_FORECAST")

if __name__=="__main__":
    unittest.main()
