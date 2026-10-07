from __future__ import annotations
import argparse, json, math, statistics, time
from pathlib import Path
import services.history_service as hs
from services.japan_xanax_window_regime_longform import build_windows, build_samples, hit

def wrate(vals, decay):
    if not vals: return 0.0
    if decay >= .999999: return sum(vals)/len(vals)
    n=len(vals); ws=[decay**(n-1-i) for i in range(n)]
    return sum(v*w for v,w in zip(vals,ws))/sum(ws)

def pool_for(train, cur, lb, band):
    p=train[-lb:] if lb else train
    if band is not None:
        den=max(60.0,cur["prev_width"])
        q=[x for x in p if abs(x["prev_width"]-cur["prev_width"])/den <= band]
        if len(q)>=8: p=q
    return p

def predict(train,cur,a,cfg):
    pool=pool_for(train,cur,cfg["lb"],cfg["band"])
    if len(pool)<8:return None
    best=None
    for wait in range(0,a.waitmax+1,a.step):
        probs={}
        for g in a.graces:
            vals=[int(hit(x,x["anchor"]+a.travel+wait,g)) for x in pool]
            probs[g]=wrate(vals,cfg["decay"])
        # Main product objective = <=3m. Exact breaks near-ties.
        score=(probs.get(180,0),probs.get(60,0),probs.get(15,0),probs.get(0,0),-wait)
        if best is None or score>best["score"]:
            best={"wait":wait,"probs":probs,"score":score,"n":len(pool)}
    return best

def evaluate(rows,lo,hi,a,cfg):
    rec=[]
    for i in range(lo,hi):
        p=predict(rows[:i],rows[i],a,cfg)
        if not p:continue
        arr=rows[i]["anchor"]+a.travel+p["wait"]
        rec.append({"i":i,"wait":p["wait"],"pred":p["probs"],
                    "actual":{g:int(hit(rows[i],arr,g)) for g in a.graces}})
    n=len(rec)
    return {"n":n,"coverage":n/max(1,hi-lo),
            "rates":{g:(sum(r["actual"][g] for r in rec)/n if n else 0) for g in a.graces},
            "records":rec}

def main():
    p=argparse.ArgumentParser(description="Japan Xanax high-coverage arrival optimizer")
    p.add_argument("--db",default="data/stock_history.db");p.add_argument("--country",default="jap");p.add_argument("--item",default="Xanax")
    p.add_argument("--travel-minutes",type=float,default=149);p.add_argument("--min-quantity",type=int,default=30)
    p.add_argument("--grace-seconds",default="0,5,15,60,180");p.add_argument("--lookbacks",default="15,20,30,40,60,all")
    p.add_argument("--width-bands",default="0,0.25,0.5,0.75,1.0");p.add_argument("--decays",default="0.90,0.94,0.97,0.99,1.0")
    p.add_argument("--departure-grid-seconds",type=int,default=15);p.add_argument("--max-wait-minutes",type=int,default=240)
    p.add_argument("--min-train-cycles",type=int,default=60);p.add_argument("--folds",type=int,default=6)
    p.add_argument("--output",default="reports/japan_xanax_high_coverage_v4")
    a=p.parse_args();a.travel=round(a.travel_minutes*60);a.waitmax=round(a.max_wait_minutes*60);a.step=a.departure_grid_seconds
    a.graces=[int(x) for x in a.grace_seconds.split(",")];hs.DB_PATH=Path(a.db)
    rows=build_samples(build_windows(a.country,a.item,a.min_quantity)); start=a.min_train_cycles
    lbs=[None if x=="all" else int(x) for x in a.lookbacks.split(",")]
    bands=[None if float(x)==0 else float(x) for x in a.width_bands.split(",")]
    decays=[float(x) for x in a.decays.split(",")]
    cfgs=[{"lb":l,"band":b,"decay":d} for l in lbs for b in bands for d in decays]
    span=len(rows)-start; bounds=[(start+round(span*f/a.folds),start+round(span*(f+1)/a.folds)) for f in range(a.folds)]
    out=[]
    print(f"samples={len(rows)} configs={len(cfgs)} folds={a.folds}",flush=True)
    for z,c in enumerate(cfgs,1):
        rs=[evaluate(rows,lo,hi,a,c) for lo,hi in bounds]
        n=sum(r["n"] for r in rs); coverage=n/span
        if n==0:continue
        rates={g:sum(r["rates"][g]*r["n"] for r in rs)/n for g in a.graces}
        floors={g:min((r["rates"][g] for r in rs if r["n"]),default=0) for g in a.graces}
        # High coverage first; among practical coverage, maximize 3m then exact.
        score=(int(coverage>=.95),rates.get(180,0),rates.get(0,0),rates.get(60,0),floors.get(180,0),coverage)
        out.append((score,c,{"n":n,"coverage":coverage,"rates":rates,"fold_floors":floors,"folds":[{k:v for k,v in r.items() if k!="records"} for r in rs]}))
        if z%25==0:print(f"tested {z}/{len(cfgs)}",flush=True)
    out.sort(key=lambda x:x[0],reverse=True)
    top=[{"config":c,"metrics":m} for _,c,m in out[:40]]
    path=Path(a.output).with_suffix(".json");path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({"schema":"japan-xanax-high-coverage-v4","created_at":int(time.time()),"development_only":True,"top":top},indent=2))
    print(json.dumps(top[:10],indent=2));print(f"Saved {path}")

if __name__=="__main__":main()
