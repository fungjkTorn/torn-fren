"""As-issued item profiles and conservative per-item LOW/HIGH router."""
import unittest

from research.v107_explicit_restock_cycle_baseline import StockObservation as O
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v156_item_cycle_profile_router import (
    item_cycle_profile, route_issued_prediction, _spearman,
)

T=1791800000


def history(*,stock_durations=None, depletion_durations=None):
    # 12 observed transitions of each kind, with first LOW left-censored.
    stock_durations=stock_durations or [500]*12
    depletion_durations=depletion_durations or [100,200,300,400,500,600,
                                                 700,800,900,1000,1100,1200]
    t=T
    rows=[O(t,0,"yata")]
    for low,high in zip(depletion_durations,stock_durations):
        t+=low
        rows.append(O(t,100,"yata"))
        if high>180:
            rows.append(O(t+70,70,"prometheus"))
            rows.append(O(t+130,80,"yata"))
        t+=high
        rows.append(O(t,0,"yata"))
    return provider_continuous_phases(rows,asof=t),t


def forecast(key,issued,model,departure):
    return {
        "item_key":key,"issued_epoch":issued,
        "cycle_sampling":model,
        "first_reachable":None if departure is None else {
            "departure_epoch":departure,
            "arrival_epoch":departure+3600,
            "wait_seconds":departure-issued,
        },
    }


class ItemSpecificRouterTests(unittest.TestCase):
    def test_perfect_positive_dependence_routes_paired_when_completed(self):
        low=[100,200,300,400,500,600,700,800,900,1000,1100,1200]
        high=[x+200 for x in low]
        phases,t=history(stock_durations=high,depletion_durations=low)
        p=item_cycle_profile("chi:Peony",phases,asof=t)
        self.assertEqual(p["predeclared_research_route"],"paired_complete")
        self.assertGreaterEqual(p["direct_completed_low_to_high_pairs"],8)
        self.assertGreater(p["paired_low_high_rank_correlation"],.99)
        self.assertTrue(p["outcome_free_selection"])
        self.assertEqual(p["stock_duration_regime"],"MEDIUM_5_TO_20MIN")
        self.assertGreater(p["flight_over_median_stocked_lifetime"],1)

    def test_negative_dependence_is_not_automatically_discarded(self):
        low=[100,200,300,400,500,600,700,800,900,1000,1100,1200]
        high=[2000-x for x in low]
        phases,t=history(stock_durations=high,depletion_durations=low)
        p=item_cycle_profile("uni:Red Fox Plushie",phases,asof=t)
        self.assertEqual(p["predeclared_research_route"],"paired_complete")
        self.assertLess(p["paired_low_high_rank_correlation"],-.99)

    def test_constant_high_lifetime_keeps_independent_and_short_stock_regime(self):
        phases,t=history(stock_durations=[240]*12)
        p=item_cycle_profile("jap:Xanax",phases,asof=t)
        self.assertEqual(p["predeclared_research_route"],"independent")
        self.assertEqual(p["selection_reason"],"NO_IDENTIFIABLE_DEPENDENCE")
        self.assertEqual(p["stock_duration_regime"],"SHORT_LT_5MIN")
        self.assertGreater(p["flight_over_median_cycle"],1.0)

    def test_unverified_few_pairs_does_not_trigger_item_winner(self):
        phases,t=history(stock_durations=[300]*5,depletion_durations=[200]*5)
        p=item_cycle_profile("mex:Jaguar Plushie",phases,asof=t)
        self.assertEqual(p["predeclared_research_route"],"independent")
        self.assertEqual(p["selection_reason"],"SPARSE_DIRECTLY_MATCHED_EPISODES")

    def test_router_falls_back_safely_and_never_uses_outcome_label(self):
        phases,t=history(
            stock_durations=[x+200 for x in range(100,1300,100)])
        p=item_cycle_profile("uni:Nessie Plushie",phases,asof=t)
        self.assertEqual(p["predeclared_research_route"],"paired_complete")
        old=forecast("uni:Nessie Plushie",t,"independent",t+300)
        paired=forecast("uni:Nessie Plushie",t,"paired_complete",t+120)
        r=route_issued_prediction(p,old,paired)
        self.assertEqual(r["departure_epoch"],t+120)
        self.assertEqual(r["actual_model_used"],"paired_complete")
        self.assertFalse(r["outcome_optimized_posthoc"])
        paired["first_reachable"]=None
        fallback=route_issued_prediction(p,old,paired)
        self.assertEqual(fallback["departure_epoch"],t+300)
        self.assertTrue(fallback["paired_fell_back_to_independent"])
        with self.assertRaisesRegex(ValueError,"mixed item"):
            route_issued_prediction(
                p,old,forecast("uni:Nessie Plushie",t+1,"paired_complete",None))

    def test_pairwise_rank_ties_use_arithmetic_centering(self):
        self.assertAlmostEqual(_spearman([1,1,1,2,3],[1,1,1,2,3]),1.0)
        self.assertIsNone(_spearman([1]*10,list(range(10))))

    def test_phase_period_after_issue_is_rejected(self):
        phases,t=history()
        phases["observed_bounded_stocked_windows"].append((t+1,t+11))
        with self.assertRaisesRegex(ValueError,"out-of-range"):
            item_cycle_profile("mex:Jaguar Plushie",phases,asof=t)


if __name__=="__main__":
    unittest.main()
