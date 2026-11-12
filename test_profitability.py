import unittest

from services.profitability import calculate_profitability, MARKET_SALE_FEE_RATE, PI_PILOT_FLIGHT_MINUTES


class ProfitabilityTests(unittest.TestCase):
    def test_basic_market_fee_and_hourly_profit(self):
        result = calculate_profitability(400_000, 500_000, 120)
        self.assertEqual(result["net_sale_value"], 475_000)
        self.assertEqual(result["net_profit_per_item"], 75_000)
        self.assertEqual(result["round_trip_minutes"], 240)
        self.assertEqual(result["profit_per_slot_per_hour"], 18_750)
        self.assertEqual(result["roi_percent"], 18.75)

    def test_negative_profit_is_preserved_for_sorting_visibility(self):
        result = calculate_profitability(100_000, 90_000, 30)
        self.assertLess(result["net_profit_per_item"], 0)
        self.assertLess(result["profit_per_slot_per_hour"], 0)

    def test_missing_inputs_return_none(self):
        self.assertIsNone(calculate_profitability(None, 100, 20))
        self.assertIsNone(calculate_profitability(100, None, 20))
        self.assertIsNone(calculate_profitability(100, 200, None))


if __name__ == "__main__":
    unittest.main()

    def test_item_market_fee_is_five_percent(self):
        self.assertEqual(MARKET_SALE_FEE_RATE, 0.05)

    def test_pi_pilot_flight_times(self):
        self.assertEqual(PI_PILOT_FLIGHT_MINUTES, {
            "mex": 17,
            "cay": 23,
            "can": 27,
            "haw": 89,
            "uni": 106,
            "arg": 111,
            "swi": 116,
            "jap": 149,
            "chi": 160,
            "uae": 180,
            "sou": 197,
        })
