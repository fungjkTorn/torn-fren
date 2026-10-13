"""Compact 24-item issue-locked evidence stays legible and denominator-safe."""
import unittest
from copy import deepcopy

from research.v149_v146_compact_report import compact
from research.v128_full24_earliest_shadow import exact_roster


def fixture():
    rows={}
    for item in exact_roster():
        rows[item]={
            "issued_hourly_samples":23,
            "original_proposals":12,
            "new_proposals":4,
            "recovered":9,
            "explicit_proposals":17,
            "HIT":3, "MISS":1, "PENDING":0,
            "new_only":1,"now_only":0,
            "matched_new_vs_now":4,
            "explicit_proxy_hit":10,"explicit_proxy_miss":5,
            "explicit_proxy_pending":1,"explicit_proxy_unknown":1,
            "explicit_only_vs_now":2,"now_only_vs_explicit":1,
            "matched_explicit_vs_now":15,
            "long_wait_needs_explanation":0,
            "explicit_departure_median_wait_seconds":700,
            "stable_proposals":12,"stable_proxy_hit":8,
            "stable_proxy_miss":2,"stable_proxy_pending":1,
            "stable_proxy_unknown":1,"matched_stable_vs_now":10,
            "stable_only_vs_now":3,"now_only_vs_stable":2,
            "stable_departure_median_wait_seconds":300,
        }
    # Original Japanese Xanax can have zero usable proposals but VALID cycles.
    rows["jap:Xanax"].update({
        "original_proposals":0,"new_proposals":0,
        "explicit_proposals":0,"explicit_proxy_hit":0,
        "explicit_proxy_miss":0,"explicit_proxy_pending":0,
        "explicit_proxy_unknown":0,"HIT":0,"MISS":0,
        "matched_new_vs_now":0,
        "matched_explicit_vs_now":0,
        "explicit_only_vs_now":0,"now_only_vs_explicit":0,
        "explicit_departure_median_wait_seconds":None,
        "stable_proposals":0,"stable_proxy_hit":0,
        "stable_proxy_miss":0,"stable_proxy_pending":0,
        "stable_proxy_unknown":0,
        "matched_stable_vs_now":0,"stable_only_vs_now":0,
        "now_only_vs_stable":0,
        "stable_departure_median_wait_seconds":None,
    })
    return {
        "status":"READ_ONLY_ASOF_REPLAY_NOT_PROSPECTIVE_CERTIFICATION",
        "exact_item_roster":24,
        "hourly_issued_cohorts":552,
        "monte_carlo_replayed":96,
        "replay_cap":96,
        "no_writes":True,
        "summary":{
            "NEW_ELIGIBLE_BUT_RESOURCE_LIMIT":389,
            "OBSERVED_HISTORY_SPARSE_OR_ONSET_UNKNOWN":67,
            "recovered":217,
        },
        "items":rows,
        "issue_phase_episode_audit":{
            "method":"GROUP_BY_ASISSUED_STOCK_PHASE_EPISODE",
            "totals":{
                "distinct_asof_phase_episodes":0,
                "raw_scorable_phase_episodes":0,
                "v158_scorable_phase_episodes":0,
                "raw_paired_exclusive_issue_wins":0,
                "raw_independent_exclusive_issue_wins":0,
                "raw_paired_winning_episodes":0,
                "raw_independent_winning_episodes":0,
                "v158_winning_episodes":0,
                "v158_losing_episodes":0,
                "raw_paired_only_missed_by_v158":0,
            },
            "items":{},
        },
    }


