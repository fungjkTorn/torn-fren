import unittest
from research.v25_release_gate import assess


def evidence():
    return dict(
        frozen_model_id="jap:Xanax-v8-research",
        item_key="jap:Xanax",
        raw_config_sha256="frozen-full-config-sha256",
        read_only_shadow=True,
        baseline_fallback_tested=True,
        freshness_and_gap_checks_tested=True,
        uses_japan_xanax_specialist=True,
        specialist_live_departure_adapter_tested=True,
        publishes_probability=False,
        same_source_db_verified=True,
        native_replay_parity_passed=True,
        causal_prefix_invariance_passed=True,
        prospective_after_model_freeze=True,
        independent_starts=45,
        distinct_resolved_qualified_windows=10,
        all_start_success=.92,
        coverage=.98,
        feature_flag_default_off=True,
        rollback_smoke_tested=True,
    )


class ReleaseGateTests(unittest.TestCase):
    def test_missing_evidence_never_promotes(self):
        self.assertFalse(assess({})["ready"])
        self.assertGreater(len(assess({})["blockers"]), 8)

    def test_prospectively_valid_candidate(self):
        self.assertTrue(assess(evidence())["ready"])

    def test_private_shadow_still_requires_specialist_adapter(self):
        x = evidence()
        x["specialist_live_departure_adapter_tested"] = False
        self.assertFalse(assess(x, "experimental_private_shadow")["ready"])

    def test_uncalibrated_trip_probability_not_allowed(self):
        x = evidence()
        x["publishes_probability"] = True
        self.assertFalse(assess(x)["ready"])
        x["probabilities_independently_calibrated"] = True
        self.assertTrue(assess(x)["ready"])

    def test_session_counts_cannot_replace_independent_events(self):
        x = evidence()
        x["distinct_resolved_qualified_windows"] = 2
        self.assertFalse(assess(x)["ready"])

    def test_marginal_arrival_success_requires_more_research(self):
        x = evidence()
        x["all_start_success"] = .79
        self.assertFalse(assess(x)["ready"])

    def test_private_experiment_not_public_promotion(self):
        x = evidence()
        x["prospective_after_model_freeze"] = False
        self.assertTrue(assess(x, "experimental_private_shadow")["ready"])
        self.assertFalse(assess(x, "public_live_guidance")["ready"])

    def test_item_specific_missing_script_blocks_private_shadow(self):
        x = evidence()
        x["uses_item_specific_specialist"] = True
        x["specialist_source_present_and_importable"] = False
        x["item_specific_departure_adapter_tested"] = True
        self.assertFalse(assess(x, "experimental_private_shadow")["ready"])

    def test_item_specific_missing_adapter_blocks_public(self):
        x = evidence()
        x["uses_item_specific_specialist"] = True
        x["specialist_source_present_and_importable"] = True
        x["item_specific_departure_adapter_tested"] = False
        self.assertFalse(assess(x, "public_live_guidance")["ready"])

    def test_unlisted_item_cannot_lower_below_ninety(self):
        x = evidence()
        x["item_key"] = "can:Fire Hydrant"
        x["required_arrival_success"] = .75
        x["all_start_success"] = .8
        self.assertFalse(assess(x)["ready"])

    def test_three_far_plushies_can_use_temporary_floor_with_caution(self):
        for key in ("arg:Monkey Plushie", "swi:Chamois Plushie", "uae:Camel Plushie"):
            x = evidence()
            x["item_key"] = key
            x["required_arrival_success"] = .75
            x["all_start_success"] = .77
            x["temporary_low_reliability_caution_visible"] = True
            self.assertTrue(assess(x)["ready"])
            x["temporary_low_reliability_caution_visible"] = False
            self.assertFalse(assess(x)["ready"])

    def test_cross_snapshot_parity_never_promotes(self):
        x = evidence()
        x["same_source_db_verified"] = False
        self.assertFalse(assess(x)["ready"])
        self.assertTrue(any("same source DB" in b for b in assess(x)["blockers"]))

    def test_lookahead_detection_blocks_promotion(self):
        x = evidence()
        x["causal_prefix_invariance_passed"] = False
        self.assertFalse(assess(x)["ready"])
        self.assertTrue(any("future data" in p for p in assess(x)["blockers"]))

    def test_unknown_release_target_rejected(self):
        with self.assertRaises(ValueError):
            assess({}, "merge_immediately")


if __name__ == "__main__":
    unittest.main()
