"""Check that waiting for the next actual restock is not a model penalty."""
import unittest
from services.next_opportunity_evaluation import (
    QualifiedStockWindow as Window, evaluate_departure, earliest_viable_leave
)

class TestNaturalRestockDelay(unittest.TestCase):
    def test_long_wait_is_free_when_needed(self):
        w = [Window(36000, 44000)]
        result = evaluate_departure(now_timestamp=0, recommended_leave_timestamp=32390,
                                    travel_seconds=3600, windows=w, max_wait_seconds=43200)
        self.assertTrue(result["arrival_success"])
        self.assertEqual(result["unavoidable_wait_seconds_hindsight"],32390)
        self.assertEqual(result["avoidable_delay_seconds_hindsight"],0)

    def test_twelve_hour_wait_is_wasteful_if_stock_already_reachable(self):
        w=[Window(0,90000)]
        result=evaluate_departure(now_timestamp=0,recommended_leave_timestamp=43200,
                                  travel_seconds=3600,windows=w,max_wait_seconds=43200)
        self.assertTrue(result["arrival_success"])
        self.assertEqual(result["unavoidable_wait_seconds_hindsight"],0)
        self.assertEqual(result["avoidable_delay_seconds_hindsight"],43200)
        self.assertTrue(result["skipped_earlier_feasible_departure"])

    def test_two_windows_selects_first_not_later(self):
        w=[Window(20000,21000),Window(50000,51000)]
        x=earliest_viable_leave(0,3600,w,10,50000)
        self.assertEqual(x,16390)
        result=evaluate_departure(now_timestamp=0,recommended_leave_timestamp=46390,
                                  travel_seconds=3600,windows=w,max_wait_seconds=50000)
        self.assertTrue(result["arrival_success"])
        self.assertEqual(result["avoidable_delay_seconds_hindsight"],30000)

    def test_no_reachable_restocks_means_no_wait_regret(self):
        result=evaluate_departure(now_timestamp=0,recommended_leave_timestamp=43200,
                                  travel_seconds=3600,windows=[Window(200000,201000)],max_wait_seconds=43200)
        self.assertIsNone(result["unavoidable_wait_seconds_hindsight"])
        self.assertIsNone(result["avoidable_delay_seconds_hindsight"])
        self.assertFalse(result["viable_within_wait_budget"])

    def test_miss_is_not_confused_with_late_arrival(self):
        result=evaluate_departure(now_timestamp=0,recommended_leave_timestamp=0,
                                  travel_seconds=3600,windows=[Window(36000,37000)],max_wait_seconds=43200)
        self.assertFalse(result["arrival_success"])
        self.assertIsNone(result["avoidable_delay_seconds_hindsight"])

    def test_bounds(self):
        with self.assertRaises(ValueError): Window(20,20)
        with self.assertRaises(ValueError): earliest_viable_leave(0,-2,[],10)
        with self.assertRaises(ValueError): evaluate_departure(now_timestamp=10,recommended_leave_timestamp=5,
                                                               travel_seconds=5,windows=[])

if __name__=="__main__":unittest.main()
