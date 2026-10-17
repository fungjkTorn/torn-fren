"""V53 frozen chronological Lion/Panda holdout audit (research only).

Inputs come solely from historical dual-expert replay in
research.v50_pair_example_export. A sample is TRAIN-eligible iff its observed
outcomes fully resolved before a fixed training cutoff. Holdout decisions must
occur after that cutoff (+ embargo) and resolve before the audit cutoff.

The selected model and its source feature medians are frozen before evaluating
holdout. Both experts and selector are evaluated on ALL eligible holdout rows,
not just expert disagreements. This prevents artificially inflated hit rates.
No new production prediction, collector writes, or online retraining.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from research.v49_lion_panda_pair_probe import TARGETS
from research.v50_pair_selector_artifact import (
    FEATURES,finite_float,train,choose_from_features,write_artifact,
)


def read_examples(path,target):
    if target not in TARGETS:
        raise ValueError("unsupported target")
    target_key=TARGETS[target]["key"]
    wanted=set(FEATURES[target])
    result=[]
    seen=set()
    with Path(path).open(encoding="utf-8") as stream:
        for n,line in enumerate(stream,1):
            if not line.strip():
                continue
            record=json.loads(line)
            if record.get("key")!=target_key:
                raise ValueError("record key does not match target")
            t=int(record["decision_ts"])
            feature_time=int(record["feature_as_of"])
            resolved=int(record["resolved_at"])
            if not 0<feature_time<=t<=resolved:
                raise ValueError("future features or impossible resolution")
            if t in seen:
                raise ValueError("duplicate decision anchor")
            seen.add(t)
            if (record.get("normalization")!="per_decision_cutoff" or
                record.get("source")!="SOURCE_PINNED_CAUSAL_ANALOG_EXPERTS" or
                record.get("research_only") is not True):
                raise ValueError("non-causal or unverified example provenance")
            a,b=record["a_success"],record["b_success"]
            if type(a) is not int or type(b) is not int or a not in (0,1) or b not in (0,1):
                raise ValueError("expert outcomes must be observed binary integers")
            f=record["features"]
            if set(f)!=wanted:
                raise ValueError("source features differ from winner")
            vals={name:finite_float(f[name]) for name in FEATURES[target]}
            if any(math.isinf(v) for v in vals.values()):
                raise ValueError("infinite source feature")
            result.append({
                "decision_ts":t,"feature_as_of":feature_time,
                "resolved_at":resolved,"a_success":a,"b_success":b,
                "features":vals,
            })
    return sorted(result,key=lambda x:x["decision_ts"])


def split_chronological(rows,train_until,evaluation_until,embargo_seconds):
    train_until=int(train_until)
    evaluation_until=int(evaluation_until)
    embargo_seconds=int(embargo_seconds)
    if not 0<train_until<evaluation_until or not 0<=embargo_seconds<=86400*7:
        raise ValueError("invalid frozen chronological cutoffs")
    training=[r for r in rows if r["decision_ts"]<=train_until
              and r["resolved_at"]<=train_until]
    # Explicit train_until embargo: no holdout decision can be part of the
    # model-fit evidence. Fully resolved after the held-out decision is okay
    # only when audited at evaluation_until, NEVER for training.
    holdout=[r for r in rows if
             train_until+embargo_seconds<r["decision_ts"]<=evaluation_until and
             r["resolved_at"]<=evaluation_until]
    return training,holdout


def rates(selected,holdout):
    if not holdout:
        raise ValueError("no resolved holdout rows")
    n=len(holdout)
    ah=sum(r["a_success"] for r in holdout)
    bh=sum(r["b_success"] for r in holdout)
    selected_hits=sum(r["b_success"] if choice else r["a_success"]
                      for r,choice in zip(holdout,selected))
    oracle=sum(max(r["a_success"],r["b_success"]) for r in holdout)
    b_choices=int(sum(selected))
    return {
        "n":n,
        "expert_a":{"hits":int(ah),"rate":ah/n},
        "expert_b":{"hits":int(bh),"rate":bh/n},
        "selector":{"hits":int(selected_hits),"rate":selected_hits/n,
                    "choose_b":b_choices,"choose_a":n-b_choices},
        "oracle_ceiling_not_reachable":{"hits":int(oracle),"rate":oracle/n},
        "expert_disagreements":sum(r["a_success"]!=r["b_success"]
                                  for r in holdout),
    }


def audit(path,target,*,train_until,evaluation_until,
          embargo_seconds=28800,min_holdout=20,artifact_path=None):
    rows=read_examples(path,target)
    early,late=split_chronological(rows,train_until,evaluation_until,
                                   embargo_seconds)
    train_only=[r for r in early if r["a_success"]!=r["b_success"]]
    if len(train_only)<12 or {r["b_success"] for r in train_only}!={0,1}:
        raise ValueError("training needs 12+ resolved two-class disagreements")
    if len(late)<min_holdout:
        raise ValueError("insufficient post-cutoff holdout observations")
    training=[(r["decision_ts"],
               [r["features"][k] for k in FEATURES[target]],
               r["a_success"],r["b_success"])
              for r in train_only]
    trained=train(training,target,train_until)
    selected=[choose_from_features(trained,r["features"]) for r in late]
    performance=rates(selected,late)
    trained["holdout_audit_only"]={
        "audit_train_until":int(train_until),
        "evaluation_until":int(evaluation_until),
        "embargo_seconds":int(embargo_seconds),
        "n_holdout":len(late),
        "holdout_metrics":performance,
    }
    digest=None
    if artifact_path is not None:
        digest=write_artifact(trained,artifact_path)
    return {
        "status":"OFFLINE_CHRONOLOGICAL_HOLDOUT_AUDIT",
        "key":TARGETS[target]["key"],
        "source_rows":len(rows),
        "training_resolved_disagreements":len(train_only),
        "training_cutoff":int(train_until),
        "holdout_start_exclusive":int(train_until)+int(embargo_seconds),
        "holdout_end":int(evaluation_until),
        "metrics":performance,
        "exported_artifact_sha256":digest,
        "research_only":True,
        "live_admission":False,
        "accuracy_claim":"holdout_on_explicit_historical_examples_only",
        "source":"SOURCE_PINNED_CAUSAL_ANALOG_EXPERTS",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--examples",required=True)
    p.add_argument("--target",required=True,choices=tuple(TARGETS))
    p.add_argument("--train-until",type=int,required=True)
    p.add_argument("--evaluate-until",type=int,required=True)
    p.add_argument("--embargo",type=int,default=28800)
    p.add_argument("--min-holdout",type=int,default=20)
    p.add_argument("--artifact",default=None)
    a=p.parse_args()
    try:
        result=audit(a.examples,a.target,train_until=a.train_until,
                     evaluation_until=a.evaluate_until,
                     embargo_seconds=a.embargo,
                     min_holdout=a.min_holdout,
                     artifact_path=a.artifact)
        print(json.dumps(result,sort_keys=True))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({"status":"RESEARCH_AUDIT_NOT_READY",
                          "error_type":type(exc).__name__,
                          "research_only":True},sort_keys=True))
        raise SystemExit(1)

if __name__=="__main__":
    main()