class CompactEvidenceTests(unittest.TestCase):
    def test_24_item_report_is_short_and_uses_paired_baselines(self):
        output=compact(fixture())
        lines=output.splitlines()
        self.assertLess(len(lines),45)
        self.assertIn("V145 recovered NEW eligibility on 217 cohorts",output)
        self.assertIn("V148 explicit-stock-window proposals",output)
        self.assertIn("V151 stable whole-cycle scenario departures",output)
        self.assertIn("V151 matched vs leave-now",output)
        self.assertIn("net +",output)
        self.assertIn("jap:Xanax",output)
        self.assertIn("uni:Xanax",output)
        self.assertIn("not independent trips",output)

    def test_pending_counts_are_not_overwritten_by_matched_counts(self):
        data=fixture()
        output=compact(data)
        # 23 items have 1 pending V151 and V148; the Japan fixture has 0.
        # 230 matched pairs exist; never print 230 'pending'.
        self.assertIn("V148 proxy outcomes:",output)
        self.assertIn("23 pending, 23 unknown",output)
        self.assertIn("V151 proxy outcomes:",output)
        self.assertIn("V151 matched vs leave-now: 230 pairs",output)
        self.assertNotIn("230 pending",output)

    def test_json_sample_must_balance_outcomes(self):
        data=fixture()
        data["items"]["chi:Peony"]["explicit_proxy_hit"]+=1
        with self.assertRaisesRegex(ValueError,"outcome denominators"):
            compact(data)

    def test_stable_denominator_check(self):
        data=fixture()
        data["items"]["chi:Peony"]["stable_proxy_hit"]+=1
        with self.assertRaisesRegex(ValueError,"outcome denominators"):
            compact(data)

    def test_legacy_recency_restocks_still_validate_paired_counts_when_not_printed(self):
        data=fixture()
        item=data["items"]["chi:Peony"]
        item["recent_recent_5_scored"]=2
        item["recent_recent_5_abs_total_seconds"]=600
        item["recent_recent_5_paired"]=2
        item["recent_recent_5_beats_v151"]=1
        item["v151_beats_recent_recent_5"]=1
        item["recent_recent_5_ties"]=0
        output=compact(data)
        # V153 metrics remain validated in underlying per-item replay data
        # but are omitted from the <=44-line compact V157 console report.
        self.assertIn("V157 PREQUENTIAL",output)
        self.assertIn("chi:Peony",output)
        item["recent_recent_5_paired"]=3
        with self.assertRaisesRegex(ValueError,"unbalanced recency"):
            compact(data)

    def test_v159_top_level_episode_results_render_nonzero_with_per_item_row(self):
        data=fixture()
        item=data["items"]["mex:Jaguar Plushie"]
        item["paired_proposals"]=2
        item["paired_proxy_hit"]=2
        item["paired_only_vs_independent"]=2
        item["paired_vs_independent_matched"]=2
        item["flight_horizon_proposals"]=2
        item["flight_horizon_selected_paired"]=2
        item["flight_horizon_proxy_hit"]=2
        item["flight_horizon_vs_independent_matched"]=2
        item["flight_horizon_only_vs_independent"]=1
        audit=data["issue_phase_episode_audit"]
        audit["totals"].update({
            "distinct_asof_phase_episodes":2,
            "raw_scorable_phase_episodes":2,
            "v158_scorable_phase_episodes":2,
            "raw_paired_exclusive_issue_wins":2,
            "raw_paired_winning_episodes":2,
            "v158_winning_episodes":1,
            "raw_paired_only_missed_by_v158":1,
        })
        audit["items"]["mex:Jaguar Plushie"]={
            "raw_scorable_phase_episodes":2,
            "v158_scorable_phase_episodes":2,
            "raw_paired_winning_episodes":2,
            "raw_independent_winning_episodes":0,
        }
        output=compact(data)
        self.assertIn("2 paired-score episodes (2 favor paired / 0 favor independent)",output)
        self.assertIn("V158: 2 clusters (1 win / 0 loss)",output)
        self.assertIn("raw paired-only issue wins V158 skipped 1",output)
        jaguar=next(line for line in output.splitlines()
                    if line.startswith("mex:Jaguar Plushie"))
        self.assertIn("2/0",jaguar)

    def test_v159_missing_top_level_audit_is_error_not_fake_zero(self):
        data=fixture()
        del data["issue_phase_episode_audit"]
        with self.assertRaisesRegex(ValueError,"top-level phase episode evidence"):
            compact(data)
        # The previous bug looked in a separate ephemeral source dictionary:
        # even false legacy data elsewhere must never replace the top level.
        data["summary"]["issue_phase_episode_audit"]={
            "method":"GROUP_BY_ASISSUED_STOCK_PHASE_EPISODE",
            "totals":{"raw_scorable_phase_episodes":999},
            "items":{},
        }
        with self.assertRaisesRegex(ValueError,"top-level phase episode evidence"):
            compact(data)

    def test_mature_paired_outcomes_cannot_have_zero_phase_groups(self):
        data=fixture()
        data["items"]["chi:Peony"]["paired_proposals"]=1
        data["items"]["chi:Peony"]["paired_proxy_hit"]=1
        data["items"]["chi:Peony"]["paired_vs_independent_matched"]=1
        with self.assertRaisesRegex(ValueError,"zero audited phases"):
            compact(data)

    def test_v159_per_item_episode_totals_fail_on_mismatch(self):
        data=fixture()
        audit=data["issue_phase_episode_audit"]
        audit["totals"]["raw_scorable_phase_episodes"]=1
        with self.assertRaisesRegex(ValueError,"item/total denominators"):
            compact(data)

    def test_no_partial_roster_or_database_write_claims(self):
        for mode in ("absent","write","issue_mismatch","extra_monte_carlo"):
            data=fixture()
            if mode=="absent":
                data["items"].pop("jap:Xanax")
            elif mode=="write":
                data["no_writes"]=False
            elif mode=="issue_mismatch":
                data["hourly_issued_cohorts"]-=1
            else:
                data["monte_carlo_replayed"]=97
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                compact(data)


if __name__=="__main__":
    unittest.main()
