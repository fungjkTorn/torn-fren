"""V51 Japan V8 checkpoint gate: no future windows, no false parity."""
import unittest
from unittest.mock import patch
from pathlib import Path

from research.japan_xanax import v51_retro_parity as m


class JapanV51ParityTests(unittest.TestCase):
    def example(self):
        # Five P2 windows, window index 2 evaluates target index 4.
        obs=[{"start":1000+i*9000,"end":2000+i*9000}
             for i in range(5)]
        adj=[{"start":w["start"],"end":w["end"],
              "width":1000} for w in obs]
        return obs,adj

    def test_v8_forecast_receives_only_causal_prefix(self):
        obs,adj=self.example()
        row={"window_index":2}
        gt={"window_index":2,"decision_anchor":obs[2]["end"],
            "target_start":obs[4]["start"],"target_end":obs[4]["end"]}
        lengths=[]
        def estimate(short_o,short_a,now):
            lengths.append((len(short_o),len(short_a),now))
            return {"status":"RESEARCH_PROPOSAL_ONLY",
                    "model_config":"V7_ordinary_regime",
                    "recommended_arrival_timestamp":obs[4]["start"]}
        with patch.object(m.v7,"strict_rows",return_value=[row]), \
             patch.object(m.v7,"adjusted_sample",return_value=gt), \
             patch.object(m.v7,"predictions",return_value=[obs[4]["start"]]), \
             patch.object(m.v8,"estimate",side_effect=estimate):
            result=m.audit_reconstructed(obs,adj,cutoff=obs[1]["end"])
        self.assertEqual(lengths,[(3,3,obs[2]["end"])])
        self.assertEqual(result["opportunities"],1)
        self.assertEqual(result["v7_exact"]["hits"],1)
        self.assertEqual(result["v8_exact"]["hits"],1)

    def test_v8_abstention_not_counted_as_false_success(self):
        obs,adj=self.example()
        row={"window_index":2}
        gt={"window_index":2,"decision_anchor":obs[2]["end"],
            "target_start":obs[4]["start"],"target_end":obs[4]["end"]}
        with patch.object(m.v7,"strict_rows",return_value=[row]), \
             patch.object(m.v7,"adjusted_sample",return_value=gt), \
             patch.object(m.v7,"predictions",return_value=[obs[4]["start"]]), \
             patch.object(m.v8,"estimate",return_value={
                 "status":"DEPARTURE_PASSED",
                 "model_config":"V7_ordinary_regime"}):
            result=m.audit_reconstructed(obs,adj,cutoff=obs[1]["end"])
        self.assertEqual(result["v8_exact"]["hits"],0)
        self.assertEqual(result["v8_exact"]["n"],0)
        self.assertEqual(result["v8_exact"]["coverage"],0.0)

    def test_reference_hash_gate_denies_deployment(self):
        obs,adj=self.example()
        dummy={
            "opportunities":21,
            "v7_exact":{"hits":7,"n":21},
            "v8_exact":{"hits":13,"n":21},
        }
        with patch.object(m,"file_sha256",return_value="other"), \
             patch.object(m,"_install_frozen_readonly_history"), \
             patch.object(m.hs,"_get_all_item_rows_with_source",
                          return_value=[None]*8609), \
             patch.object(m.v7,"build_adjusted",return_value=(obs,adj)), \
             patch.object(m,"audit_reconstructed",return_value=dummy):
            out=m.report(__file__)
        self.assertEqual(out["status"],"REFERENCE_SNAPSHOT_NOT_VERIFIED")
        self.assertFalse(out["deploy_approved"])
        self.assertFalse(out["matches_checkpoint_source_hash"])

    def test_identical_hash_cannot_mask_failed_v7_reproduction(self):
        obs,adj=self.example()
        dummy={
            "opportunities":21,
            "v7_exact":{"hits":6,"n":21},
            "v8_exact":{"hits":13,"n":21},
        }
        with patch.object(m,"file_sha256",return_value=m.REFERENCE_SHA256), \
             patch.object(m,"_install_frozen_readonly_history"), \
             patch.object(m.hs,"_get_all_item_rows_with_source",
                          return_value=[None]*8609), \
             patch.object(m.v7,"build_adjusted",return_value=(obs,adj)), \
             patch.object(m,"audit_reconstructed",return_value=dummy):
            out=m.report(__file__)
        self.assertEqual(out["status"],"V7_BASELINE_PARITY_FAILED")
        self.assertFalse(out["deploy_approved"])

    def test_verification_does_not_promote_new_v8_by_itself(self):
        obs,adj=self.example()
        dummy={
            "opportunities":21,
            "v7_exact":{"hits":7,"n":21},
            "v8_exact":{"hits":13,"n":21},
        }
        with patch.object(m,"file_sha256",return_value=m.REFERENCE_SHA256), \
             patch.object(m,"_install_frozen_readonly_history"), \
             patch.object(m.hs,"_get_all_item_rows_with_source",
                          return_value=[None]*8609), \
             patch.object(m.v7,"build_adjusted",return_value=(obs,adj)), \
             patch.object(m,"audit_reconstructed",return_value=dummy):
            out=m.report(__file__)
        self.assertEqual(out["status"],"HISTORICAL_V8_RATE_PARITY_OBSERVED")
        self.assertFalse(out["deploy_approved"])
        self.assertEqual(out["development_v8_exact"],"13/21")


if __name__=="__main__":
    unittest.main()
