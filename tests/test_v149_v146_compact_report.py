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

    def test_recency_restocks_are_reported_as_matched_not_unconditional_wins(self):
        data=fixture()
        item=data["items"]["chi:Peony"]
        item["recent_recent_5_scored"]=2
        item["recent_recent_5_abs_total_seconds"]=600
        item["recent_recent_5_paired"]=2
        item["recent_recent_5_beats_v151"]=1
        item["v151_beats_recent_recent_5"]=1
        item["recent_recent_5_ties"]=0
        output=compact(data)
        self.assertIn("recent_5 2 paired, 1 better/1 worse",output)
        self.assertIn("5.0m",output)
        item["recent_recent_5_paired"]=3
        with self.assertRaisesRegex(ValueError,"unbalanced recency"):
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
