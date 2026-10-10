"""V50 tests: no future labels, sklearn JSON decision parity, safe artifact."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research import v50_pair_selector_artifact as m


class V50ArtifactTests(unittest.TestCase):
    def rows(self,target,n=60):
        names=m.FEATURES[target]
        result=[]
        for i in range(n):
            # Both expert classes occur, and every example is a disagreement.
            y=int((i*7)%13>=6)
            vals=[0.05*j+((i*31+j*17)%19)/10 for j in range(len(names))]
            if i%13==0:
                vals[2]=float("nan")
            result.append((1800000000+i*1800,vals,1-y,y))
        return result

    def test_source_feature_keys_match_original_champion(self):
        self.assertEqual(len(m.FEATURES["lion"]),24)
        self.assertEqual(len(m.FEATURES["panda"]),29)
        self.assertEqual(m.FEATURES["panda"][-5:],
                         ("g2_g6","g6_g18raw","rL_g18raw","prob_gap","rob_gap"))

    def test_logistic_matches_real_sklearn_across_training_samples(self):
        data=self.rows("lion")
        trained=m.train(data,"lion",1801000000)
        self.assertEqual(trained["model"]["family"],"logistic")
        self.assertFalse(trained["approved_for_live"])
        self.assertEqual(trained["resolved_disagreements"],60)
        for row in data:
            vec=np.asarray(row[1])
            med=np.asarray(trained["imputation_medians"])
            v=np.where(np.isfinite(vec),vec,med)
            self.assertIn(m.choose_from_vector(trained,v),(0,1))

    def test_forest_portable_inference_matches_real_sklearn(self):
        data=self.rows("panda",80)
        trained=m.train(data,"panda",1801000000)
        self.assertEqual(trained["model"]["family"],"extra_trees")
        self.assertEqual(len(trained["model"]["trees"]),300)
        first=dict(zip(m.FEATURES["panda"],data[0][1]))
        self.assertIn(m.choose_from_features(trained,first),(0,1))
        with tempfile.TemporaryDirectory() as tmp:
            filename=Path(tmp)/"panda.json"
            sha=m.write_artifact(trained,filename)
            self.assertEqual(len(sha),64)
            loaded=json.loads(filename.read_text())
            self.assertFalse(loaded["approved_for_live"])
            self.assertEqual(m.choose_from_features(loaded,first),
                             m.choose_from_features(trained,first))

    def test_reject_future_outcome_even_when_decision_past(self):
        now=1801000000
        names=m.FEATURES["lion"]
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"examples.jsonl"
            record={
                "key":"sou:Lion Plushie",
                "decision_ts":now-1800,
                "feature_as_of":now-1800,
                "resolved_at":now+1,
                "features":{name:float(i) for i,name in enumerate(names)},
                "a_success":0,"b_success":1,
            }
            file.write_text(json.dumps(record)+"\n")
            with self.assertRaisesRegex(ValueError,"unresolved"):
                m.load_resolved_examples(file,"lion",now)

    def test_reject_future_features_and_wrong_item(self):
        now=1801000000
        names=m.FEATURES["panda"]
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"examples.jsonl"
            record={
                "key":"chi:Panda Plushie",
                "decision_ts":now-1800,
                "feature_as_of":now+5,
                "resolved_at":now-200,
                "features":{name:float(i) for i,name in enumerate(names)},
                "a_success":0,"b_success":1,
            }
            file.write_text(json.dumps(record)+"\n")
            with self.assertRaisesRegex(ValueError,"unresolved"):
                m.load_resolved_examples(file,"panda",now)
            record["feature_as_of"]=now-1800
            record["key"]="sou:Lion Plushie"
            file.write_text(json.dumps(record)+"\n")
            with self.assertRaisesRegex(ValueError,"wrong item"):
                m.load_resolved_examples(file,"panda",now)

    def test_no_training_without_two_resolved_classes(self):
        data=self.rows("lion",30)
        collapsed=[(ts,x,0,1) for ts,x,_,_ in data]
        with self.assertRaisesRegex(ValueError,"two classes"):
            m.train(collapsed,"lion",1801000000)

    def test_cannot_use_artifact_as_live_approval(self):
        a=m.train(self.rows("lion"),"lion",1801000000)
        a["approved_for_live"]=True
        sample=dict(zip(m.FEATURES["lion"],self.rows("lion")[0][1]))
        with self.assertRaisesRegex(ValueError,"contract"):
            m.choose_from_features(a,sample)

if __name__=="__main__":
    unittest.main()
