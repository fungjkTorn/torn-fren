"""Strict research-only freeze/approval checks for Canada and UK Xanax."""
from dataclasses import asdict
import json
import unittest
from unittest.mock import Mock, patch

from research import v42_xanax_candidate_tick as candidate
from services.plushie_flower_dynamic_planner_v18 import configs


class FrozenXanaxTests(unittest.TestCase):
    def test_two_frozen_candidates_match_original_config_sources(self):
        self.assertEqual(candidate.ALLOWED, {"can:Xanax": "dyn8", "uni:Xanax": "dyn3"})
        master = json.loads(candidate.MASTER.read_text(encoding="utf-8"))
        self.assertEqual(set(master["results"]), set(candidate.ALLOWED))
        self.assertTrue(candidate.approved_source())
        existing = {c.name: asdict(c) for c in configs()}
        for key, name in candidate.ALLOWED.items():
            self.assertEqual(master["results"][key]["selected_on_training"]["config"], existing[name])

    def test_japan_is_explicitly_not_generic(self):
        with patch.object(candidate, "frozen_single_tick") as task:
            result = candidate.predict("/unused", "jap", "Xanax", 1800000000)
        self.assertEqual(result["status"], "NOT_APPROVED_FROZEN_XANAX_CANDIDATE")
        task.assert_not_called()

    def test_original_versioned_engine_called_without_mutating_horizon(self):
        now = 1800000000
        result = {
            "status":"RESEARCH_PROPOSAL_ONLY","model_generation":"v19",
            "model_config":"dyn8","replan_step_seconds":300,
            "research_horizon_seconds":21600,"quantity_threshold":30,
            "grace_seconds":10,"probability_calibrated":False,
            "recommended_departure_timestamp":now+600,
            "recommended_arrival_timestamp":now+600+1620,
        }
        with patch.object(candidate, "frozen_single_tick", return_value=result.copy()) as worker:
            answer = candidate.predict("/unused", "can", "Xanax", now)
        worker.assert_called_once_with("/unused",candidate.MASTER,"v19","can","Xanax",now)
        self.assertEqual(answer["status"],"RESEARCH_PROPOSAL_ONLY")
        self.assertEqual(answer["research_horizon_seconds"],21600)

    def test_invalid_output_cannot_claim_actionable(self):
        for bad in [
            {"model_config":"dyn1"}, {"grace_seconds":30},
            {"research_horizon_seconds":28800}, {"probability_calibrated":True},
        ]:
            result = {
                "status":"RESEARCH_PROPOSAL_ONLY","model_generation":"v19",
                "model_config":"dyn3","replan_step_seconds":300,
                "research_horizon_seconds":21600,"quantity_threshold":30,
                "grace_seconds":10,"probability_calibrated":False,
            }
            result.update(bad)
            with patch.object(candidate, "frozen_single_tick", return_value=result):
                response = candidate.predict("/unused","uni","Xanax",1800000000)
            self.assertEqual(response["status"],"FROZEN_XANAX_OUTPUT_MISMATCH")

    def test_frozen_master_tamper_fails_closed(self):
        with patch.object(candidate,"approved_source",return_value=False), \
             patch.object(candidate,"frozen_single_tick") as worker:
            result=candidate.predict("/unused","can","Xanax",1800000000)
        self.assertEqual(result["status"],"FROZEN_XANAX_CONFIG_MISMATCH")
        worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
