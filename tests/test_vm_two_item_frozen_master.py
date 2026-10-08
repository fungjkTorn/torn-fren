"""Frozen two-item V21 private canary must match the research registry."""
import json
import unittest
from pathlib import Path
from dataclasses import fields

from services.plushie_flower_dynamic_planner_v19 import Config

ROOT=Path(__file__).resolve().parents[1]
MASTER=ROOT/"research"/"v21_canary_two_items_frozen.json"
REGISTRY=ROOT/"research"/"all_236_champions_v26.json"

class TwoItemFrozenMasterTests(unittest.TestCase):
    def test_source_identity_and_safe_scope(self):
        m=json.loads(MASTER.read_text())
        self.assertEqual(m["source_master_sha256"],
          "dadf6fbcb6c6b5f68ed39871bae7185a1e23e773948ffffacabc8aaeca7362f7")
        self.assertEqual(set(m["results"]),{"can:Fire Hydrant","can:Bear Gall"})
        self.assertEqual((m["settings"]["options"]["max_wait"],
                          m["settings"]["options"]["replan_step"],
                          m["settings"]["options"]["departure_grid"]),(43200,900,900))
        self.assertNotIn("holdout_rows",MASTER.read_text())
        self.assertNotIn("api_key",MASTER.read_text().lower())

    def test_frozen_policy_names_equal_private_registry(self):
        master=json.loads(MASTER.read_text())
        registry=json.loads(REGISTRY.read_text())
        for key,v in master["results"].items():
            with self.subTest(item=key):
                cfg=v["selected_on_training"]["config"]
                self.assertEqual(set(cfg),{f.name for f in fields(Config)})
                self.assertEqual(v["status"],"complete")
                self.assertEqual(cfg["name"],
                   registry["items"][key]["current_provisional_candidate"]["config_name"])
                self.assertEqual(
                   registry["items"][key]["current_provisional_candidate"]["model_family"],"v21")

if __name__=="__main__":unittest.main()
