"""V103 research: ACTUAL champion model arrival score curves, not delay guesses.

Reads the pinned research champion objects from plushie_champions/common.py.
Copies their score calculation, while leaving their champion plan selection
untouched; parity regressions compare raw curve to original plan.

AnalogPlanner: historical nearest-neighbor success frequency for each arrival.
TemplatePlanner: weighted historic-pattern projected >=30-state for each arrival.
Both are MODEL SCORES, NOT forecasted quantity or calibrated probabilities,
and their >=30 windows are score-based proxies, not actual restock timestamps.

No calls to APIs/VM/website and no production code changes. The as-of
historical query must be earlier than every analog training end: inherited
AnalogPlanner uses neighbors resolved before query time (q-maxfuture).
"""
from __future__ import annotations

import math

import numpy as np

from research.plushie_champions.common import MAX_WAIT,STEP,AnalogPlanner,TemplatePlanner


def analog_scores(planner: AnalogPlanner, query: int):
    """Same raw and robust availability scores computed inside AnalogPlanner.plan."""
    if not isinstance(planner,AnalogPlanner):
        raise TypeError("expected research AnalogPlanner")
    q=int(query)
    qi=int(round((q-planner.ctx.grid[0])/STEP))
    if qi<0 or qi>=len(planner.ctx.grid):
        return None
    hi=np.searchsorted(planner.ctx.grid,q-planner.maxfuture,"right")
    ids=np.arange(0,hi,6)
    ids=ids[
        planner.path_ok[ids]
        & ~np.isnan(planner.ctx.active[planner.target_i,ids])
    ]
    if len(ids)<planner.k:
        return None
    same=(planner.ctx.active[planner.target_i,ids]
          ==planner.ctx.active[planner.target_i,qi])
    if same.sum()>=planner.k:
        ids=ids[same]
    diff=(planner.Z[ids]-planner.Z[qi])*planner.weights
    dist=np.sqrt(np.nanmean(diff*diff,axis=1))
    kk=min(planner.k,len(dist))
    pick=np.argpartition(dist,kk-1)[:kk]
    nid,dd=ids[pick],dist[pick]
    ww=np.exp(-dd)
    ww/=ww.sum() or 1
    arrivals=planner.ctx.grid[nid][:,None]+planner.delays[None,:]+planner.travel
    probs=(planner.tl.success_many(arrivals.ravel())
           .reshape(len(nid),len(planner.delays))*ww[:,None]).sum(axis=0)
    robust=probs.copy()
    for j in range(len(planner.delays)):
        nearby=probs[max(0,j-2):min(len(planner.delays),j+3)]
        robust[j]=.55*probs[j]+.3*nearby.mean()+.15*nearby.min()
    return {"delay_seconds":np.asarray(planner.delays,dtype=int),
            "availability_score":np.asarray(probs,dtype=float),
            "robust_score":np.asarray(robust,dtype=float),
            "eligible_historical_neighbors":len(nid),
            "model_type":"analog"}


def template_scores(planner: TemplatePlanner, query: int):
    """Same pattern-matching score for EACH delay as TemplatePlanner.plan."""
    if not isinstance(planner,TemplatePlanner):
        raise TypeError("expected research TemplatePlanner")
    q=int(query)
    refs=[]
    for d in planner.lags:
        fit,shift,raw=planner._best_ref(q,d)
        if fit>=planner.minfit:
            refs.append((d,shift,fit,raw))
    delay=[]
    probs=[]
    for d in range(0,MAX_WAIT+1,STEP):
        at=q+planner.travel+d
        num=den=0.0
        for day,shift,fit,raw in refs:
            observed=planner._state(at-day*86400-shift)
            if observed is None:
                continue
            weight=fit*fit/day
            num+=weight*int(observed)
            den+=weight
        if den:
            delay.append(d)
            probs.append(num/den)
    # When no references fit, incumbent returns a .5 fallback for departure
    # scoring. Do not invent a supposedly 'earliest supported' curve.
    return {
        "delay_seconds":np.asarray(delay,dtype=int),
        "availability_score":np.asarray(probs,dtype=float),
        "eligible_reference_patterns":len(refs),
        "model_type":"template"}


def score_curve(planner,query):
    if isinstance(planner,AnalogPlanner):
        return analog_scores(planner,query)
    if isinstance(planner,TemplatePlanner):
        return template_scores(planner,query)
    raise TypeError("unsupported model family: explicit adapters needed")


def analog_champion_from_curve(q,curve):
    """Exact historic AnalogPlanner.plan selection logic for parity checks."""
    if curve is None:
        return None
    probs=curve["availability_score"]
    robust=curve["robust_score"]
    delays=curve["delay_seconds"]
    near=np.where((robust>=robust.max()-.025)&
                  (probs>=probs.max()-.04))[0]
    if len(near):
        groups=np.split(near,np.where(np.diff(near)>1)[0]+1)
        best=max(groups,key=lambda g:(robust[g].mean(),probs[g].mean(),
                                      len(g),-g[0]))
        j=int(best[len(best)//2])
    else:
        j=int(np.argmax(robust))
    return (int(q)+int(delays[j]),float(probs[j]),float(robust[j]))


def template_champion_from_curve(q,curve):
    """Match current template plateau selection (including .5 fallback)."""
    if curve is None:
        return None
    delay=curve["delay_seconds"]
    probs=curve["availability_score"]
    if not len(delay):
        return (int(q),.5)
    best=float(max(probs))
    cand=[(int(d),float(p)) for d,p in zip(delay,probs) if p>=best-.04]
    groups=[]
    for pair in cand:
        if not groups or pair[0]-groups[-1][-1][0]>STEP:
            groups.append([pair])
        else:
            groups[-1].append(pair)
    selected=max(groups,key=lambda g:(sum(v for _,v in g)/len(g),
                                      len(g),-g[0][0]))
    d,p=selected[len(selected)//2]
    return (int(q)+d,p)


def earliest_from_curve(q,curve,*,floor,min_consecutive_points=1):
    """Earliest prospective departure satisfying fixed predeclared score floor.

    A stability constraint requires a *contiguous sequence* of scored 5m
    arrivals. No future observed stock rows are inspected to pick departures.
    """
    if (not isinstance(floor,(int,float)) or isinstance(floor,bool)
        or not math.isfinite(floor) or not 0<=floor<=1
        or type(min_consecutive_points) is not int
        or not 1<=min_consecutive_points<=30):
        raise ValueError("invalid score threshold")
    if curve is None or not len(curve["delay_seconds"]):
        return None
    delays=curve["delay_seconds"]
    probabilities=curve["availability_score"]
    count=len(delays)
    for i in range(count):
        if probabilities[i]<floor:
            continue
        j=i+1
        while (j<count and delays[j]-delays[j-1]==STEP
               and probabilities[j]>=floor):
            j+=1
        if j-i>=min_consecutive_points:
            return (int(q)+int(delays[i]),float(probabilities[i]))
    return None
