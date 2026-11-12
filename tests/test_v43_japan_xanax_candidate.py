"""Causal V8 checkpoint candidate tests; not performance validation."""
import unittest
from unittest.mock import patch,Mock
from research.japan_xanax import v8_regime_candidate as m

NOW=1800000000


class JapanXanaxCandidateTests(unittest.TestCase):
    def test_non_japan_rejected_before_source_access(self):
        with patch.object(m,"inspect_live_source") as inspection:
            x=m.predict("/does/not/exist","can","Xanax",NOW)
        self.assertEqual(x["status"],"NOT_APPROVED_JAPAN_XANAX")
        inspection.assert_not_called()

    def test_stale_source_fails_closed(self):
        with patch.object(m,"inspect_live_source",
                          return_value={"status":"COLLECTOR_STALE_OR_NO_HEARTBEAT"}):
            x=m.predict("/does/not/exist","jap","Xanax",NOW)
        self.assertEqual(x["status"],"COLLECTOR_STALE_OR_NO_HEARTBEAT")

    def test_training_rejects_all_unresolved_target_labels(self):
        # A tempting unresolved record must never enter Ridge training.
        records=[{"window_index":n,
                  "decision_anchor":NOW-60000+n*100,
                  "target_end":NOW+1000,
                  "target_start":NOW+2000} for n in range(120)]
        with patch.object(m,"reconstructed_state",return_value=m.np.ones(12)):
            result=m.fit_rolling_ridge(records,[None]*130,129,NOW)
        self.assertIsNone(result)

    def test_deployment_contract_and_dont_fabricate_probability(self):
        idx=100
        observed=[{"start":NOW-20000+i*500,
                   "end":NOW-19800+i*500} for i in range(idx)]
        adjusted=[{"start":x["start"],"end":x["end"],
                   "width":200} for x in observed]
        now=observed[-1]["end"]+10
        with patch.object(m.v7,"strict_rows",return_value=[]), \
             patch.object(m.v7,"base_prediction",return_value=now+m.TRAVEL+600), \
             patch.object(m.v7,"cooldown_history",return_value=[7200]*30), \
             patch.object(m,"regime_ratio",return_value=1.0):
            result=m.estimate(observed,adjusted,now)
        self.assertEqual(result["status"],"RESEARCH_PROPOSAL_ONLY")
        self.assertEqual(result["recommended_departure_timestamp"],now+600)
        self.assertFalse(result["probability_calibrated"])
        self.assertEqual(result["replan_step_seconds"],300)
        self.assertEqual(result["quantity_threshold"],30)
        self.assertEqual(result["grace_seconds"],10)

    def test_late_departures_are_abstentions(self):
        observed=[{"start":NOW-500,"end":NOW-300}]
        adjusted=[{"start":NOW-500,"end":NOW-300,"width":200}]
        with patch.object(m.v7,"strict_rows",return_value=[]), \
             patch.object(m.v7,"base_prediction",return_value=NOW+60), \
             patch.object(m.v7,"cooldown_history",return_value=[7200]), \
             patch.object(m,"regime_ratio",return_value=None):
            result=m.estimate(observed,adjusted,NOW)
        self.assertEqual(result["status"],"DEPARTURE_PASSED")

    def test_regime_adapts_only_after_resolved_ridge(self):
        idx=80
        observed=[{"start":NOW-20000+i*150,"end":NOW-19900+i*150}
                  for i in range(idx)]
        adjusted=[{"start":x["start"],"end":x["end"],
                   "width":100} for x in observed]
        now=observed[-1]["end"]+20
        with patch.object(m.v7,"strict_rows",return_value=[]), \
             patch.object(m.v7,"base_prediction",return_value=now+m.TRAVEL+900), \
             patch.object(m.v7,"cooldown_history",return_value=[7200]*30), \
             patch.object(m,"regime_ratio",return_value=.75), \
             patch.object(m,"fit_rolling_ridge",
                          return_value=now+m.TRAVEL+600):
            x=m.estimate(observed,adjusted,now)
        self.assertEqual(x["model_config"],"V8_rolling_ridge_alpha3_regime")
        self.assertEqual(x["recommended_departure_timestamp"],now+600)


if __name__=="__main__":
    unittest.main()
