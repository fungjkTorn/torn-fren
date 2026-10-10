"""V52 requires reviewed digest and never publishes research candidate."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

import numpy as np

from research import v52_pair_trained_tick as m


NOW=1800000000

def artifact(target,positive=True):
    cfg=m.TARGETS[target]
    names=m.FEATURES[target]
    return {
        "schema":m.SCHEMA,
        "research_only":True,
        "approved_for_live":False,
        "target":target,"key":cfg["key"],
        "feature_names":list(names),
        "imputation_medians":[0.0]*len(names),
        "expert_a":list(cfg["expert_a"]),
        "expert_b":list(cfg["expert_b"]),
        "winning_selector":cfg["selector"],
        "train_asof":NOW-10000,
        "model":{"family":"logistic",
                 "coef":[0.0]*len(names),
                 "intercept":10.0 if positive else -10.0},
    }

def save(folder,target,positive=True):
    path=Path(folder)/("artifact_"+target+".json")
    path.write_text(json.dumps(artifact(target,positive),
                    sort_keys=True,separators=(",",":"))+"\n")
    return path,hashlib.sha256(path.read_bytes().strip()).hexdigest()


class TrainedPairTests(unittest.TestCase):
    def test_wrong_sha_denied_before_source_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,digest=save(tmp,"lion")
            with patch.object(m,"inspect_live_source") as inspect:
                with self.assertRaisesRegex(ValueError,"ARTIFACT_HASH_MISMATCH"):
                    m.predict("/no/db","lion",NOW,path,"0"*64)
                inspect.assert_not_called()

    def test_bad_target_fails_before_file_read(self):
        with self.assertRaisesRegex(ValueError,"unsupported"):
            m.predict("/no/db","monkey",NOW,"/no/artifact","0"*64)

    def test_bad_artifact_contract_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,digest=save(tmp,"panda")
            a=artifact("panda")
            a["approved_for_live"]=True
            path.write_text(json.dumps(a)+"\n")
            digest=hashlib.sha256(path.read_bytes().strip()).hexdigest()
            with self.assertRaisesRegex(ValueError,"CONTRACT"):
                m.load_pinned_artifact(path,digest,"panda")

    def test_stale_source_doesnt_build_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,digest=save(tmp,"lion")
            build=Mock()
            r=m.predict("/no/db","lion",NOW,path,digest,
                source_checker=lambda *a:{"status":"COLLECTOR_STALE"},
                context_builder=build)
            self.assertEqual(r["status"],"COLLECTOR_STALE")
            build.assert_not_called()

    def test_research_selection_chooses_but_never_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,digest=save(tmp,"lion",positive=True)
            con=Mock()
            ctx=SimpleNamespace(grid=np.array([NOW],float),con=con)
            class Planner:
                def __init__(self,ctx,country,item,*,k,global_weight,cutoff):
                    self.k=k
                def plan(self,q):
                    return (q+(1200 if self.k==18 else 600),.5,.5)
            features={x:0.0 for x in m.FEATURES["lion"]}
            with patch.object(m,"original_features",return_value=features):
                r=m.predict("/no/db","lion",NOW,path,digest,
                    source_checker=lambda *a:{"status":"FRESH"},
                    context_builder=lambda *a,**kw:ctx,
                    planner_class=Planner)
            self.assertEqual(r["status"],"RESEARCH_NOT_ADMITTED_CANDIDATE")
            self.assertEqual(r["selected_expert"],"b")
            self.assertEqual(r["candidate_status"],"BOUNDED_EXPERIMENTAL_TIMING")
            self.assertEqual(r["research_departure_timestamp"],NOW+1200)
            self.assertEqual(r["research_arrival_timestamp"],NOW+1200+11820)
            self.assertFalse(r["published_to_website"])
            self.assertTrue(r["research_only"])
            con.close.assert_called_once()

    def test_selected_expert_no_schedule_abstains(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,digest=save(tmp,"lion",positive=False)
            con=Mock()
            ctx=SimpleNamespace(grid=np.array([NOW],float),con=con)
            class Planner:
                def __init__(self,ctx,country,item,*,k,global_weight,cutoff):
                    self.k=k
                def plan(self,q):
                    return None if self.k==14 else (q+1200,.5,.5)
            features={x:0.0 for x in m.FEATURES["lion"]}
            with patch.object(m,"original_features",return_value=features):
                r=m.predict("/no/db","lion",NOW,path,digest,
                    source_checker=lambda *a:{"status":"FRESH"},
                    context_builder=lambda *a,**kw:ctx,
                    planner_class=Planner)
            self.assertEqual(r["candidate_status"],"SELECTED_EXPERT_ABSTAINED")
            self.assertNotIn("research_departure_timestamp",r)


if __name__=="__main__":
    unittest.main()
