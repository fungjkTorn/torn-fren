import json
import unittest
from pathlib import Path
from research.v26_merge_champion_registry import merge_registry


ROOT = Path(__file__).resolve().parents[1]


class V26RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plushies = json.loads(
            (ROOT / "research" / "plushie_flower_champions_v26.json").read_text()
        )
        cls.keys = [x["item_key"] for x in cls.plushies["items"]]
        # A test-only synthetic catalog to verify complete override/retention behavior.
        cls.prior = [
            {"item_key": key, "category": "plushie" if "Plushie" in key else "flower",
             "old_provisional_family": "v19", "old_provisional_config": "dyn2",
             "old_matched_success_rate": "0.8", "old_matched_hits": "80",
             "old_matched_n": "100"}
            for key in cls.keys
        ] + [
            {"item_key": f"other:{i}", "category": "other",
             "old_provisional_family": "v21", "old_provisional_config": "dyn1",
             "old_matched_success_rate": "", "old_matched_hits": "",
             "old_matched_n": ""}
            for i in range(214)
        ] + [
            {"item_key": "jap:Xanax", "category": "other",
             "old_provisional_family": "japan_xanax_specialist",
             "old_provisional_config": "", "old_matched_success_rate": "",
             "old_matched_hits": "", "old_matched_n": ""}
        ]

    def test_handoff_has_21_with_18_development_over_90(self):
        data = self.plushies
        self.assertEqual(len(self.keys), 21)
        self.assertEqual(len(set(self.keys)), 21)
        self.assertEqual(sum(x["development_success_rate"] >= .9 for x in data["items"]), 18)
        self.assertEqual(sum(x["source_verified"] is False for x in data["items"]), 7)
        self.assertTrue(all(x["promotion_status"] == "RESEARCH_ONLY_BLOCKED" for x in data["items"]))

    def test_merging_all_236_preserves_japan_xanax(self):
        merged = merge_registry(self.prior, self.plushies, {"v19":{}, "v20":{}, "v21":{}})
        self.assertEqual(len(merged["items"]), 236)
        self.assertEqual(sum("replaces_old_all_item_candidate_for_research" in x for x in merged["items"].values()), 21)
        self.assertEqual(merged["items"]["jap:Xanax"]["candidate"]["model_family"], "japan_xanax_specialist")
        self.assertTrue(all(x["promotion_status"] == "RESEARCH_ONLY_BLOCKED" for x in merged["items"].values()))

    def test_preserves_old_provisional_after_override(self):
        merged = merge_registry(self.prior, self.plushies, {"v19":{}, "v20":{}, "v21":{}})
        item = merged["items"]["uni:Nessie Plushie"]
        self.assertEqual(item["historical_all_item_selection"]["config"], "dyn2")
        self.assertEqual(item["candidate"]["model_family"], "recent_phase_template")
        self.assertFalse(item["candidate"]["source_verified"])

    def test_rejects_mutated_promoted_handoff(self):
        p=json.loads(json.dumps(self.plushies))
        p["items"][0]["promotion_status"] = "LIVE"
        with self.assertRaisesRegex(ValueError, "pre-promoted"):
            merge_registry(self.prior,p,{"v19":{}, "v20":{}, "v21":{}})

    def test_rejects_duplicate_catalog_keys(self):
        p=json.loads(json.dumps(self.prior))
        p[-1]["item_key"]=p[0]["item_key"]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            merge_registry(p,self.plushies,{"v19":{}, "v20":{}, "v21":{}})

    def test_rejects_unsupported_handoff_catalog(self):
        p=json.loads(json.dumps(self.plushies))
        p["items"][0]["item_key"]="badcountry:Imaginary"
        with self.assertRaisesRegex(ValueError,"missing from catalog"):
            merge_registry(self.prior,p,{"v19":{}, "v20":{}, "v21":{}})

    def test_frozen_generic_config_hashed(self):
        fake={"results":{"mex:Dahlia":{"status":"complete", "selected_on_training":{"config":{"name":"dyn9", "k":10}}}}}
        merged=merge_registry(self.prior,self.plushies,{"v19":fake, "v20":{}, "v21":{}})
        value=merged["items"]["mex:Dahlia"]["frozen_generic_candidates"]["v19"]
        self.assertEqual(value["config"]["name"],"dyn9")
        self.assertEqual(len(value["sha256"]),64)

    def test_all_plushie_candidates_full_coverage(self):
        self.assertTrue(all(x["development_coverage"] == 1 for x in self.plushies["items"]))
        self.assertTrue(all(x["max_wait_seconds"] == 28800 for x in self.plushies["items"]))
        self.assertTrue(all(x["replan_seconds"] == 300 for x in self.plushies["items"]))


if __name__=="__main__":
    unittest.main()
