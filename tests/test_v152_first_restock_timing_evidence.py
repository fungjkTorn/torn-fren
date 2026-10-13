"""V152 first truly bounded future restock versus as-issued median onset."""
import unittest
from research.v107_explicit_restock_cycle_baseline import StockObservation as O
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v152_first_restock_timing_evidence import evaluate_next_completed_restock

T=1791800000


class FirstCompletedNextRestockAuditTests(unittest.TestCase):
    def test_completed_start_end_survives_same_threshold_source_changes(self):
        observations=[
            O(T,0,"yata"),
            O(T+500,100,"yata"),
            O(T+700,90,"prometheus"),
            O(T+900,75,"yata"),
            O(T+1000,0,"yata"),
        ]
        phases=provider_continuous_phases(observations,asof=T+1200)
        report=evaluate_next_completed_restock(
            observations,phases,issued=T+100,
            predicted_onset_epoch=T+540,asof=T+1200)
        self.assertEqual(report["status"],
                         "MATCHED_NEXT_BOUNDED_RESTOCK_TIMING_PROXY")
        self.assertEqual(report["absolute_forecast_error_seconds"],40)
        self.assertTrue(report["within_1_min"])
        self.assertTrue(report["within_5_min"])
        self.assertFalse(report["source_freshness_certified"])

    def test_gap_before_future_restock_makes_first_event_uncertain(self):
        obs=[O(T,0,"yata"),O(T+200,0,"yata"),O(T+400,0,"yata"),
             O(T+500,100,"yata"),O(T+1000,0,"yata")]
        gap=[(T+220,T+340)]
        phases=provider_continuous_phases(obs,asof=T+1500,gaps=gap)
        r=evaluate_next_completed_restock(
            obs,phases,issued=T+100,
            predicted_onset_epoch=T+550,asof=T+1500,gaps=gap)
        self.assertEqual(r["status"],"COLLECTOR_GAP_BEFORE_NEXT_RESTOCK")
        self.assertIsNone(r["absolute_forecast_error_seconds"])

    def test_cross_source_phase_transition_before_first_verified_disqualifies(self):
        obs=[
            O(T,0,"yata"),O(T+100,100,"prometheus"), # provider disagreement
            O(T+200,0,"prometheus"),
            O(T+500,100,"prometheus"),O(T+1000,0,"prometheus")
        ]
        phases=provider_continuous_phases(obs,asof=T+1500)
        r=evaluate_next_completed_restock(
            obs,phases,issued=T+50,
            predicted_onset_epoch=T+500,asof=T+1500)
        self.assertEqual(
            r["status"],"AMBIGUOUS_CROSS_PROVIDER_EVENT_BEFORE_NEXT_RESTOCK")
        self.assertIsNone(r["forecast_error_seconds"])

    def test_only_observed_start_without_depletion_end_not_scored(self):
        obs=[O(T,0,"yata"),O(T+500,100,"yata")]
        phases=provider_continuous_phases(obs,asof=T+700)
        r=evaluate_next_completed_restock(
            obs,phases,issued=T+100,predicted_onset_epoch=T+500,
            asof=T+700)
        self.assertEqual(r["status"],"NO_VERIFIED_COMPLETE_NEXT_RESTOCK")
        self.assertIsNone(r["within_5_min"])

    def test_complete_stock_but_model_abstention_not_counted_as_success(self):
        obs=[O(T,0,"yata"),O(T+500,100,"yata"),O(T+1000,0,"yata")]
        phases=provider_continuous_phases(obs,asof=T+1500)
        r=evaluate_next_completed_restock(
            obs,phases,issued=T+100,predicted_onset_epoch=None,
            asof=T+1500)
        self.assertEqual(r["status"],"NEXT_RESTOCK_OBSERVED_BUT_MODEL_ABSTAINED")
        self.assertIsNone(r["within_1_min"])

    def test_future_predictions_and_future_outcomes_forbidden(self):
        obs=[O(T,0,"yata"),O(T+500,100,"yata"),O(T+1000,0,"yata")]
        phases=provider_continuous_phases(obs,asof=T+1500)
        with self.assertRaises(ValueError):
            evaluate_next_completed_restock(obs,phases,issued=T+100,
                predicted_onset_epoch=T+50,asof=T+1500)
        with self.assertRaises(ValueError):
            evaluate_next_completed_restock(obs,phases,issued=T+100,
                predicted_onset_epoch=T+500,asof=T+800)


if __name__=="__main__":
    unittest.main()
