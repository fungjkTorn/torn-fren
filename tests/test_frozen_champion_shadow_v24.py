"""No-live-side-effects tests for frozen champion replay orchestration."""
import unittest
from services.frozen_champion_shadow_v24 import (
    _match,_resolve_config,_champion_entries,OLD_NATIVE
)

class FrozenReplayTests(unittest.TestCase):
    def test_same_start_pairing(self):
        x={"versions":{
            "v19":{"rows":[{"start":10,"success":True},{"start":20,"success":False}]},
            "v21":{"rows":[{"start":10,"success":False},{"start":20,"success":True},{"start":30,"success":True}]}
        }}
        r=_match(x)
        self.assertEqual(r["common_starts"],2)
        self.assertEqual(r["versions"]["v19"],{"hits":1,"paired_n":2})
        self.assertEqual(r["versions"]["v21"],{"hits":1,"paired_n":2})

    def test_frozen_config_not_selected_afresh(self):
        entry={"key":"arg:Tear Gas","provisional_model":"v19"}
        models={"v19":{"results":{"arg:Tear Gas":{
            "status":"complete","selected_on_training":{"config":{"name":"dyn3"}}}
        }}}
        ver,cfg,item=_resolve_config(entry,models)
        self.assertEqual(ver,"v19")
        self.assertEqual(cfg["name"],"dyn3")

    def test_only_valid_champions(self):
        self.assertIsNone(_resolve_config({"key":"jap:Xanax","provisional_model":"specialist"},{}))
        self.assertIn("v20",OLD_NATIVE)
        self.assertEqual(len(_champion_entries({"entries":[{"key":"arg:Tear Gas"}]})),1)

if __name__=="__main__":
    unittest.main()
