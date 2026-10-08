"""Fixed-cutoff, read-only specialist research replay.

Unlike replay.py, the split is an explicit frozen timestamp, not the final
25% of whatever database was passed. Shared eligible starts are generated
before calculating model outcomes. All stored recommendations on valid starts
are scored; absence is failure. NO production routing.

Usage:
  python research/plushie_champions/locked_replay.py --db SNAPSHOT.db \
    --cutoff 1791241486 --target all --max-starts 12 --output report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from collections import defaultdict

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression

from common import (
    ResearchContext, AnalogPlanner, TemplatePlanner, TRAVEL_SECONDS,
    MAX_WAIT, STEP, GRACE, DAY, valid_starts, dynamic_replay,
    fixed_expert_outcomes, selector_feature_dict,
)
from recent_phase_select import WINNING_CONFIG as NESSIE
from rf_localgrid import WINNING_CONFIG as REDFOX
from lion_pair_selector_ml import EXPERT_A as LION_A, EXPERT_B as LION_B
from panda_pair_selector_ml import EXPERT_A as PANDA_A, EXPERT_B as PANDA_B
from checkpoint4_online_selector import EXPERTS as TEMPLATES, WINNING_WINDOWS
from camel_fast_selector import WINNING_CONFIG as CAMEL_CONFIG

TARGETS={
  "nessie": ("uni","Nessie Plushie"),
  "redfox": ("uni","Red Fox Plushie"),
  "lion": ("sou","Lion Plushie"),
  "panda": ("chi","Panda Plushie"),
  "monkey": ("arg","Monkey Plushie"),
  "chamois": ("swi","Chamois Plushie"),
  "camel": ("uae","Camel Plushie"),
}


def cohort(ctx,country,item,cutoff,max_starts=0,step=1800):
    """Start only after model freeze; use an 8h fully observed future window."""
    all_starts=valid_starts(ctx,country,item,stride=step)
    result=[s for s in all_starts if s>=cutoff]
    if max_starts and len(result)>max_starts:
        ix=np.linspace(0,len(result)-1,max_starts).round().astype(int)
        result=[result[i] for i in ix]
    return result


def _row(s,p,tl,travel):
    if p is None:
        return {"start":int(s),"departure":None,"arrival":None,
                "success":False,"recommended":False}
    dep=float(p[0]); arr=dep+travel
    return {"start":int(s),"departure":int(dep),"arrival":int(arr),
            "success":bool(tl.success(arr,GRACE)),"recommended":True}


def _simulate(s,plan,tl,travel):
    """Match uploaded specialist dynamic plan/scheduled-departure contract."""
    q=s; deadline=s+MAX_WAIT; sched=None
    while q<=deadline:
        proposal=plan(q)
        if proposal is not None and proposal[0]<=deadline:
            sched=proposal
        if sched is not None and sched[0]<=q+STEP:
            return _row(s,(max(q,sched[0]),),tl,travel)
        q+=STEP
    return _row(s,None,tl,travel)


def _summarize(rows):
    n=len(rows);hits=sum(r["success"] for r in rows)
    rec=sum(r["recommended"] for r in rows)
    waits=sorted(r["departure"]-r["start"] for r in rows if r["recommended"])
    return {"hits":hits,"starts":n,"all_start_success":hits/n if n else None,
            "recommendations":rec,"coverage":rec/n if n else None,
            "median_wait_seconds":waits[len(waits)//2] if waits else None,
            "rows":rows}


def _template_bank(ctx,country,item):
    return {x:TemplatePlanner(ctx,country,item,lags=x[0],lookback=x[1],
                             shift_range=x[2]).plan for x in TEMPLATES}


def _analog(ctx,country,item,spec,cutoff):
    return AnalogPlanner(ctx,country,item,int(spec["k"]),
                         float(spec["global_regime_weight"]),cutoff=cutoff).plan


def _feature(ctx,country,item,s,pa,pb,extra):
    d=selector_feature_dict(ctx,country,item,s,pa,pb)
    if extra:
        d.update({
          "g2_g6":d["g2"]/d["g6"] if d["g6"] else 1.,
          "g6_g18raw":d["g6"]/d["g18"] if d["g18"] else 1.,
          "rL_g18raw":d["rL"]/d["g18"] if d["g18"] else 1.,
          "prob_gap":d["B_prob"]-d["A_prob"],
          "rob_gap":d["B_rob"]-d["A_rob"],
        })
    return d


def _pair(ctx,country,item,starts,cutoff,expert_a,expert_b,kind):
    travel=TRAVEL_SECONDS[country];tl=ctx.timelines[(country,item)]
    # The training outcomes themselves must have matured before model freeze.
    early=valid_starts(ctx,country,item)
    early=[s for s in early if s+MAX_WAIT+travel+GRACE<=cutoff]
    if len(early)>320:
        ix=np.linspace(0,len(early)-1,320).round().astype(int)
        early=[early[i] for i in ix]
    A=_analog(ctx,country,item,expert_a,cutoff)
    B=_analog(ctx,country,item,expert_b,cutoff)
    a_train,a_first=fixed_expert_outcomes(tl,A,early,travel)
    b_train,b_first=fixed_expert_outcomes(tl,B,early,travel)
    # The expert training label means B uniquely wins versus A; where both agree,
    # no selector preference is identified.
    vectors=[];labels=[];names=None
    for s in early:
        if a_train[s]==b_train[s]:continue
        feat=_feature(ctx,country,item,s,a_first[s],b_first[s],kind=="panda")
        if names is None:names=list(feat)
        vectors.append([feat[k] for k in names])
        labels.append(int(b_train[s] and not a_train[s]))
    if not vectors or len(set(labels))<2:
        return {"status":"insufficient_discordant_training",
                "training_starts":len(early),"discordant":len(labels)}
    X=np.asarray(vectors,float); y=np.asarray(labels,int)
    med=np.nanmedian(X,axis=0);X=np.where(np.isfinite(X),X,med)
    if kind=="lion":
        clf=LogisticRegression(max_iter=2000,class_weight="balanced")
    else:
        clf=ExtraTreesClassifier(n_estimators=300,max_depth=3,
            min_samples_leaf=3,class_weight="balanced",
            random_state=2,n_jobs=-1,max_features="sqrt")
    clf.fit(X,y)
    a_future,a_first_future=fixed_expert_outcomes(tl,A,starts,travel)
    b_future,b_first_future=fixed_expert_outcomes(tl,B,starts,travel)
    rows=[]
    for s in starts:
        f=_feature(ctx,country,item,s,a_first_future[s],
                   b_first_future[s],kind=="panda")
        vec=np.asarray([[f[k] for k in names]],float)
        vec=np.where(np.isfinite(vec),vec,med)
        choose_b=int(clf.predict(vec)[0])
        chosen=B if choose_b else A
        row=_simulate(s,chosen,tl,travel)
        row["expert"]="B" if choose_b else "A"
        rows.append(row)
    out=_summarize(rows);out.update({"status":"complete",
        "training_starts":len(early),"discordant_training":len(labels),
        "cutoff":int(cutoff),"source":"frozen_pair_experts_refitted_pre_cutoff"})
    return out


def _online(ctx,country,item,starts,cutoff):
    tl=ctx.timelines[(country,item)];travel=TRAVEL_SECONDS[country]
    ps=_template_bank(ctx,country,item)
    # Only previously fully resolved outcomes may score expert utility.
    history=[s for s in valid_starts(ctx,country,item) if s<cutoff]
    session_pool=sorted(set(history+list(starts)))
    outcomes={};resolves={}
    for e,plan in ps.items():
        for s in session_pool:
            row=_simulate(s,plan,tl,travel)
            outcomes[(e,s)]=int(row["success"])
            resolves[(e,s)]=(row["arrival"]+GRACE) if row["recommended"] else None
    days=WINNING_WINDOWS[item];rows=[]
    for s in starts:
        matches=[x for x in session_pool if s-days*DAY<=x<s]
        ranked=[]
        for e in ps:
            past=[outcomes[(e,h)] for h in matches
                  if resolves[(e,h)] is not None and resolves[(e,h)]<s]
            rate=(sum(past)+2)/(len(past)+4) if past else .5
            ranked.append((rate,len(past),e))
        selected=max(ranked,key=lambda z:(z[0],z[1]))[2]
        row=_simulate(s,ps[selected],tl,travel)
        row["expert"]=repr(selected)
        rows.append(row)
    out=_summarize(rows)
    out.update({"status":"complete","resolved_window_days":days,
                "cutoff":int(cutoff),"source":"online_selected_from_resolved_past"})
    return out


def _camel(ctx,country,item,starts,cutoff):
    tl=ctx.timelines[(country,item)];travel=TRAVEL_SECONDS[country]
    ps=_template_bank(ctx,country,item)
    rows=[]
    for s in starts:
        def choose(q):
            candidates=[]
            for e,p in ps.items():
                result=p(q)
                if result is not None and result[0]<=s+MAX_WAIT:
                    candidates.append((result[1],result[2].get("maxfit",0),-result[0],result))
            return max(candidates,key=lambda z:(z[0],z[1],z[2]))[3] if candidates else None
        rows.append(_simulate(s,choose,tl,travel))
    out=_summarize(rows)
    out.update({"status":"complete","source":"24_template_current_plan_selector"})
    return out


def evaluate(ctx,name,cutoff,max_starts=0,step=1800):
    country,item=TARGETS[name];tl=ctx.timelines[(country,item)]
    starts=cohort(ctx,country,item,cutoff,max_starts,step)
    if not starts:return {"status":"no_clean_post_cutoff_starts","starts":0}
    if name=="nessie":
        planner=TemplatePlanner(ctx,country,item,lags=NESSIE["lags"],
            lookback=int(NESSIE["lookback_h"]*3600),
            shift_range=int(NESSIE["shift_h"]*3600),
            minfit=float(NESSIE["minfit"]))
        rows=[_simulate(s,planner.plan,tl,TRAVEL_SECONDS[country]) for s in starts]
        return {"status":"complete",**_summarize(rows)}
    if name=="redfox":
        plan=_analog(ctx,country,item,REDFOX,cutoff)
        rows=[_simulate(s,plan,tl,TRAVEL_SECONDS[country]) for s in starts]
        return {"status":"complete",**_summarize(rows)}
    if name in ("lion","panda"):
        pair=(LION_A,LION_B) if name=="lion" else (PANDA_A,PANDA_B)
        return _pair(ctx,country,item,starts,cutoff,*pair,name)
    if name in ("monkey","chamois"):
        return _online(ctx,country,item,starts,cutoff)
    return _camel(ctx,country,item,starts,cutoff)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--cutoff",type=int,required=True)
    p.add_argument("--target",choices=[*TARGETS,"all"],default="all")
    p.add_argument("--max-starts",type=int,default=8)
    p.add_argument("--step",type=int,default=1800)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    if a.max_starts<1 or a.step<300:
        p.error("max-starts>=1 and step>=300 required")
    db=Path(a.db).resolve(strict=True)
    result={"schema":"torn-fren-fixed-cutoff-specialist-shadow-v1",
        "db_sha256":hashlib.sha256(db.read_bytes()).hexdigest(),
        "cutoff":a.cutoff,
        "warning":"Unseen postcutoff observational shadow replay, NOT calibrated per-trip chance",
        "results":{}}
    targets=list(TARGETS) if a.target=="all" else [a.target]
    for target in targets:
        ctx=ResearchContext.build(str(db))
        try:result["results"][target]=evaluate(ctx,target,a.cutoff,a.max_starts,a.step)
        finally:ctx.con.close()
        print(target,result["results"][target].get("status"),flush=True)
    output=Path(a.output)
    if output.exists():raise SystemExit("Refusing to overwrite existing research artifact")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,default=str)+"\n")
    print("Saved",output)

if __name__=="__main__":main()
