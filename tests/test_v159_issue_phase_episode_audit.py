"""V159 counts distinct issue-time stock phase episodes, not fake trips."""
import unittest

from research.v159_issue_phase_episode_audit import episode_audit

T=1791800000


def issue(item="mex:Jaguar Plushie",phase="LOW",onset=T,
          issued=T+300,old="MISS",paired="HIT",routed="HIT",
          selected="paired_complete"):
    return {
        "item_key":item,"issued_epoch":issued,
        "issue_phase":phase,"issue_phase_onset":onset,
        "stable_outcome":old,"paired_outcome":paired,
        "flight_horizon_outcome":routed,
        "flight_horizon_selection":selected,
    }


class GroupedIssueEpisodeTests(unittest.TestCase):
    def test_same_stock_episode_repeat_disagreements_count_once(self):
        rows=[
            issue(),
            issue(issued=T+3600,routed="MISS",selected="independent"),
            issue(phase="HIGH",onset=T+3900,issued=T+4000,
                  old="HIT",paired="MISS",routed="HIT",
                  selected="independent"),
        ]
        evidence=episode_audit(rows)
        t=evidence["totals"]
        item=evidence["items"]["mex:Jaguar Plushie"]
        self.assertEqual(t["eligible_mature_issue_rows"],3)
        self.assertEqual(t["distinct_asof_phase_episodes"],2)
        self.assertEqual(t["raw_paired_exclusive_issue_wins"],2)
        self.assertEqual(t["raw_independent_exclusive_issue_wins"],1)
        self.assertEqual(t["raw_paired_winning_episodes"],1)
        self.assertEqual(t["raw_independent_winning_episodes"],1)
        self.assertEqual(t["v158_winning_episodes"],1)
        self.assertEqual(t["v158_losing_episodes"],0)
        self.assertEqual(t["raw_paired_only_missed_by_v158"],1)
        self.assertEqual(item["v158_paired_chosen_issues"],1)
        self.assertTrue(evidence["not_independent_future_restock_proof"])
        self.assertTrue(evidence["historical_backfill_provenance_unfrozen"])

    def test_selected_paired_with_independent_fallback_counts_missed_win(self):
        row=issue(selected="paired_complete",routed="MISS")
        row["flight_horizon_actual"]="independent"
        result=episode_audit([row])
        t=result["totals"]
        self.assertEqual(t["raw_paired_only_missed_by_v158"],1)
        self.assertEqual(
            result["items"]["mex:Jaguar Plushie"]["v158_paired_chosen_issues"],0)
        self.assertEqual(t["v158_winning_episodes"],0)

    def test_unknown_unmatured_results_are_not_losses_or_tied_episodes(self):
        rows=[
            issue(old="PENDING",paired="HIT",routed="MISS"),
            issue(phase="HIGH",onset=T+20,issued=T+40,
                  old="UNKNOWN_DATA_GAP",paired="HIT",
                  routed="UNKNOWN_DATA_GAP"),
        ]
        t=episode_audit(rows)["totals"]
        self.assertEqual(t["raw_scorable_phase_episodes"],0)
        self.assertEqual(t["v158_scorable_phase_episodes"],0)
        self.assertEqual(t["distinct_asof_phase_episodes"],0)
        self.assertEqual(t["raw_paired_exclusive_issue_wins"],0)
        self.assertEqual(t["raw_independent_exclusive_issue_wins"],0)

    def test_frozen_origin_missing_does_not_fabricate_episode(self):
        row=issue()
        row["issue_phase_onset"]=None
        second=issue()
        second["issued_epoch"]=None
        t=episode_audit([row,second])["totals"]
        self.assertEqual(t["unknown_or_unsupportable_issue_phase_rows"],2)
        self.assertEqual(t["distinct_asof_phase_episodes"],0)

    def test_both_modes_agree_means_distinct_tied_episode(self):
        result=episode_audit([
            issue(old="HIT",paired="HIT",routed="HIT"),
            issue(issued=T+4000,old="MISS",paired="MISS",routed="MISS"),
        ])
        t=result["totals"]
        self.assertEqual(t["distinct_asof_phase_episodes"],1)
        self.assertEqual(t["raw_paired_winning_episodes"],0)
        self.assertEqual(t["raw_independent_winning_episodes"],0)
        self.assertEqual(result["items"]["mex:Jaguar Plushie"][
            "raw_tied_or_mixed_episodes"],1)
        self.assertEqual(result["items"]["mex:Jaguar Plushie"][
            "v158_tied_or_mixed_episodes"],1)

    def test_nonexistent_future_phase_not_counted(self):
        sample=issue(onset=T+5000)
        t=episode_audit([sample])["totals"]
        self.assertEqual(t["distinct_asof_phase_episodes"],0)
        self.assertEqual(t["unknown_or_unsupportable_issue_phase_rows"],1)

    def test_unknown_old_new_but_router_mature_keeps_separate_denominator(self):
        row=issue(old="MISS",paired="PENDING",routed="HIT")
        item=episode_audit([row])["items"]["mex:Jaguar Plushie"]
        self.assertEqual(item["raw_scorable_phase_episodes"],0)
        self.assertEqual(item["v158_scorable_phase_episodes"],1)
        self.assertEqual(item["v158_winning_episodes"],1)

    def test_reject_malformed_or_unbounded_input(self):
        for x in ({},None,[None],[{}]*20001):
            with self.subTest(x=str(type(x))),self.assertRaises(ValueError):
                episode_audit(x)


if __name__=="__main__":
    unittest.main()
