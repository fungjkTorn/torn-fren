"""V157 chronological first-cycle stock survival score; no late outcomes in selection."""
import unittest

from research.v107_explicit_restock_cycle_baseline import StockObservation as O
from research.v145_provider_continuous_phases import provider_continuous_phases
from research.v157_prequential_stock_survival_router import (
    cross_validate_cycle_survival,prequential_item_route,
)

T=1791800000


def history(pairs):
    t=T
    observations=[O(t,0,"yata")]
    for depleted,stocked in pairs:
        t+=depleted
        observations.append(O(t,100,"yata"))
        if stocked>=240:
            observations.append(O(t+100,90,"prometheus"))
        t+=stocked
        observations.append(O(t,0,"yata"))
    return provider_continuous_phases(observations,asof=t),t


class PrequentialPairedRouterTests(unittest.TestCase):
    def test_joint_phase_relationship_outperforms_cartesian_mixing(self):
        # All observed cycles have either (short LOW, short HIGH) or
        # (long LOW, long HIGH). Independent Cartesian products synthesize
        # false stocked intervals after the short LOW and long HIGH.
        pairs=[(100,100),(900,900)]*7
        result=cross_validate_cycle_survival(pairs)
        self.assertEqual(result["heldout_episodes"],9)
        self.assertGreater(result["heldout_scores"],20)
        self.assertEqual(result["selected_sampling"],"paired_complete")
        self.assertGreater(result["paired_brier_improvement"],.02)
        self.assertTrue(result["asof_research_only"])
        self.assertFalse(result["real_flight_success_verified"])

    def test_constant_stock_survival_keeps_independent(self):
        result=cross_validate_cycle_survival(
            [(100+i*10,500) for i in range(14)])
        self.assertEqual(result["selected_sampling"],"independent")
        self.assertEqual(result["reason"],
                         "NONIDENTIFIABLE_CONSTANT_PHASE_DURATION")

    def test_fewer_than_nine_completed_episode_abstains(self):
        result=cross_validate_cycle_survival(
            [(200+i*10,100+i*10) for i in range(8)])
        self.assertEqual(result["selected_sampling"],"independent")
        self.assertEqual(result["heldout_episodes"],0)
        self.assertEqual(result["reason"],"INSUFFICIENT_DIRECTLY_BOUNDED_PAIRS")

    def test_issue_time_history_changes_only_when_observation_arrives(self):
        pairs=[(100,100),(900,900)]*8
        profile,issue=history(pairs[:14])
        a=prequential_item_route("uni:Red Fox Plushie",profile,asof=issue)
        b=prequential_item_route("uni:Red Fox Plushie",profile,asof=issue+300)
        self.assertEqual(a["selected_sampling"],b["selected_sampling"])
        self.assertEqual(a["paired_brier_improvement"],b["paired_brier_improvement"])
        self.assertTrue(a["history_pinned_to_issue"])
        self.assertFalse(a["departure_advice_published"])
        with self.assertRaises(ValueError):
            prequential_item_route("uni:Red Fox Plushie",profile,asof=issue-1)

    def test_future_completed_phases_are_forbidden(self):
        phases,issue=history([(100,500)]*10)
        phases["observed_bounded_stocked_windows"].append((issue+1,issue+500))
        with self.assertRaises(ValueError):
            prequential_item_route("jap:Xanax",phases,asof=issue)

    def test_invalid_cycle_lengths_fail_closed(self):
        for pair in ([(100,-200)]*12,[("100",200)]*12,[(0,100)]*12):
            with self.assertRaises(ValueError):
                cross_validate_cycle_survival(pair)


if __name__=="__main__":
    unittest.main()
