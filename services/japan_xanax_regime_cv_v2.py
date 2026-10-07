from __future__ import annotations
import argparse, json, math, statistics, time
from pathlib import Path
import services.history_service as hs
from services.japan_xanax_window_regime_longform import build_windows, build_samples, evaluate

def wilson(k,n,z=1.96):
    if not n:return 0.0
    p=k/n; d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/d

def metric(r,g):
    return r["rates"].get(g,0.0)

def fold_eval(rows,cfg,args,start,end,folds):
    span=end-start
    bounds=[]
    for f in range(folds):
        lo=start+round(span*f/folds); hi=start+round(span*(f+1)/folds)
        if hi>lo: bounds.append((lo,hi))
    rs=[evaluate(rows,lo,hi,cfg,args) for lo,hi in bounds]
    ns=[r["n"] for r in rs]; total=sum(ns)
    hits={g:sum(round(r["rates"].get(g,0)*r["n"]) for r in rs) for g in args.graces}
    rates={g:(hits[g]/total if total else 0) for g in args.graces}
    cov=sum(r["coverage"]*(hi-lo) for r,(lo,hi) in zip(rs,bounds))/max(1,span)
    active=[r for r in rs if r["n"]]
    return {"n":total,"coverage":cov,"rates":rates,
      "wilson":{g:wilson(hits[g],total) for g in args.graces},
      "fold_rates":{g:[r["rates"].get(g,0) for r in active] for g in args.graces},
      "fold_n":ns}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",default="data/stock_history.db"); p.add_argument("--country",default="jap"); p.add_argument("--item",default="Xanax")
    p.add_argument("--travel-minutes",type=float,default=149); p.add_argument("--min-quantity",type=int,default=30)
    p.add_argument("--grace-seconds",default="0,5,15,60,180"); p.add_argument("--width-thresholds",default="0,8,10,12,14,16,18,20,22,24")
    p.add_argument("--lookbacks",default="10,15,20,30,40,60,all"); p.add_argument("--tod-bins",default="0,4,6")
    p.add_argument("--confidence-thresholds",default="0,0.5,0.6,0.7,0.75,0.8,0.85,0.9")
    p.add_argument("--departure-grid-seconds",type=int,default=30); p.add_argument("--max-wait-minutes",type=int,default=240)
    p.add_argument("--min-analogs",type=int,default=5); p.add_argument("--min-train-cycles",type=int,default=60)
    p.add_argument("--walk-forward-folds",type=int,default=6); p.add_argument("--min-validation-recommendations",type=int,default=18)
    p.add_argument("--min-active-folds",type=int,default=4); p.add_argument("--min-policy-coverage",type=float,default=.10)
    p.add_argument("--target-exact",type=float,default=.50); p.add_argument("--target-5s",type=float,default=.60)
    p.add_argument("--target-15s",type=float,default=.75); p.add_argument("--target-60s",type=float,default=.90)
    p.add_argument("--output",default="reports/japan_xanax_regime_cv_v2")
    a=p.parse_args(); a.travel=round(a.travel_minutes*60); a.waitmax=round(a.max_wait_minutes*60); a.step=a.departure_grid_seconds
    a.graces=[int(x) for x in a.grace_seconds.split(",")]; hs.DB_PATH=Path(a.db)
    rows=build_samples(build_windows(a.country,a.item,a.min_quantity)); start=a.min_train_cycles; end=len(rows)
    lbs=[None if x=="all" else int(x) for x in a.lookbacks.split(",")]
    cuts=[None if float(x)==0 else float(x)*60 for x in a.width_thresholds.split(",")]
    bins=[int(x) or None for x in a.tod_bins.split(",")]; confs=[None if float(x)==0 else float(x) for x in a.confidence_thresholds.split(",")]
    cfgs=[{"lb":lb,"width_cut":cut,"tod_bins":b,"conf":c,"min_analogs":a.min_analogs} for lb in lbs for cut in cuts for b in bins for c in confs]
    print(f"samples={len(rows)} development_range={start}:{end} configs={len(cfgs)} folds={a.walk_forward_folds}",flush=True)
    scored=[]
    for z,c in enumerate(cfgs,1):
        r=fold_eval(rows,c,a,start,end,a.walk_forward_folds)
        active=sum(n>0 for n in r["fold_n"])
        if r["n"]<a.min_validation_recommendations or r["coverage"]<a.min_policy_coverage or active<a.min_active_folds: continue
        # Conservative ranking: exact reliability first, then downstream reliability,
        # with Wilson lower bounds and worst-fold behavior penalizing tiny/unstable policies.
        floors={g:min(r["fold_rates"][g]) if r["fold_rates"][g] else 0 for g in (0,5,15,60)}
        gates=(metric(r,0)>a.target_exact,metric(r,5)>=a.target_5s,metric(r,15)>=a.target_15s,metric(r,60)>=a.target_60s)
        prefix=0
        for ok in gates:
            if ok: prefix+=1
            else: break
        score=(prefix,r["wilson"].get(0,0),r["wilson"].get(60,0),floors[0],floors[60],r["coverage"],r["n"])
        scored.append((score,c,r,floors))
        if z%200==0: print(f"tested {z}/{len(cfgs)} eligible={len(scored)}",flush=True)
    scored.sort(key=lambda x:x[0],reverse=True)
    if not scored: raise SystemExit("No robust policies met minimum evidence constraints")
    # Coverage frontier by minimum exact Wilson reliability bands.
    frontier=[]
    for floor in (0.30,0.35,0.40,0.45,0.50,0.55,0.60):
        eligible=[x for x in scored if x[2]["wilson"].get(0,0)>=floor]
        if eligible:
            best=max(eligible,key=lambda x:(x[2]["coverage"],x[2]["wilson"].get(60,0)))
            frontier.append({"exact_wilson_floor":floor,"config":best[1],"metrics":best[2],"fold_floors":best[3]})
    top=[{"config":c,"metrics":r,"fold_floors":fl} for _,c,r,fl in scored[:30]]
    out={"schema":"japan-xanax-regime-cv-v2","created_at":int(time.time()),"samples":len(rows),
      "development_only":True,"note":"Previously opened latest 25% is included as development; no final holdout claim.",
      "top":top,"coverage_frontier":frontier}
    path=Path(a.output).with_suffix(".json"); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(out,indent=2))
    print("\n=== ROBUST CV LEADER ==="); print(json.dumps(top[0],indent=2))
    print("\n=== COVERAGE FRONTIER ===")
    for x in frontier: print(json.dumps({"wilson_floor":x["exact_wilson_floor"],"coverage":x["metrics"]["coverage"],"n":x["metrics"]["n"],"rates":x["metrics"]["rates"],"config":x["config"]}))
    print(f"\nSaved {path}")

if __name__=="__main__": main()
