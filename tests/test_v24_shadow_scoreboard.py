"""Regression tests for the read-only V24 all-item CSV exporter."""
import unittest
from research.v24_shadow_scoreboard import SCHEMA, summarize


class ShadowScoreboardTests(unittest.TestCase):
    def sample(self):
        return {
            "schema": SCHEMA,
            "results": {
                "arg:Tear Gas": {
                    "status": "complete", "shared_starts": 40,
                    "matched": {"versions": {
                        "v19": {"paired_n": 40, "recommendations": 38, "hits": 23},
                        "v20": {"paired_n": 40, "recommendations": 40, "hits": 30},
                        "v21": {"paired_n": 40, "recommendations": 20, "hits": 18},
                    }}
                },
                "chi:Bo Staff": {"status": "no_clean_new_sessions"},
            }
        }

    def test_all_start_leader_not_conditional_leader(self):
        rows = summarize(self.sample())
        item = [r for r in rows if r["item"] == "arg:Tear Gas"]
        self.assertEqual({r["item_leader"] for r in item}, {"v20"})
        self.assertTrue(all(r["leader_evidence"] == "descriptive_only_no_promotion" for r in item))
        assert_v21 = next(r for r in item if r["version"] == "v21")
        self.assertEqual(assert_v21["all_start_success_rate"], 18 / 40)
        self.assertEqual(assert_v21["conditional_success_rate"], 18 / 20)
        self.assertEqual(assert_v21["coverage"], 0.5)

    def test_insufficient_sample_no_promotion(self):
        x = self.sample()
        x["results"]["arg:Tear Gas"]["shared_starts"] = 10
        for row in x["results"]["arg:Tear Gas"]["matched"]["versions"].values():
            row.update(paired_n=10, recommendations=8, hits=7)
        res = summarize(x)
        self.assertEqual(res[0]["item_leader"], "tie")
        self.assertEqual(res[0]["leader_evidence"], "too_few_independent_starts")

    def test_reject_v1_and_impossible_counts(self):
        with self.assertRaises(ValueError):
            summarize({"schema": "frozen-champion-v24-new-data-shadow-v1"})
        x = self.sample()
        x["results"]["arg:Tear Gas"]["matched"]["versions"]["v21"]["hits"] = 21
        with self.assertRaises(ValueError):
            summarize(x)


if __name__ == "__main__":
    unittest.main()
