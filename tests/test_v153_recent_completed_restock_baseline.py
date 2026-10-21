"""V153 only fully bounded historical intervals; no lookahead or launch."""
import unittest

from research.v107_explicit_restock_cycle_baseline import StockObservation
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v153_recent_completed_restock_baseline import recent_restock_forecasts

T=1791800000


def phase_history(low_durations=(900,900,900,900,900,300,300,300),
                  high_durations=(300,)*8, *, source_churn=True):
    t=T
    rows=[StockObservation(t,0,"yata")]
    for low,high in zip(low_durations,high_durations):
        t+=low
        rows.append(StockObservation(t,100,"yata"))
        if source_churn and high>=120:
            rows.append(StockObservation(t+40,90,"prometheus"))
            rows.append(StockObservation(t+80,85,"yata"))
        t+=high
        rows.append(StockObservation(t,0,"yata"))
    return provider_continuous_phases(rows,asof=t),t,rows


class RecentObservedRestockTests(unittest.TestCase):
    def test_recent_3_follows_changed_depletion_regime_without_future_data(self):
        hist,issued,_=phase_history()
        self.assertEqual(len(hist["observed_bounded_depleted_windows"]),7)
        self.assertEqual(len(hist["observed_bounded_stocked_windows"]),8)
        result=recent_restock_forecasts("chi:Peony",hist,asof=issued)
        self.assertEqual(result["status"],"ISSUED_PREDECLARED_RECENCY_CHALLENGERS")
        self.assertEqual(result["forecasts"]["recent_3"]["forecast_epoch"],
                         issued+300)
        self.assertEqual(result["forecasts"]["all_bounded"]["forecast_epoch"],
                         issued+900)
        self.assertFalse(result["future_information_used_in_forecast"])
        self.assertIsNone(result["published_departure"])

    def test_low_phase_remaining_duration_conditions_on_observed_age(self):
        hist,issued,_=phase_history()
        future=recent_restock_forecasts("arg:Monkey Plushie",hist,
                                        asof=issued+100)
        self.assertEqual(future["forecasts"]["recent_3"]["forecast_epoch"],
                         issued+300)
        self.assertEqual(future["forecasts"]["recent_3"][
            "elapsed_current_phase_seconds"],100)

    def test_short_bounded_history_still_visible_no_fake_forecast(self):
        hist,issued,_=phase_history(
            low_durations=(600,600),high_durations=(300,300))
        result=recent_restock_forecasts("uni:Nessie Plushie",hist,asof=issued)
        self.assertEqual(result["forecasts"]["recent_3"]["status"],
                         "TOO_FEW_COMPLETED_PERIODS")
        self.assertIsNotNone(result["forecasts"]["all_bounded"]["forecast_epoch"])
        self.assertTrue(result["history_only_completed_boundaries"])

    def test_churn_inside_high_still_produces_real_history(self):
        hist,issued,_=phase_history(source_churn=True)
        result=recent_restock_forecasts("mex:Jaguar Plushie",hist,asof=issued)
        self.assertEqual(result["forecasts"]["recent_5"][
            "observed_high_count"],5)
        self.assertEqual(result["forecasts"]["recent_5"][
            "observed_low_count"],5)

    def test_missing_low_period_or_phase_onset_never_fabricated(self):
        hist,issued,_=phase_history()
        hist["observed_bounded_depleted_windows"]=[]
        result=recent_restock_forecasts("jap:Xanax",hist,asof=issued)
        self.assertEqual(result["status"],"NO_COMPLETE_BOTH_PHASE_TYPES")
        self.assertEqual(result["forecasts"],{})
        hist["phase_onset"]=None
        result=recent_restock_forecasts("jap:Xanax",hist,asof=issued)
        self.assertEqual(result["status"],"UNKNOWN_CURRENT_PHASE")

    def test_future_and_overlapping_intervals_refused(self):
        hist,issued,_=phase_history()
        with self.assertRaises(ValueError):
            recent_restock_forecasts("uni:Heather",hist,asof=issued-1)
        hist["observed_bounded_depleted_windows"]=[
            (T+300,T+600),(T+500,T+1000)]
        with self.assertRaises(ValueError):
            recent_restock_forecasts("uni:Heather",hist,asof=issued)


if __name__=="__main__":
    unittest.main()
