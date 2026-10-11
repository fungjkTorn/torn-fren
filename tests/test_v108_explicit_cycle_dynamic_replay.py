"""V108 dynamic projection tests: no need to wait a fixed delay."""
import unittest

from research import v108_explicit_cycle_dynamic_replay as m

NOW=1_800_000
ITEM="mex:Jaguar Plushie"


class CycleReplayTests(unittest.TestCase):
    def test_restock_window_lead_time_subtracts_flight_and_commits(self):
        queries=[]
        def forecast(item,history,*,asof,collection_gaps):
            queries.append(asof)
            return {"status":"FORECAST_AVAILABLE",
                    "windows":[{
                        "earliest_expected_departure":NOW+600,
                        "earliest_conservative_departure":NOW+900}]}
        out=m.simulate_cycle_policies(NOW,ITEM,[],[],forecast=forecast)
        self.assertEqual(out["departures"]["cycle_expected"],NOW+600)
        self.assertEqual(out["departures"]["cycle_cautious"],NOW+900)
        self.assertEqual(out["departures"]["depart_now"],NOW)
        self.assertEqual(queries,[NOW,NOW+300,NOW+600])
        self.assertEqual(out["forecast_tick_count"],3)

    def test_empty_cycle_history_abstains_not_claims_stock(self):
        out=m.simulate_cycle_policies(NOW,ITEM,[],[])
        self.assertIsNone(out["departures"]["cycle_expected"])
        self.assertIsNone(out["departures"]["cycle_cautious"])
        self.assertEqual(out["departures"]["depart_now"],NOW)
        self.assertGreaterEqual(
            out["forecast_statuses"]["ABSTAIN_STALE_OR_MISSING_STOCK"],1)

    def test_withdrawn_future_stock_window_is_never_flown(self):
        def forecast(item,history,*,asof,collection_gaps):
            if asof==NOW:
                return {"status":"FORECAST_AVAILABLE","windows":[{
                    "earliest_expected_departure":NOW+1800,
                    "earliest_conservative_departure":None}]}
            return {"status":"ABSTAIN_INSUFFICIENT_COMPLETED_CYCLES",
                    "windows":[]}
        out=m.simulate_cycle_policies(NOW,ITEM,[],[],forecast=forecast)
        self.assertIsNone(out["departures"]["cycle_expected"])
        self.assertIsNone(out["departures"]["cycle_cautious"])

    def test_next_restock_not_reachable_but_second_is(self):
        def forecast(item,history,*,asof,collection_gaps):
            return {"status":"FORECAST_AVAILABLE","windows":[
                {"earliest_expected_departure":None,
                 "earliest_conservative_departure":None},
                {"earliest_expected_departure":NOW+600,
                 "earliest_conservative_departure":NOW+900}]}
        out=m.simulate_cycle_policies(NOW,ITEM,[],[],forecast=forecast)
        self.assertEqual(out["departures"]["cycle_expected"],NOW+600)
        self.assertEqual(out["departures"]["cycle_cautious"],NOW+900)

    def test_prior_8h_horizon_is_strict(self):
        def forecast(item,history,*,asof,collection_gaps):
            return {"status":"FORECAST_AVAILABLE","windows":[{
                "earliest_expected_departure":NOW+8*3600+1200,
                "earliest_conservative_departure":None}]}
        out=m.simulate_cycle_policies(NOW,ITEM,[],[],forecast=forecast)
        self.assertIsNone(out["departures"]["cycle_expected"])

    def test_country_specific_flight_geometry_is_preserved(self):
        self.assertEqual(m.TRAVEL_SECONDS["mex"],1020)
        self.assertEqual(m.TRAVEL_SECONDS["uni"],6360)


if __name__=="__main__":
    unittest.main()
