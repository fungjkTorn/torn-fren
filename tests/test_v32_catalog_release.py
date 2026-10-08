import json
import unittest
from pathlib import Path
from research.v32_catalog_release_report import audit_catalog

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"research"/"all_236_champions_v26.json"

class CatalogReleaseTests(unittest.TestCase):
    def test_empty_forward_evidence_stays_unknown_not_false_zero(self):
        data=audit_catalog(json.loads(REGISTRY.read_text()),None)
        self.assertEqual(data["item_count"],236)
        self.assertEqual(len(data["rows"]),236)
        self.assertEqual(data["has_prospective_evidence"],0)
        self.assertEqual(data["publicly_promoted"],0)
        self.assertTrue(all(x["live_status"]=="RESEARCH_ONLY_BLOCKED" for x in data["rows"]))
        self.assertTrue(all(x["prospective_all_start_rate"] is None for x in data["rows"]))

    def test_even_high_small_sample_cannot_promote(self):
        reg=json.loads(REGISTRY.read_text())
        res={"schema":"torn-fren-v32-prospective-single-tick-audit-v1",
             "items":{"uae:Camel Plushie":{
                 "resolved_eligible_sessions":8,
                 "successful_arrivals":8,
                 "all_start_success":1.0,
                 "coverage":1.0,
                 "qualified_independent_windows":2}}}
        result=audit_catalog(reg,res)
        camel=next(x for x in result["rows"] if x["item_key"]=="uae:Camel Plushie")
        self.assertEqual(camel["prospective_all_start_rate"],1.0)
        self.assertIn("FEWER_THAN_30_PROSPECTIVE_STARTS",camel["blockers"])
        self.assertIn("INDEPENDENT_WINDOWS_NOT_CERTIFIED",camel["blockers"])
        self.assertEqual(camel["live_status"],"RESEARCH_ONLY_BLOCKED")

    def test_wrong_registry_and_fake_forward_schema_rejected(self):
        reg=json.loads(REGISTRY.read_text())
        with self.assertRaises(ValueError):
            audit_catalog(reg,{"schema":"historical_research_not_forward","items":{}})
        reg["items"].pop(next(iter(reg["items"])))
        with self.assertRaises(ValueError):
            audit_catalog(reg,None)

if __name__=="__main__":
    unittest.main()
