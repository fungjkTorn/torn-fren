from __future__ import annotations
import argparse, json, math, statistics, time
from pathlib import Path

import services.history_service as hs
from services.japan_xanax_window_regime_longform import build_windows, build_samples, hit


def strict_samples(rows, lo=90*60, hi=150*60):
    return [r for r in rows if lo <= r["g1"] <= hi and lo <= r["g2"] <= hi]


def wilson(k, n, z=1.96):
    if not n:
        return [0.0, 0.0]
    p=k/n; d=1+z*z/n
    c=(p+z*z/(2*n))/d
    r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [c-r,c+r]


def width_percentile(windows, sample):
    i=sample["window_index"]
    hist=[w["width"] for w in windows[:i]]
    if not hist:
        return 1.0
    return sum(v <= sample["prev_width"] for v in hist)/len(hist)


def base_prediction(windows, sample):
    i=sample["window_index"]
    cooldowns=[]
    for j in range(1,i+1):
        c=windows[j]["start"]-windows[j-1]["end"]
        if 90*60 <= c <= 150*60:
            cooldowns.append(c)
    cooldowns=cooldowns[-20:]
    center=statistics.mean(cooldowns)
    width_center=statistics.median(w["width"] for w in windows[:i+1])
    return 2*center + .5*windows[i]["width"] + .5*width_center


def build_predictions(windows, rows, min_train=60):
    preds=[None]*len(rows)
    for k,row in enumerate(rows):
        base=base_prediction(windows,row)
        if k < min_train:
            preds[k]=base
            continue
        resolved=[j for j in range(k) if rows[j]["target_end"] <= row["anchor"]]
        recent=resolved[-10:]
        if len(recent) >= 5:
            residuals=[]
            for j in recent:
                old_base=base_prediction(windows,rows[j])
                residuals.append((rows[j]["target_start"]-rows[j]["anchor"])-old_base)
            base += .5*statistics.median(residuals)
        preds[k]=base
    return preds


def profile(rows, windows, preds, min_train, width_floor, recent20_ceiling):
    prior_hit=[False]*len(rows)
    selected=[]
    for k,row in enumerate(rows):
        arrival=row["anchor"]+preds[k]
        prior_hit[k]=hit(row,arrival,0)
        if k < min_train:
            continue
        resolved=[j for j in range(k) if rows[j]["target_end"] <= row["anchor"]]
        if not resolved:
            continue
        recent=resolved[-20:]
        recent_exact=sum(prior_hit[j] for j in recent)/len(recent)
        if width_percentile(windows,row) < width_floor:
            continue
        if recent_exact > recent20_ceiling:
            continue
        selected.append(k)

    rates={}
    for grace in [0,5,15,60,180]:
        hits=sum(hit(rows[k],rows[k]["anchor"]+preds[k],grace) for k in selected)
        rates[str(grace)]={"hits":hits,"n":len(selected),"rate":hits/len(selected) if selected else 0.0}

    eval_n=max(1,len(rows)-min_train)
    first=rows[min_train]["anchor"]; last=rows[-1]["anchor"]
    days=max((last-first)/86400,1e-9)
    blocks=[]
    span=len(rows)-min_train
    cuts=[min_train+round(span*i/4) for i in range(5)]
    for lo,hi in zip(cuts,cuts[1:]):
        ks=[k for k in selected if lo <= k < hi]
        n=len(ks)
        blocks.append({
            "range":[lo,hi],
            "n":n,
            "coverage":n/max(1,hi-lo),
            "exact":sum(hit(rows[k],rows[k]["anchor"]+preds[k],0) for k in ks)/n if n else None,
            "3m":sum(hit(rows[k],rows[k]["anchor"]+preds[k],180) for k in ks)/n if n else None,
        })
    return {
        "width_percentile_floor":width_floor,
        "recent20_exact_ceiling":recent20_ceiling,
        "n":len(selected),
        "coverage":len(selected)/eval_n,
        "recommendations_per_day":len(selected)/days,
        "rates":rates,
        "wilson_exact":wilson(rates["0"]["hits"],len(selected)),
        "wilson_3m":wilson(rates["180"]["hits"],len(selected)),
        "blocks":blocks,
    }


def main():
    p=argparse.ArgumentParser(description="Japan Xanax causal confidence frontier V6")
    p.add_argument("--db",default="data/stock_history.db")
    p.add_argument("--country",default="jap")
    p.add_argument("--item",default="Xanax")
    p.add_argument("--min-quantity",type=int,default=30)
    p.add_argument("--min-train-cycles",type=int,default=60)
    p.add_argument("--output",default="reports/japan_xanax_confidence_frontier_v6")
    a=p.parse_args()
    hs.DB_PATH=Path(a.db)
    windows=build_windows(a.country,a.item,a.min_quantity)
    rows=strict_samples(build_samples(windows))
    if len(rows) <= a.min_train_cycles:
        raise SystemExit(f"Only {len(rows)} strict samples")
    preds=build_predictions(windows,rows,a.min_train_cycles)
    report={
        "schema":"japan-xanax-confidence-frontier-v6",
        "created_at":int(time.time()),
        "development_only":True,
        "strict_clean_samples":len(rows),
        "evaluation_samples":len(rows)-a.min_train_cycles,
        "profiles":{
            "balanced":profile(rows,windows,preds,a.min_train_cycles,.17,.55),
            "high_confidence":profile(rows,windows,preds,a.min_train_cycles,.15,.50),
        },
        "notes":[
            "Collector-gap and provider-bounce cleaning comes from the shared window builder.",
            "Both cooldowns must be 90-150 minutes.",
            "Recent exact rate uses only prior predictions whose target windows fully resolved before the current anchor.",
            "Final validation still requires new frozen future data."
        ],
    }
    out=Path(a.output).with_suffix(".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    print(f"Saved {out}")


if __name__=="__main__":
    main()
