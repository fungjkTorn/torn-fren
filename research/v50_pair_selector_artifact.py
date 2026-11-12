"""V50 portable, source-pinned Lion/Panda SELECTOR artifacts (research only).

Data format: JSONL, one historical decision per line:
{"key":"sou:Lion Plushie","decision_ts":123,"resolved_at":456,
 "feature_as_of":123,"features":{"g2_g18":...,...},
 "a_success":0,"b_success":1}

Generate examples separately from frozen historical replay. Require completed
real outcomes; NEVER train from predicted probability or use future labels.
Export JSON, not pickle/joblib. Deterministic pure Python inference matches
sklearn predictions (CI parity proof). Training is OFFLINE ONLY; artifacts
aren't approved for website or 19-worker scheduler by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from research.v49_lion_panda_pair_probe import TARGETS

SCHEMA="torn-fren-v50-research-selector-v1"
BASE=(
    "g2_g18","g6_g18","active_frac","rL_g6","rW",
    "active","age","qty","hour",
    "A_prob","A_rob","A_delay",
    "B_prob","B_rob","B_delay",
    "dp","dr","ddelay","g2","g6","g18","af","rL","rW2",
)
PANDA_EXTRA=("g2_g6","g6_g18raw","rL_g18raw","prob_gap","rob_gap")
FEATURES={"lion":BASE,"panda":BASE+PANDA_EXTRA}

def finite_float(value):
    if value is None:
        return float("nan")
    if isinstance(value,bool):
        raise ValueError("boolean feature")
    return float(value)

def load_resolved_examples(filename,target,cutoff):
    if target not in TARGETS:
        raise ValueError("unsupported target")
    now=int(cutoff)
    expected=TARGETS[target]["key"]
    names=FEATURES[target]
    rows=[]
    seen=set()
    with Path(filename).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj=json.loads(line)
            if obj.get("key")!=expected:
                raise ValueError("wrong item key in source examples")
            t=int(obj["decision_ts"])
            observed=int(obj["resolved_at"])
            feature_as_of=int(obj["feature_as_of"])
            if not 0<feature_as_of<=t<=observed<=now:
                raise ValueError("unresolved or future-labelled example rejected")
            if t in seen:
                raise ValueError("duplicate decision timestamp")
            seen.add(t)
            a,b=obj["a_success"],obj["b_success"]
            if a not in (0,1) or b not in (0,1):
                raise ValueError("only observed binary outcomes accepted")
            feats=obj["features"]
            if set(feats)!=set(names):
                raise ValueError("selector feature key schema mismatch")
            x=[finite_float(feats[k]) for k in names]
            if any(math.isinf(v) for v in x):
                raise ValueError("infinite selector feature")
            rows.append((t,x,int(a),int(b)))
    rows.sort()
    # The original selector trains only on expert disagreements.
    differing=[r for r in rows if r[2]!=r[3]]
    if len(differing)<12 or {r[3] for r in differing}!={0,1}:
        raise ValueError("insufficient resolved two-class expert disagreements")
    return differing

def to_matrix(examples):
    X=np.asarray([r[1] for r in examples],float)
    if X.ndim!=2:
        raise ValueError("missing training matrix")
    with np.errstate(all="ignore"):
        med=np.nanmedian(X,axis=0)
    if not np.all(np.isfinite(med)):
        raise ValueError("feature column has no finite samples")
    X=np.where(np.isfinite(X),X,med)
    if not np.all(np.isfinite(X)):
        raise ValueError("failed to impute invalid feature")
    return X,med

def train(examples,target,cutoff,*,source_label="USER_SUPPLIED_CAUSAL_REPLAY"):
    """Train EXACT winning sklearn selector hyperparameters on resolved-only data."""
    if target not in TARGETS:
        raise ValueError("unsupported target")
    X,med=to_matrix(examples)
    # y=1 if B wins disagreement, else 0; matches original champion script.
    y=np.asarray([r[3] for r in examples],int)
    if set(y.tolist())!={0,1}:
        raise ValueError("two classes needed")
    if target=="lion":
        from sklearn.linear_model import LogisticRegression
        clf=LogisticRegression(max_iter=2000,class_weight="balanced").fit(X,y)
        model={"family":"logistic",
               "coef":clf.coef_[0].astype(float).tolist(),
               "intercept":float(clf.intercept_[0])}
    else:
        from sklearn.ensemble import ExtraTreesClassifier
        clf=ExtraTreesClassifier(
            n_estimators=300,max_depth=3,min_samples_leaf=3,
            class_weight="balanced",random_state=2,n_jobs=1,
            max_features="sqrt").fit(X,y)
        trees=[]
        for fitted in clf.estimators_:
            tree=fitted.tree_
            # tree.value shape: nodes x n_outputs(=1) x n_classes(=2).
            raw=tree.value[:,0,:].astype(float)
            den=raw.sum(axis=1)
            if np.any(den<=0):
                raise ValueError("zero-count classification tree node")
            leaf_p=(raw[:,1]/den).tolist()
            trees.append({
                "left":tree.children_left.astype(int).tolist(),
                "right":tree.children_right.astype(int).tolist(),
                "feature":tree.feature.astype(int).tolist(),
                "threshold":tree.threshold.astype(float).tolist(),
                "p_class1":leaf_p,
            })
        model={"family":"extra_trees","trees":trees}
    if clf.classes_.tolist()!=[0,1]:
        raise ValueError("unexpected classes")
    artifact={
        "schema":SCHEMA,
        "research_only":True,
        "approved_for_live":False,
        "target":target,
        "key":TARGETS[target]["key"],
        "source":source_label,
        "train_asof":int(cutoff),
        "train_max_decision_ts":max(r[0] for r in examples),
        "resolved_disagreements":len(examples),
        "feature_names":list(FEATURES[target]),
        "imputation_medians":med.astype(float).tolist(),
        "winning_selector":TARGETS[target]["selector"],
        "expert_a":list(TARGETS[target]["expert_a"]),
        "expert_b":list(TARGETS[target]["expert_b"]),
        "model":model,
    }
    # Cross-check every training row. A parity failure blocks export.
    reconstructed=np.array([choose_from_vector(artifact,row) for row in X])
    expected=clf.predict(X).astype(int)
    if not np.array_equal(reconstructed,expected):
        raise ValueError("portable selector diverged from fitted sklearn")
    return artifact

def choose_from_vector(artifact,vector):
    """Pure numerical implementation of sklearn binary decisions; no pickle."""
    x=np.asarray(vector,dtype=float)
    m=artifact["model"]
    if x.shape!=(len(artifact["feature_names"]),) or not np.all(np.isfinite(x)):
        raise ValueError("invalid imputed feature vector")
    if m["family"]=="logistic":
        z=float(np.dot(x,np.asarray(m["coef"],float))+m["intercept"])
        return int(z>0)
    if m["family"]=="extra_trees":
        probs=[]
        for t in m["trees"]:
            j=0
            for _ in range(20):
                left=int(t["left"][j])
                if left<0:
                    probs.append(float(t["p_class1"][j]))
                    break
                k=int(t["feature"][j])
                j=left if x[k]<=float(t["threshold"][j]) else int(t["right"][j])
            else:
                raise ValueError("tree depth bound exceeded")
        # ExtraTreesClassifier.predict averages class probabilities; ties
        # choose first class (0) via argmax, as in sklearn.
        return int((sum(probs)/len(probs))>.5)
    raise ValueError("unknown selector family")

def choose_from_features(artifact,features):
    if not isinstance(artifact,dict) or artifact.get("schema")!=SCHEMA:
        raise ValueError("unsupported artifact schema")
    if artifact.get("approved_for_live") is not False or not artifact.get("research_only"):
        raise ValueError("research artifact contract changed")
    names=artifact["feature_names"]
    if set(features)!=set(names):
        raise ValueError("feature mismatch")
    x=np.asarray([finite_float(features[k]) for k in names],float)
    med=np.asarray(artifact["imputation_medians"],float)
    if x.shape!=med.shape or not np.all(np.isfinite(med)):
        raise ValueError("bad artifact medians")
    x=np.where(np.isfinite(x),x,med)
    return choose_from_vector(artifact,x)

def write_artifact(artifact,path):
    path=Path(path)
    if path.suffix!=".json":
        raise ValueError("output must be JSON")
    path.parent.mkdir(parents=True,exist_ok=True)
    body=json.dumps(artifact,sort_keys=True,separators=(",",":"),allow_nan=False)
    digest=hashlib.sha256(body.encode("utf-8")).hexdigest()
    # file is intentionally marked NOT approved for live use.
    path.write_text(body+"\n",encoding="utf-8")
    return digest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target",required=True,choices=tuple(TARGETS))
    p.add_argument("--examples",required=True)
    p.add_argument("--train-asof",required=True,type=int)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    data=load_resolved_examples(a.examples,a.target,a.train_asof)
    artifact=train(data,a.target,a.train_asof)
    digest=write_artifact(artifact,a.output)
    print(json.dumps({
        "status":"RESEARCH_ONLY_SELECTOR_ARTIFACT",
        "key":artifact["key"],
        "examples":len(data),
        "training_cutoff":a.train_asof,
        "sha256":digest,
        "no_live_promotion":True,
    },sort_keys=True))

if __name__=="__main__":
    main()
