"""Japan Xanax V8 regime-adaptive PRIVATE RESEARCH candidate.

Restores frozen V7 causal observation-lag mechanics and implements a
60-resolved-sample standardized Ridge alpha=3 challenger when the last five
reconstructed lifetimes are <0.90x the preceding average. The feature
engineering is a NEW V8 implementation informed by the checkpoint, not a
bit-for-bit verified reproduction of the original offline V8 tournament.
Do not schedule or publish before independent parity and VM workload checks.

This emits a candidate, NOT a live-calibrated success percentage.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np

from research.japan_xanax import v7_observation_lag as v7
from services.frozen_candidate_worker_v31 import (
    inspect_live_source, _install_frozen_readonly_history,
)

COUNTRY="jap"
ITEM="Xanax"
KEY=f"{COUNTRY}:{ITEM}"
SOURCE_BRANCH="research/japan_xanax"
STEP=300
HORIZON=28800
TRAVEL=8940
MIN_QTY=30
GRACE=10
RIDGE_ALPHA=3.0
RIDGE_N=60
REGIME_RATIO=0.90


def reconstructed_state(adjusted, idx):
    """Only adjusted windows <= decision idx enter a model feature."""
    if idx < 20 or adjusted[idx] is None:
        return None
    widths=[float(w["width"]) for w in adjusted[:idx+1] if w is not None]
    if len(widths)<20:
        return None
    cooldowns=v7.cooldown_history(None,adjusted,idx)
    if len(cooldowns)<20:
        return None
    def avg(values,n):
        return float(np.mean(values[-n:]))
    return np.array([
        widths[-1],widths[-2],
        avg(widths,3),avg(widths,5),avg(widths,10),avg(widths,20),
        cooldowns[-1],cooldowns[-2],
        avg(cooldowns,3),avg(cooldowns,5),
        avg(cooldowns,10),avg(cooldowns,20),
    ],dtype=float)


def regime_ratio(adjusted,idx):
    widths=[float(w["width"]) for w in adjusted[:idx+1] if w is not None]
    if len(widths)<20:
        return None
    historical=widths[:-5]
    prior=float(np.mean(historical))
    if prior<=0:
        return None
    return float(np.mean(widths[-5:]))/prior


def fit_rolling_ridge(known_samples,adjusted,idx,anchor):
    """No training label is visible until target window has fully resolved."""
    train=[]
    for sample in known_samples:
        if sample is None or sample["window_index"]>=idx:
            continue
        if sample["target_end"]>anchor:
            continue
        j=sample["window_index"]
        features=reconstructed_state(adjusted,j)
        if features is None:
            continue
        train.append((features,
                      float(sample["target_start"]-sample["decision_anchor"])))
    train=train[-RIDGE_N:]
    target=reconstructed_state(adjusted,idx)
    if len(train)<RIDGE_N or target is None:
        return None
    x=np.vstack([row[0] for row in train])
    y=np.array([row[1] for row in train],dtype=float)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(target)):
        return None
    mu=x.mean(axis=0)
    sigma=x.std(axis=0)
    sigma[sigma<1e-9]=1.0
    z=(x-mu)/sigma
    ztarget=(target-mu)/sigma
    beta=np.linalg.solve(z.T@z+RIDGE_ALPHA*np.eye(z.shape[1]),
                         z.T@(y-y.mean()))
    return anchor+float(y.mean()+ztarget@beta)


def estimate(observed,adjusted,now):
    """Return estimated arrival and method, or a transparent abstention."""
    if len(observed)!=len(adjusted) or not observed:
        return {"status":"INSUFFICIENT_RECONSTRUCTED_HISTORY"}
    idx=len(observed)-1
    current=adjusted[idx]
    if current is None:
        return {"status":"CURRENT_WINDOW_RECONSTRUCTION_UNAVAILABLE"}
    anchor=int(observed[idx]["end"])
    if anchor>now:
        return {"status":"FUTURE_ANCHOR_REJECTED"}
    cur={
        "window_index":idx,
        "decision_anchor":anchor,
        "dep_est":int(current["end"]),
        "prev_width":int(current["width"]),
    }
    if not v7.cooldown_history(observed,adjusted,idx):
        return {"status":"INSUFFICIENT_COOLDOWN_HISTORY"}
    strict=v7.strict_rows(observed)
    resolved=[]
    for row in strict:
        sample=v7.adjusted_sample(row,observed,adjusted)
        if sample is not None and sample["target_end"]<=anchor:
            resolved.append(sample)
    baseline=v7.base_prediction(cur,observed,adjusted)
    if baseline is None:
        return {"status":"V7_BASELINE_UNAVAILABLE"}
    residual=[]
    for sample in resolved:
        old=v7.base_prediction(sample,observed,adjusted)
        if old is not None:
            residual.append(float(sample["target_start"])-old)
    if residual:
        baseline=baseline+0.25*float(np.median(residual[-10:]))
    ratio=regime_ratio(adjusted,idx)
    chosen=baseline
    family="V7_ordinary_regime"
    if ratio is not None and ratio<REGIME_RATIO:
        challenger=fit_rolling_ridge(resolved,adjusted,idx,anchor)
        if challenger is not None:
            chosen=challenger
            family="V8_rolling_ridge_alpha3_regime"
        else:
            family="V7_no_resolved_ridge_training"
    arrival=int(round(chosen))
    departure=arrival-TRAVEL
    if departure<now:
        return {"status":"DEPARTURE_PASSED","model_config":family}
    if departure>now+HORIZON:
        return {"status":"OUT_OF_BOUNDS_CANDIDATE_REJECTED"}
    return {
        "status":"RESEARCH_PROPOSAL_ONLY",
        "model_generation":"V8_REGIME_CANDIDATE",
        "model_config":family,
        "key":KEY,
        "query_timestamp":now,
        "recommended_departure_timestamp":departure,
        "recommended_arrival_timestamp":arrival,
        "replan_step_seconds":STEP,
        "research_horizon_seconds":HORIZON,
        "quantity_threshold":MIN_QTY,
        "grace_seconds":GRACE,
        "probability_calibrated":False,
        "gameplay_automated":False,
        "source":"NEW_RECONSTRUCTION_CHECKPOINT_PARITY_PENDING",
    }


def predict(db,country,item,now):
    country,item,now=str(country).strip().lower(),str(item).strip(),int(now)
    if (country,item)!=(COUNTRY,ITEM):
        return {"status":"NOT_APPROVED_JAPAN_XANAX"}
    source=inspect_live_source(db,now)
    if source["status"]!="FRESH":
        return {"status":source["status"]}
    from services import history_service as hs
    _install_frozen_readonly_history(hs,db)
    observed,adjusted=v7.build_adjusted(COUNTRY,ITEM,MIN_QTY,2500)
    # Collector may append after the initial freshness attestation, while the
    # SQLite history helper reads. Refuse any observation newer than query time.
    p=Path(db).resolve(strict=True)
    with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=2) as con:
        latest=con.execute("SELECT MAX(timestamp) FROM stock_history").fetchone()[0]
    if latest is not None and int(latest)>now:
        return {"status":"FUTURE_RECORDS_PRESENT"}
    return estimate(observed,adjusted,now)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--country",required=True)
    p.add_argument("--item",required=True)
    p.add_argument("--now",type=int,required=True)
    a=p.parse_args()
    try:
        r=predict(a.db,a.country,a.item,a.now)
    except Exception as exc:
        r={"status":"JAPAN_V8_RESEARCH_ERROR","error_type":type(exc).__name__}
    print(json.dumps(r,sort_keys=True))


if __name__=="__main__":
    main()
