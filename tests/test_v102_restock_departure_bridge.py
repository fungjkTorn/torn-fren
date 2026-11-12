"""V102: forecasted stock interval must drive departure, not wait heuristics."""
import unittest
from research.v102_restock_departure_bridge import (
    ArrivalScore,StockedWindowForecast,derive_departure_windows,
    derive_from_arrival_scores
)

NOW=2_000_000
FLIGHT=1020


def window(**kwargs):
    base={
        "item_key":"mex:Jaguar Plushie","model_id":"fake-model",
        "issued_at":NOW-15,"stock_as_of":NOW-20,
        "expected_start":NOW+1800,"expected_end":NOW+3300,
        "late_start":NOW+2100,"early_end":NOW+3000,
    }
    base.update(kwargs)
    return StockedWindowForecast(**base)


class RestockDepartureTests(unittest.TestCase):
    def test_earliest_departure_from_stocked_window_and_flight(self):
        p=derive_departure_windows(window(),now=NOW)
        self.assertEqual(p["earliest_expected_departure"],NOW+780)
        self.assertEqual(p["expected_arrival"],NOW+1800)
        self.assertEqual(p["earliest_conservative_departure"],NOW+1080)
        self.assertEqual(p["conservative_arrival"],NOW+2100)
        self.assertFalse(p["guaranteed"])

    def test_leave_immediately_if_predicted_window_covers_arrival(self):
        p=derive_departure_windows(window(),now=NOW+1500)
        self.assertEqual(p["earliest_expected_departure"],NOW+1500)
        self.assertEqual(p["earliest_conservative_departure"],NOW+1500)

    def test_expected_stock_depleted_before_landing_abstain(self):
        p=derive_departure_windows(window(expected_start=NOW-1000,
                                           expected_end=NOW+400,
                                           late_start=NOW-800,
                                           early_end=NOW+100),now=NOW)
        self.assertIsNone(p["earliest_expected_departure"])
        self.assertIsNone(p["earliest_conservative_departure"])

    def test_uncertainty_can_eliminate_conservative_window(self):
        p=derive_departure_windows(window(
            late_start=NOW+3200,early_end=NOW+3000),now=NOW)
        self.assertEqual(p["earliest_expected_departure"],NOW+780)
        self.assertIsNone(p["earliest_conservative_departure"])

    def test_no_arbitrary_delay_if_arrival_stocked_now(self):
        p=derive_departure_windows(window(
            expected_start=NOW-120,expected_end=NOW+2400,
            late_start=NOW-60,early_end=NOW+1800),now=NOW)
        self.assertEqual(p["earliest_expected_departure"],NOW)
        self.assertEqual(p["earliest_conservative_departure"],NOW)

    def test_stock_window_ends_exclusively_no_arrival_at_depletion(self):
        with self.assertRaises(ValueError):
            derive_departure_windows(window(
                expected_start=NOW+FLIGHT,
                expected_end=NOW+FLIGHT,
                late_start=NOW+FLIGHT,
                early_end=NOW+FLIGHT),now=NOW)


class AvailabilityCurveTests(unittest.TestCase):
    def test_earliest_above_floor_differs_from_best_scored_later(self):
        arrivals=[NOW+FLIGHT+300*i for i in range(5)]
        raw=[.55,.71,.84,.92,.88]
        pts=[ArrivalScore(t,p,estimated) for t,p,estimated in zip(
            arrivals,raw,[100,90,85,83,70])]
        out=derive_from_arrival_scores(
            "mex:Jaguar Plushie",pts,now=NOW,
            issued_at=NOW-10,stock_as_of=NOW-20,
            minimum_raw_score=.70)
        self.assertEqual(out["earliest"]["departure_epoch"],NOW+300)
        self.assertEqual(out["best_score"]["departure_epoch"],NOW+900)
        self.assertIs(out["raw_score_calibrated"],False)

    def test_no_feasible_model_score_abstains(self):
        pts=[ArrivalScore(NOW+FLIGHT,.25)]
        out=derive_from_arrival_scores(
            "mex:Jaguar Plushie",pts,now=NOW,
            issued_at=NOW-10,stock_as_of=NOW-20,
            minimum_raw_score=.8)
        self.assertIsNone(out["earliest"])
        self.assertEqual(out["reason"],"NO_ELIGIBLE_SCORE_WINDOW")

    def test_quantity_floor_blocks_false_score_win(self):
        pts=[ArrivalScore(NOW+FLIGHT,.9,25),
             ArrivalScore(NOW+FLIGHT+300,.75,100)]
        out=derive_from_arrival_scores(
            "mex:Jaguar Plushie",pts,now=NOW,
            issued_at=NOW-10,stock_as_of=NOW-20,
            minimum_raw_score=.7)
        self.assertEqual(out["earliest"]["departure_epoch"],NOW+300)

    def test_require_two_contiguous_points_when_policy_requires_it(self):
        pts=[
            ArrivalScore(NOW+FLIGHT,.9),
            ArrivalScore(NOW+FLIGHT+300,.2),
            ArrivalScore(NOW+FLIGHT+600,.8),
            ArrivalScore(NOW+FLIGHT+900,.8),
        ]
        out=derive_from_arrival_scores(
            "mex:Jaguar Plushie",pts,now=NOW,
            issued_at=NOW-10,stock_as_of=NOW-20,
            minimum_raw_score=.7,min_consecutive_points=2)
        self.assertEqual(out["earliest"]["departure_epoch"],NOW+600)
        self.assertEqual(out["qualifying_grid_points"],2)

    def test_unknown_probability_cannot_be_silently_assumed(self):
        with self.assertRaises(TypeError):
            derive_from_arrival_scores(
                "mex:Jaguar Plushie",[],now=NOW,
                issued_at=NOW-10,stock_as_of=NOW-20)

    def test_rejects_invalid_quantity_and_duplicate_arrival_time(self):
        p=ArrivalScore(NOW+FLIGHT,.8,40)
        with self.assertRaises(ValueError):
            derive_from_arrival_scores(
                "mex:Jaguar Plushie",[p,p],now=NOW,
                issued_at=NOW-10,stock_as_of=NOW-20,
                minimum_raw_score=.7)
        with self.assertRaises(ValueError):
            derive_from_arrival_scores(
                "mex:Jaguar Plushie",[ArrivalScore(NOW+FLIGHT,.8,-1)],
                now=NOW,issued_at=NOW-10,stock_as_of=NOW-20,
                minimum_raw_score=.7)


if __name__=="__main__":
    unittest.main()
