"""V130 phase-pinned Monte Carlo reduces artificial reissue jitter."""
import unittest

from research import v128_full24_earliest_shadow as base
from research import v130_phase_pinned_mc_challenger as m
from research.v107_explicit_restock_cycle_baseline import StockObservation

T0=1790000000


def trace(cycles=60,*,phase="HIGH"):
    t=T0
    history=[StockObservation(t,0,"yata")]
    for i in range(cycles):
        t+=5400
        history.append(StockObservation(t,200,"yata"))
        if i==cycles-1 and phase=="HIGH":
            break
        t+=6900
        history.append(StockObservation(t,0,"yata"))
    return history,t


class PhasePinnedStabilityTests(unittest.TestCase):
    def test_same_phase_same_seed_even_when_wall_clock_advances(self):
        obs,at=trace()
        phase1=base.fast_phases(obs,asof=at+180)
        phase2=base.fast_phases(obs,asof=at+186)
        self.assertEqual(
            m.phase_pinned_seed(phase1,"uni:Nessie Plushie"),
            m.phase_pinned_seed(phase2,"uni:Nessie Plushie"))
        old1=m.model(phase1,"uni:Nessie Plushie",asof=at+180)
        old2=m.model(phase2,"uni:Nessie Plushie",asof=at+186)
        self.assertEqual(old1["status"],"ISSUED_EMPIRICAL_TWO_PHASE_CURVE")
        self.assertEqual(old1["scores"],old2["scores"])
        self.assertTrue(old1["scores_distinct"]>1)
        self.assertFalse(old1["score_is_calibrated_probability"])

    def test_different_stock_phase_changes_seed(self):
        obs,at=trace(phase="LOW")
        first=base.fast_phases(obs,asof=at)
        first_seed=m.phase_pinned_seed(first,"uni:Nessie Plushie")
        more=[*obs,StockObservation(at+3000,100,"yata")]
        next_phase=base.fast_phases(more,asof=at+3000)
        self.assertNotEqual(first_seed,
            m.phase_pinned_seed(next_phase,"uni:Nessie Plushie"))
        self.assertNotEqual(first_seed,
            m.phase_pinned_seed(first,"uni:Red Fox Plushie"))

    def test_missing_phase_onset_still_abstains(self):
        obs,at=trace()
        more=[*obs,StockObservation(at+100,120,"prometheus")]
        h=base.fast_phases(more,asof=at+120)
        self.assertIsNone(m.phase_pinned_seed(h,"uni:Nessie Plushie"))
        c=m.model(h,"uni:Nessie Plushie",asof=at+120)
        self.assertEqual(c["status"],"CURRENT_PHASE_ONSET_UNKNOWN")
        r=m.record("uni:Nessie Plushie",base.exact_roster()["uni:Nessie Plushie"],
                   more,[],issued=at+120)
        self.assertEqual(r["earliest_departure"],None)
        self.assertEqual(r["departure_state"],"ABSTAIN")

    def test_fixed_observation_history_drift_audit(self):
        obs,at=trace()
        report=m.drift_comparison(
            obs,"uni:Nessie Plushie",issued=at+180,seconds=6)
        self.assertTrue(report["same_input_stock_history_both_queries"])
        self.assertFalse(report["arrival_success_verified"])
        self.assertEqual(report["comparisons"]["v130"]["score_drift_max"],0)
        self.assertGreaterEqual(
            report["comparisons"]["v128"]["score_drift_max"],0)
        with self.assertRaises(ValueError):
            m.drift_comparison(obs,"uni:Nessie Plushie",
                               issued=at+180,seconds=0)

    def test_country_specific_travel_kept(self):
        obs,at=trace()
        key="can:Xanax"
        curve=m.model(base.fast_phases(obs,asof=at+180),key,asof=at+180)
        choice=base.earliest_credible_for_country(curve,key)
        if choice["departure"] is not None:
            self.assertEqual(choice["arrival"]-choice["departure"],
                             base.TRAVEL_SECONDS["can"])
        row=m.record(key,base.exact_roster()[key],obs,[],issued=at+180)
        self.assertEqual(row["policy_id"],m.POLICY)
        self.assertTrue(row["research_only"])
        self.assertFalse(row["published_to_website"])
        self.assertEqual(row["travel_seconds"],base.TRAVEL_SECONDS["can"])


if __name__=="__main__":
    unittest.main()
