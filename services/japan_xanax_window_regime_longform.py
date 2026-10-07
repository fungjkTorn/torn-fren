from __future__ import annotations
import argparse, csv, json, math, statistics, time
from pathlib import Path
import services.history_service as hs

def wilson(k,n,z=1.96):
    if not n: return 0.0
    p=k/n; d=1+z*z/n
    return (p+z*z/(2*n)-z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)))/d

def build_windows(country,item,minq):
    raw=hs._get_all_item_rows_with_source(country,item)
    clean,_=hs._suppress_provider_bounces(raw)
    out=[]; start=None; peak=0
    for ts,q,_source in clean:
        if q>=minq and start is None: start=ts; peak=q
        elif q>=minq: peak=max(peak,q)
        elif start is not None:
            if ts>start: out.append({"start":start,"end":ts,"width":ts-start,"peak":peak})
            start=None; peak=0
    return out

def build_samples(ws):
    out=[]
    for i in range(len(ws)-2):
        anchor=ws[i]["end"]; target=ws[i+2]
        recent=[x["width"] for x in ws[max(0,i-4):i+1]]
        out.append({"anchor":anchor,"prev_width":ws[i]["width"],
          "prev2_width":ws[i-1]["width"] if i else None,
          "recent3":statistics.mean(recent[-3:]),"recent5":statistics.mean(recent),
          "target_start":target["start"],"target_end":target["end"],
          "target_width":target["width"],"target_offset":target["start"]-anchor})
    return out

def hit(s,arrival,grace):
    return arrival+grace>=s["target_start"] and arrival<=s["target_end"]

def tod_bin(ts,bins):
    return int(((ts%86400)/86400)*bins)%bins

def analogs(train,cfg,candidate_arrival):
    pool=train[-cfg["lb"]:] if cfg["lb"] else train
    if cfg["width_cut"] is not None:
        pool=[x for x in pool if x["prev_width"]>=cfg["width_cut"]]
    if cfg["tod_bins"]:
        b=tod_bin(candidate_arrival,cfg["tod_bins"])
        pool=[x for x in pool if tod_bin(x["anchor"]+x["target_offset"],cfg["tod_bins"])==b]
    return pool

def predict(train,cur,cfg,args):
    best=None
    for wait in range(0,args.waitmax+1,args.step):
        arrival=cur["anchor"]+args.travel+wait
        pool=analogs(train,cfg,arrival)
        if len(pool)<cfg["min_analogs"]: continue
        rates={g:sum(hit(x,x["anchor"]+args.travel+wait,g) for x in pool)/len(pool) for g in args.graces}
        score=(rates.get(0,0)*4+rates.get(5,0)*3+rates.get(15,0)*2+rates.get(60,0),-wait)
        if best is None or score>best["score"]:
            best={"wait":wait,"rates":rates,"n_analogs":len(pool),"score":score}
    return best

def evaluate(rows,start,end,cfg,args):
    rec=[]
    for i in range(start,end):
        pr=predict(rows[:i],rows[i],cfg,args)
        if not pr: continue
        if cfg["conf"] is not None and pr["rates"].get(60,0)<cfg["conf"]: continue
        arrival=rows[i]["anchor"]+args.travel+pr["wait"]
        rec.append({"i":i,"wait_s":pr["wait"],"analogs":pr["n_analogs"],
          "actual":{g:int(hit(rows[i],arrival,g)) for g in args.graces},
          "target_width_s":rows[i]["target_width"]})
    n=len(rec); rates={g:(sum(r["actual"][g] for r in rec)/n if n else 0) for g in args.graces}
    return {"n":n,"coverage":n/max(1,end-start),"rates":rates,
      "wilson":{g:wilson(sum(r["actual"][g] for r in rec),n) for g in args.graces},"records":rec}

