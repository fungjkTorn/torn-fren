"""V51 offline Japan Xanax V7 versus new V8 implementation parity audit.

The historical V8 checkpoint reports V7 7/21 exact and candidate regime
13/21 exact on a specific SQLite snapshot. Those are development-only values.

This audit reconstructs fully-resolved P2 strict opportunities and computes
forecasts AS OF EACH historical anchor. For every forecast the candidate is
given only the prefix of observed/adjusted windows available at that anchor.
No key, web, bot or VM scheduler access; collector DB read-only.

Never claim bit-for-bit V8 parity unless BOTH original source snapshot hash
and frozen V7 baseline reproduce. V8 differences remain observable, not
silently relabelled as the historical champion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

from services import history_service as hs
from services.frozen_candidate_worker_v31 import _install_frozen_readonly_history
from research.japan_xanax import v7_observation_lag as v7
from research.japan_xanax import v8_regime_candidate as v8

REFERENCE_SHA256="d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583"
FROZEN_CUTOFF=1791241426
EXPECTED_ROWS=8609
REFERENCE_N=21
V7_EXPECTED_EXACT=7
V8_DEV_EXPECTED_EXACT=13


def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk=f.read(1<<20)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def selected_opportunities(observed, adjusted, cutoff):
    # A sample's label may only be used to SCORE after the target ended.
    strict=v7.strict_rows(observed)
    out=[]
    for row in strict:
        sample=v7.adjusted_sample(row,observed,adjusted)
        if sample is None:
            continue
        if sample["decision_anchor"]<=cutoff:
            continue
        out.append((row,sample))
    return out


def audit_reconstructed(observed,adjusted,*,cutoff=FROZEN_CUTOFF):
    if len(observed)!=len(adjusted):
        raise ValueError("misaligned history")
    strict=v7.strict_rows(observed)
    samples=[v7.adjusted_sample(r,observed,adjusted) for r in strict]
    v7_predictions=v7.predictions(samples,observed,adjusted,60)
    v7_by_i={sample["window_index"]:pred
             for sample,pred in zip(samples,v7_predictions)
             if sample is not None and pred is not None}
    opportunities=selected_opportunities(observed,adjusted,cutoff)
    rows=[]
    for r,ground_truth in opportunities:
        i=int(r["window_index"])
        # The V8 candidate is NEW code; never use target i+2 or stock events
        # after anchor i in its causal decision path.
        prefix_o=observed[:i+1]
        prefix_a=adjusted[:i+1]
        anchor=int(observed[i]["end"])
        proposal=v8.estimate(prefix_o,prefix_a,anchor)
        baseline=v7_by_i.get(i)
        latest={
            "window_index":i,
            "decision_anchor":anchor,
            "target_end":int(ground_truth["target_end"]),
            "target_start":int(ground_truth["target_start"]),
            "v7_arrival":float(baseline) if baseline is not None else None,
            "v7_hit_exact":bool(v7.hit(ground_truth,baseline,0))
                 if baseline is not None else None,
            "v7_hit_10s":bool(v7.hit(ground_truth,baseline,10))
                 if baseline is not None else None,
            "v8_status":proposal["status"],
            "v8_model":proposal.get("model_config"),
            "v8_arrival":proposal.get("recommended_arrival_timestamp"),
        }
        if proposal["status"]=="RESEARCH_PROPOSAL_ONLY":
            arrival=proposal["recommended_arrival_timestamp"]
            latest["v8_hit_exact"]=bool(v7.hit(ground_truth,arrival,0))
            latest["v8_hit_10s"]=bool(v7.hit(ground_truth,arrival,10))
            latest["v8_hit_60s"]=bool(v7.hit(ground_truth,arrival,60))
            latest["v8_hit_180s"]=bool(v7.hit(ground_truth,arrival,180))
        else:
            for metric in ("v8_hit_exact","v8_hit_10s",
                           "v8_hit_60s","v8_hit_180s"):
                latest[metric]=None
        rows.append(latest)
    def rate(metric):
        eligible=[r[metric] for r in rows if r[metric] is not None]
        hits=sum(eligible)
        return {"hits":hits,"n":len(eligible),
                "coverage":len(eligible)/len(rows) if rows else 0,
                "rate":hits/len(eligible) if eligible else None}
    return {
        "opportunities":len(rows),
        "v7_exact":rate("v7_hit_exact"),
        "v7_10s":rate("v7_hit_10s"),
        "v8_exact":rate("v8_hit_exact"),
        "v8_10s":rate("v8_hit_10s"),
        "v8_60s":rate("v8_hit_60s"),
        "v8_180s":rate("v8_hit_180s"),
        "model_choices":{
            "V7_ordinary_regime":sum(
                r["v8_model"]=="V7_ordinary_regime" for r in rows),
            "V8_rolling_ridge_alpha3_regime":sum(
                r["v8_model"]=="V8_rolling_ridge_alpha3_regime" for r in rows),
            "other_or_abstain":sum(r["v8_model"] not in
                ("V7_ordinary_regime","V8_rolling_ridge_alpha3_regime")
                for r in rows),
        },
        "decisions":rows,
    }


def report(db,*,cutoff=FROZEN_CUTOFF,check_hash=True):
    resolved=Path(db).resolve(strict=True)
    digest=file_sha256(resolved) if check_hash else None
    _install_frozen_readonly_history(hs,resolved)
    raw=hs._get_all_item_rows_with_source("jap","Xanax")
    observed,adjusted=v7.build_adjusted("jap","Xanax",30,2500)
    result=audit_reconstructed(observed,adjusted,cutoff=cutoff)
    reference=(cutoff==FROZEN_CUTOFF and
               digest==REFERENCE_SHA256 and len(raw)==EXPECTED_ROWS)
    baseline_match=(result["opportunities"]==REFERENCE_N and
                    result["v7_exact"]["hits"]==V7_EXPECTED_EXACT and
                    result["v7_exact"]["n"]==REFERENCE_N)
    v8_match=(result["v8_exact"]["hits"]==V8_DEV_EXPECTED_EXACT and
              result["v8_exact"]["n"]==REFERENCE_N)
    status=("HISTORICAL_V8_RATE_PARITY_OBSERVED"
            if reference and baseline_match and v8_match else
            "HISTORICAL_V8_RATE_PARITY_FAILED"
            if reference and baseline_match and not v8_match else
            "V7_BASELINE_PARITY_FAILED"
            if reference and not baseline_match else
            "REFERENCE_SNAPSHOT_NOT_VERIFIED")
    result.update({
        "status":status,
        "source_sha256":digest,
        "matches_checkpoint_source_hash":digest==REFERENCE_SHA256
            if digest is not None else False,
        "source_japan_rows":len(raw),
        "reference_snapshot_row_count":EXPECTED_ROWS,
        "reference_cutoff":FROZEN_CUTOFF,
        "cutoff_used":int(cutoff),
        "reference_v7_exact":"7/21",
        "development_v8_exact":"13/21",
        "baseline_match":baseline_match,
        "v8_rate_match":v8_match,
        "research_only":True,
        "source":"NEW_V8_RECONSTRUCTION_UNVALIDATED",
        "deploy_approved":False,
    })
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--cutoff",type=int,default=FROZEN_CUTOFF)
    p.add_argument("--no-hash",action="store_true",
                   help="No exact-snapshot parity claim without hash")
    p.add_argument("--output",default=None,
                   help="Optional local JSON report path, NEVER source DB")
    a=p.parse_args()
    result=report(a.db,cutoff=a.cutoff,check_hash=not a.no_hash)
    output={"status":result["status"],
            "reference_verified":result["matches_checkpoint_source_hash"],
            "opportunities":result["opportunities"],
            "v7_exact":result["v7_exact"],
            "v8_exact":result["v8_exact"],
            "v8_180s":result["v8_180s"],
            "v8_model_choices":result["model_choices"],
            "deploy_approved":False}
    if a.output:
        pth=Path(a.output)
        pth.parent.mkdir(parents=True,exist_ok=True)
        pth.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                       encoding="utf-8")
        output["report_path"]=str(pth)
    print(json.dumps(output,sort_keys=True))
    # A parity gap means HOLD FOR AUDIT, not a shell crash / production fault.
    # Never publish V8 from this offline audit without prospective evaluation.

if __name__=="__main__":
    main()
