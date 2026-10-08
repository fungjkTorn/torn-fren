"""Tests for all-item V21 checkpoint target classification and leaderboard."""
import unittest

from services.all_item_v21_checkpoint_tournament import plan, build_leaderboard


class CheckpointPlanningTest(unittest.TestCase):
    def test_classifies_all_items_without_destroying_best_existing_evidence(self):
        source = {"results": {
            "mex:Strong": {"status": "complete", "cycles": 90},
            "mex:Weak": {"status": "complete", "cycles": 40},
            "mex:Seeded": {"status": "complete", "cycles": 40},
            "mex:Insufficient": {"status": "insufficient_cycles", "cycles": 2},
            "mex:TooFew": {"status": "complete", "cycles": 8},
            "jap:Xanax": {"status": "complete", "cycles": 100},
            "mex:SparseEligible": {"status": "insufficient_cycles", "cycles": 9},
        }}
        audit = {"masters": [{
            "master": "data/all_item_v19/master.json",
            "items": [
                {"key": "mex:Strong", "corrected_rate": .95},
                {"key": "mex:Weak", "corrected_rate": .30},
                {"key": "mex:Seeded", "corrected_rate": .81},
                {"key": "mex:TooFew", "corrected_rate": .15},
            ],
        }]}
        seed = {"results": {"mex:Seeded": {"status": "complete"}}}
        quantities = {k: 100 for k in source["results"]}
        quantities["mex:TooFew"] = 12
        out = plan(source, audit, seed, quantities, .90, 6, 30, False)
        c = {r["key"]: r["category"] for r in out}
        self.assertEqual(len(c), 7)
        self.assertEqual(c["mex:Strong"], "v19_corrected_incumbent_retained")
        self.assertEqual(c["mex:Weak"], "v21_corrected_tournament")
        self.assertEqual(c["mex:Seeded"], "existing_v21_seed")
        self.assertEqual(c["mex:Insufficient"], "needs_sparse_availability_model")
        self.assertEqual(c["mex:TooFew"], "threshold_not_observed")
        self.assertEqual(c["mex:SparseEligible"], "v21_corrected_tournament")
        self.assertEqual(c["jap:Xanax"], "specialized_champion_pending")

    def test_leaderboard_does_not_automatically_promote_v21(self):
        report = {
            "plan": [
                {"key": "mex:Weak", "category": "v21_corrected_tournament",
                 "v19_corrected_rate": .50},
                {"key": "mex:Strong", "category": "v19_corrected_incumbent_retained",
                 "v19_corrected_rate": .96},
            ],
            "results": {
                "mex:Weak": {
                    "status": "complete",
                    "selected_on_training": {
                        "config": {"name": "dyn7"},
                        "holdout": {"arrival_success_rate": .93, "valid_starts": 50,
                                    "median_wait_seconds": 33000},
                    },
                    "holdout_rows": [{"session_cap": True}, {"session_cap": False}],
                },
            },
        }
        out = build_leaderboard(report)
        self.assertEqual(out["totals"]["total_keys"], 2)
        self.assertEqual(out["totals"]["v21_completed"], 1)
        self.assertEqual(out["rows"][0]["winner_status"], "pending_matched_comparison")
        self.assertEqual(out["rows"][0]["v21_session_cap_count"], 1)
        self.assertEqual(out["rows"][1]["winner_status"], "provisional_v19")


if __name__ == "__main__":
    unittest.main()