def main():
    p=argparse.ArgumentParser(description="Long-form Japan Xanax P2 arrival/regime tournament")
    p.add_argument("--db",default="data/stock_history.db"); p.add_argument("--country",default="jap")
    p.add_argument("--item",default="Xanax"); p.add_argument("--travel-minutes",type=float,default=149)
    p.add_argument("--min-quantity",type=int,default=30); p.add_argument("--holdout-fraction",type=float,default=.25)
    p.add_argument("--min-train-cycles",type=int,default=60); p.add_argument("--grace-seconds",default="0,5,15,60,180")
    p.add_argument("--width-thresholds",default="0,8,10,12,14,16,18,20,22,24,26,28,30")
    p.add_argument("--lookbacks",default="10,15,20,30,40,60,all"); p.add_argument("--tod-bins",default="0,4,6")
    p.add_argument("--confidence-thresholds",default="0,0.5,0.6,0.7,0.75,0.8,0.85,0.9")
    p.add_argument("--departure-grid-seconds",type=int,default=15); p.add_argument("--max-wait-minutes",type=int,default=240)
    p.add_argument("--min-analogs",type=int,default=5); p.add_argument("--min-policy-coverage",type=float,default=.05)
    p.add_argument("--target-exact",type=float,default=.50); p.add_argument("--target-5s",type=float,default=.60)
    p.add_argument("--target-15s",type=float,default=.75); p.add_argument("--target-60s",type=float,default=.90)
    p.add_argument("--output",default="reports/japan_xanax_window_regime_longform")
    a=p.parse_args(); a.travel=round(a.travel_minutes*60); a.waitmax=round(a.max_wait_minutes*60)
    a.step=a.departure_grid_seconds; a.graces=[int(x) for x in a.grace_seconds.split(",")]
    hs.DB_PATH=Path(a.db)
    ws=build_windows(a.country,a.item,a.min_quantity); rows=build_samples(ws)
    if len(rows)<a.min_train_cycles+20: raise SystemExit(f"Only {len(rows)} usable P2 samples")
    split=max(a.min_train_cycles,int(len(rows)*(1-a.holdout_fraction))); split=min(split,len(rows)-1)
    lbs=[None if x=="all" else int(x) for x in a.lookbacks.split(",")]
    cuts=[None if float(x)==0 else float(x)*60 for x in a.width_thresholds.split(",")]
    bins=[int(x) or None for x in a.tod_bins.split(",")]
    confs=[None if float(x)==0 else float(x) for x in a.confidence_thresholds.split(",")]
    cfgs=[{"lb":lb,"width_cut":cut,"tod_bins":b,"conf":c,"min_analogs":a.min_analogs}
          for lb in lbs for cut in cuts for b in bins for c in confs]
    print(f"windows={len(ws)} p2_samples={len(rows)} train={split} holdout={len(rows)-split} configs={len(cfgs)}",flush=True)
    v0=max(a.min_train_cycles,int(split*.65)); scored=[]
    for z,cfg in enumerate(cfgs,1):
        r=evaluate(rows,v0,split,cfg,a); n=r["n"]; rr=r["rates"]
        if r["coverage"]<a.min_policy_coverage or n<5: continue
        gates=(rr.get(0,0)>a.target_exact,rr.get(5,0)>=a.target_5s,rr.get(15,0)>=a.target_15s,rr.get(60,0)>=a.target_60s)
        prefix=0
        for ok in gates:
            if ok: prefix+=1
            else: break
        score=(prefix,rr.get(60,0),rr.get(15,0),rr.get(5,0),rr.get(0,0),r["coverage"])
        scored.append((score,cfg,r))
        if z%100==0: print(f"validated {z}/{len(cfgs)}",flush=True)
    if not scored: raise SystemExit("No eligible configurations; reduce --min-policy-coverage or --min-analogs")
    scored.sort(key=lambda x:x[0],reverse=True)
    chosen=scored[0]; hold=evaluate(rows,split,len(rows),chosen[1],a)
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    report={"schema":"japan-xanax-window-regime-longform-v1","created_at":int(time.time()),"db":str(a.db),
      "windows":len(ws),"p2_samples":len(rows),"train_n":split,"holdout_n":len(rows)-split,
      "targets":{"exact":a.target_exact,"5s":a.target_5s,"15s":a.target_15s,"60s":a.target_60s},
      "selected_config":chosen[1],
      "validation":{k:v for k,v in chosen[2].items() if k!="records"},
      "holdout":{k:v for k,v in hold.items() if k!="records"},
      "top_validation":[{"config":c,"metrics":{k:v for k,v in r.items() if k!="records"}} for _,c,r in scored[:25]]}
    out.with_suffix(".json").write_text(json.dumps(report,indent=2))
    with out.with_suffix(".csv").open("w",newline="") as f:
        w=csv.writer(f); w.writerow(["sample","wait_s","analogs"]+[f"hit_{g}s" for g in a.graces]+["target_width_s"])
        for r in hold["records"]: w.writerow([r["i"],r["wait_s"],r["analogs"]]+[r["actual"][g] for g in a.graces]+[r["target_width_s"]])
    print("\n=== SELECTED ON TRAINING/VALIDATION ONLY ==="); print(json.dumps(chosen[1],indent=2))
    print("VALIDATION",json.dumps({k:v for k,v in chosen[2].items() if k!="records"},indent=2))
    print("\n=== LOCKED HOLDOUT ==="); print(json.dumps({k:v for k,v in hold.items() if k!="records"},indent=2))
    print(f"\nSaved {out.with_suffix('.json')} and {out.with_suffix('.csv')}",flush=True)

if __name__=="__main__": main()
