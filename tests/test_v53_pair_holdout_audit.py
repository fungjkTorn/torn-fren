"""V53 chronological holdout prevents training-label leaks and selection bias."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v53_pair_holdout_audit as m
from research.v50_pair_selector_artifact import FEATURES

BASE=1800000000
STEP=1800

def record(i,target="lion",*,resolved_offset=600):
    ts=BASE+i*STEP
    # Explicitly both expert disagreement classes appear on train;
    # holdout includes agreements, so evaluation is not biased to disputes.
    if i%4==0:
        a,b=1,1
    elif i%4==1:
        a,b=0,0
    elif i%4==2:
        a,b=0,1
    else:
        a,b=1,0
    names=FEATURES[target]
    return {
        "key":"sou:Lion Plushie" if target=="lion" else "chi:Panda Plushie",
        "decision_ts":ts,
        "feature_as_of":ts,
        "resolved_at":ts+resolved_offset,
        "features":{name:(None if k==7 and i%10==0 else
                          round(.1*k+((i*17+k*13)%19)/10,5))
                    for k,name in enumerate(names)},
        "a_success":a,"b_success":b,
        "source":"SOURCE_PINNED_CAUSAL_ANALOG_EXPERTS",
        "normalization":"per_decision_cutoff",
        "research_only":True,
    }

def save(path,n=110,target="lion"):
    with Path(path).open("w") as f:
        for i in range(n):
            f.write(json.dumps(record(i,target))+"\n")


class V53HoldoutTests(unittest.TestCase):
    def test_split_uses_resolved_training_labels_not_just_decisions(self):
        r=[record(0),record(1,resolved_offset=100000),
           record(2),record(3)]
        early,hold=m.split_chronological(r,BASE+STEP,BASE+10*STEP,0)
        self.assertEqual(len(early),1)
        self.assertEqual([x["decision_ts"] for x in hold],
                         [BASE+2*STEP,BASE+3*STEP])

    def test_every_holdout_row_is_evaluated_not_disagreements_only(self):
        sample=[record(i) for i in range(4)]
        for r in sample:r["a_success"]=int(r["a_success"])
        score=m.rates([0,1,1,0],sample)
        self.assertEqual(score["n"],4)
        self.assertEqual(score["expert_disagreements"],2)
        self.assertEqual(score["selector"]["hits"],3)
        self.assertEqual(score["expert_a"]["hits"],2)
        self.assertEqual(score["expert_b"]["hits"],2)
        self.assertEqual(score["oracle_ceiling_not_reachable"]["hits"],3)

    def test_reject_unverified_source_and_feature_lookahead(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cases.jsonl"
            bad=record(0);bad["feature_as_of"]=bad["decision_ts"]+1
            path.write_text(json.dumps(bad)+"\n")
            with self.assertRaisesRegex(ValueError,"future features"):
                m.read_examples(path,"lion")
            bad=record(0);bad["source"]="GUESS"
            path.write_text(json.dumps(bad)+"\n")
            with self.assertRaisesRegex(ValueError,"non-causal"):
                m.read_examples(path,"lion")
            bad=record(0);bad["a_success"]=True
            path.write_text(json.dumps(bad)+"\n")
            with self.assertRaisesRegex(ValueError,"binary"):
                m.read_examples(path,"lion")

    def test_duplicate_anchor_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"cases.jsonl"
            row=record(0)
            path.write_text(json.dumps(row)+"\n"+json.dumps(row)+"\n")
            with self.assertRaisesRegex(ValueError,"duplicate"):
                m.read_examples(path,"lion")

    def test_audit_fits_only_resolved_before_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"examples.jsonl"
            out=Path(tmp)/"lion.json"
            save(path)
            train_until=BASE+70*STEP
            evaluation_until=BASE+112*STEP
            result=m.audit(path,"lion",train_until=train_until,
                           evaluation_until=evaluation_until,
                           embargo_seconds=STEP,min_holdout=20,
                           artifact_path=out)
            self.assertEqual(result["status"],
                             "OFFLINE_CHRONOLOGICAL_HOLDOUT_AUDIT")
            self.assertGreaterEqual(result["training_resolved_disagreements"],12)
            self.assertGreater(result["metrics"]["n"],20)
            self.assertFalse(result["live_admission"])
            self.assertEqual(len(result["exported_artifact_sha256"]),64)
            artifact=json.loads(out.read_text())
            self.assertFalse(artifact["approved_for_live"])
            self.assertTrue(artifact["research_only"])
            self.assertEqual(artifact["train_asof"],train_until)
            self.assertLessEqual(artifact["train_max_decision_ts"],
                                 train_until)

    def test_hard_failure_when_holdout_too_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"examples.jsonl"
            save(path,80)
            with self.assertRaisesRegex(ValueError,"insufficient post-cutoff"):
                m.audit(path,"lion",train_until=BASE+73*STEP,
                        evaluation_until=BASE+80*STEP,
                        embargo_seconds=STEP,min_holdout=20)

    def test_panda_offline_holdout_and_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"panda.jsonl"
            save(path,95,"panda")
            r=m.audit(path,"panda",train_until=BASE+62*STEP,
                      evaluation_until=BASE+95*STEP,
                      embargo_seconds=STEP,min_holdout=20)
            self.assertGreater(r["metrics"]["n"],20)
            self.assertEqual(r["key"],"chi:Panda Plushie")
            self.assertEqual(r["metrics"]["selector"]["choose_a"]+
                             r["metrics"]["selector"]["choose_b"],
                             r["metrics"]["n"])


if __name__=="__main__":
    unittest.main()
