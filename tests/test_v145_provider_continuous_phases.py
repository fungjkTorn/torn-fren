"""V145 validates observed start/end phases despite benign provider churn."""
import unittest

from research.v107_explicit_restock_cycle_baseline import StockObservation as O
from research.v128_full24_earliest_shadow import (
    fast_phases, empirical_arrival_scores,
)
from research.v145_provider_continuous_phases import (
    provider_continuous_phases,compare_phase_eligibility,
    observed_cycle_evidence_tier,
)

T = 1791800000


def rows(*events):
    return [O(T + offset,qty,source) for offset,qty,source in events]


def regular_cycles(n=10):
    points=[O(T,0,"yata")]
    t=T
    for i in range(n):
        # Both threshold boundaries are witnessed by the same source.
        t+=600
        points.append(O(t,200,"yata"))
        # The middle of stocked and depleted phases can be observed by
        # the fallback without invalidating start/end boundaries.
        t+=100
        points.append(O(t,100,"prometheus"))
        t+=100
        points.append(O(t,95,"yata"))
        t+=800
        points.append(O(t,0,"yata"))
        t+=100
        points.append(O(t,0,"prometheus"))
        t+=100
        points.append(O(t,0,"yata"))
    return points,t


class ProviderContinuityTests(unittest.TestCase):
    def test_benign_switch_does_not_erase_observed_phase_start_end(self):
        trace=rows(
            (0,0,"yata"), (100,90,"yata"),(200,95,"prometheus"),
            (250,70,"yata"),(400,0,"yata")
        )
        old=fast_phases(trace,asof=T+400)
        improved=provider_continuous_phases(trace,asof=T+400)
        self.assertEqual(old["stocked_durations"],[])
        self.assertEqual(improved["stocked_durations"],[300])
        self.assertEqual(improved["phase_onset"],T+400)
        self.assertEqual(improved["diagnostics"]["benign_provider_switches_preserved"],2)
        self.assertEqual(improved["diagnostics"]["clean_observed_threshold_crossings"],2)

    def test_single_observed_bounded_period_is_valid_history_not_no_data(self):
        # A completed high period is real evidence even without V128's
        # arbitrary 5+5 minimum; we do not pretend it validates a flight.
        trace=rows((0,0,"yata"),(100,80,"yata"),
                   (150,80,"prometheus"),(200,80,"yata"),
                   (300,0,"yata"))
        observed=provider_continuous_phases(trace,asof=T+300)
        tier=observed_cycle_evidence_tier(observed)
        self.assertEqual(tier["tier"],
                         "ONE_PHASE_KIND_OBSERVED_NO_CLOSED_FULL_CYCLE")
        self.assertTrue(tier["history_exists"])
        self.assertTrue(tier["supports_valid_completed_stocked_lifetime"])
        self.assertFalse(tier["sufficient_for_existing_v128_monte_carlo"])
        self.assertFalse(tier["permission_to_publish_as_certified_departure"])

    def test_sparse_both_phase_types_count_as_bounded_history(self):
        trace=rows((0,0,"yata"),(100,80,"yata"),
                   (200,0,"yata"),(300,80,"yata"))
        tier=observed_cycle_evidence_tier(
            provider_continuous_phases(trace,asof=T+300))
        self.assertEqual(tier["tier"],"BOUNDED_HISTORY_SPARSE_PROVISIONAL")
        self.assertEqual(tier["observed_bounded_stocked_intervals"],1)
        self.assertEqual(tier["observed_bounded_depleted_intervals"],1)
        self.assertFalse(tier["arrival_recommendation_accuracy_established"])

    def test_no_provider_switch_parity_with_v128(self):
        trace=rows((0,0,"yata"),(100,80,"yata"),
                   (250,0,"yata"),(500,80,"yata"),
                   (600,0,"yata"))
        a=fast_phases(trace,asof=T+600)
        b=provider_continuous_phases(trace,asof=T+600)
        for field in ("phase","phase_onset","last_observation",
                      "stocked_durations","depleted_durations"):
            self.assertEqual(a[field],b[field],field)

    def test_cannot_infer_restock_if_provider_switch_changes_threshold(self):
        trace=rows((0,0,"yata"),(100,80,"prometheus"), # uncertain
                   (200,90,"prometheus"),(300,0,"prometheus"))
        b=provider_continuous_phases(trace,asof=T+300)
        self.assertEqual(b["stocked_durations"],[])
        self.assertEqual(b["depleted_durations"],[])
        self.assertEqual(b["phase_onset"],T+300)
        self.assertEqual(b["diagnostics"]["cross_source_threshold_conflict"],1)

    def test_collection_gap_still_breaks_unverified_phase(self):
        trace=rows((0,0,"yata"),(100,80,"yata"),
                   (200,75,"prometheus"),(300,0,"prometheus"))
        b=provider_continuous_phases(trace,asof=T+300,
                                     gaps=[(T+150,T+175)])
        self.assertEqual(b["stocked_durations"],[])
        self.assertEqual(b["phase_onset"],T+300)
        self.assertEqual(b["diagnostics"]["restarted_after_gap_or_clock"],1)

    def test_many_completed_observed_starts_ends_enable_model_curve(self):
        trace,last=regular_cycles()
        old=fast_phases(trace,asof=last)
        good=provider_continuous_phases(trace,asof=last)
        self.assertGreaterEqual(len(good["stocked_durations"]),9)
        self.assertGreaterEqual(len(good["depleted_durations"]),9)
        self.assertEqual(old["stocked_durations"],[])
        self.assertEqual(old["depleted_durations"],[])
        # Same V128 Monte Carlo function, only safer recovery of genuinely
        # observed past cycles; no change to its uncertainty threshold.
        curve=empirical_arrival_scores(good,"uni:Nessie Plushie",asof=last)
        self.assertEqual(curve["status"],"ISSUED_EMPIRICAL_TWO_PHASE_CURVE")
        old_curve=empirical_arrival_scores(old,"uni:Nessie Plushie",asof=last)
        self.assertIn(old_curve["status"],
                      ("CURRENT_PHASE_ONSET_UNKNOWN",
                       "INSUFFICIENT_COMPLETED_CYCLES"))
        self.assertFalse(curve["score_is_calibrated_probability"])

    def test_comparison_is_nonmutating_and_only_past_events(self):
        original,last=regular_cycles(n=7)
        orig=list(original)
        summary=compare_phase_eligibility(original,asof=last)
        self.assertGreater(summary["new_completed_stocked"],
                           summary["old_completed_stocked"])
        self.assertEqual(orig,original)
        self.assertEqual(summary["safety"],
                         "RESEARCH_ONLY_NO_FORWARD_ACCURACY_CLAIM")
        with self.assertRaises(ValueError):
            provider_continuous_phases(original,asof=last-1)

    def test_resets_on_clock_regression(self):
        trace=rows((0,0,"yata"),(100,100,"yata"),
                   (50,120,"yata"),(400,0,"yata"))
        new=provider_continuous_phases(trace,asof=T+400)
        self.assertIsNone(new["stocked_durations"][-1] if new["stocked_durations"] else None)
        self.assertEqual(new["diagnostics"]["restarted_after_gap_or_clock"],1)


if __name__=="__main__":
    unittest.main()
