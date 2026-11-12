from __future__ import annotations
import argparse, json, statistics, time
from pathlib import Path

import services.history_service as hs
from services.japan_xanax_window_regime_longform import build_windows, build_samples


def mean(xs):
    return statistics.mean(xs) if xs else None


def median(xs):
    return statistics.median(xs) if xs else None


def ols_window(window, clean_rows, full_quantity=2500, min_quantity=30):
    start=float(window["start"]); end=float(window["end"])
    pts=[(ts,q) for ts,q,_src in clean_rows if start <= ts <= end]
    live=[(ts,q) for ts,q in pts if q >= min_quantity]
    if not live:
        return None

    def endpoint_fallback():
        first_q=float(live[0][1])
        duration_min=(end-start)/60.0
        if first_q <= 0 or duration_min <= 0:
            return None
        rate=first_q/duration_min
        start_adj=start-((full_quantity-first_q)/rate)*60.0
        end_adj=start+((first_q-min_quantity)/rate)*60.0
        return start_adj,end_adj

    fit=None
    if len(pts) >= 3:
        xs=[(ts-start)/60.0 for ts,_q in pts]
        ys=[float(q) for _ts,q in pts]
        xm=mean(xs); ym=mean(ys)
        den=sum((x-xm)**2 for x in xs)
        if den > 0:
            slope=sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/den
            intercept=ym-slope*xm
            if slope < -1e-9:
                t_full=(float(full_quantity)-intercept)/slope
                t_min=(float(min_quantity)-intercept)/slope
                fit=(start+t_full*60.0,start+t_min*60.0)

    if fit is None:
        fit=endpoint_fallback()
    if fit is None:
        return None

    start_adj,end_adj=fit
    start_adj=min(start,start_adj)
    start_adj=max(start-45*60,start_adj)
    last_live=float(live[-1][0])
    end_adj=max(last_live,min(end,end_adj))
    if end_adj <= start_adj:
        fit=endpoint_fallback()
        if fit is None:
            return None
        start_adj,end_adj=fit
        start_adj=min(start,max(start-45*60,start_adj))
        end_adj=max(last_live,min(end,end_adj))
    if end_adj <= start_adj:
        return None

    return {
        "start":int(round(start_adj)),
        "end":int(round(end_adj)),
        "width":int(round(end_adj-start_adj)),
        "peak":window.get("peak"),
        "observed_start":int(window["start"]),
        "observed_end":int(window["end"]),
        "first_observed_quantity":int(live[0][1]),
    }


def build_adjusted(country,item,min_quantity,full_quantity):
    raw=hs._get_all_item_rows_with_source(country,item)
    clean,_=hs._suppress_provider_bounces(raw)
    observed=build_windows(country,item,min_quantity)
    adjusted=[ols_window(w,clean,full_quantity,min_quantity) for w in observed]
    return observed,adjusted


def strict_rows(observed):
    rows=build_samples(observed)
    return [
        r for r in rows
        if 90*60 <= r["g1"] <= 150*60 and 90*60 <= r["g2"] <= 150*60
    ]


def adjusted_sample(orig, observed, adjusted):
    i=orig["window_index"]
    if i+2 >= len(adjusted) or any(adjusted[j] is None for j in (i,i+1,i+2)):
        return None
    return {
        "window_index":i,
        "decision_anchor":int(observed[i]["end"]),
        "dep_est":int(adjusted[i]["end"]),
        "prev_width":int(adjusted[i]["width"]),
        "target_start":int(adjusted[i+2]["start"]),
        "target_end":int(adjusted[i+2]["end"]),
        "target_width":int(adjusted[i+2]["width"]),
    }


def cooldown_history(observed, adjusted, upto_i):
    out=[]
    for j in range(1,upto_i+1):
        if adjusted[j-1] is None or adjusted[j] is None:
            continue
        c=adjusted[j]["start"]-adjusted[j-1]["end"]
        if 90*60 <= c <= 150*60:
            out.append(c)
    return out


def base_prediction(sample, observed, adjusted):
    i=sample["window_index"]
    cds=cooldown_history(observed,adjusted,i)[-40:]
    if not cds:
        return None
    cooldown_center=mean(cds)
    hist=[adjusted[j]["width"] for j in range(i+1) if adjusted[j] is not None]
    life_pred=.25*adjusted[i]["width"]+.75*mean(hist)
    return sample["dep_est"]+2*cooldown_center+life_pred


def predictions(samples, observed, adjusted, min_train=60):
    base=[base_prediction(s,observed,adjusted) if s else None for s in samples]
    out=list(base)
    for k in range(min_train,len(samples)):
        cur=samples[k]
        if cur is None or base[k] is None:
            continue
        resolved=[
            j for j in range(k)
            if samples[j] is not None and base[j] is not None
            and samples[j]["target_end"] <= cur["decision_anchor"]
        ]
        recent=resolved[-10:]
        if recent:
            residuals=[samples[j]["target_start"]-base[j] for j in recent]
            out[k]=base[k]+.25*median(residuals)
    return out


def hit(sample,arrival,grace=0):
    return arrival+grace >= sample["target_start"] and arrival <= sample["target_end"]


def metrics(samples,preds,indices):
    valid=[k for k in indices if samples[k] is not None and preds[k] is not None]
    n=len(valid)
    rates={}
    for g in (0,5,10,15,60,180,300,600):
        h=sum(hit(samples[k],preds[k],g) for k in valid)
        rates[str(g)]={"hits":h,"n":n,"rate":h/n if n else 0.0}
    return {"n":n,"rates":rates}


def main():
    p=argparse.ArgumentParser(description="Japan Xanax OLS observation-lag V7 research")
    p.add_argument("--db",default="data/stock_history.db")
    p.add_argument("--country",default="jap")
    p.add_argument("--item",default="Xanax")
    p.add_argument("--min-quantity",type=int,default=30)
    p.add_argument("--full-quantity",type=int,default=2500)
    p.add_argument("--min-train-cycles",type=int,default=60)
    p.add_argument("--output",default="reports/japan_xanax_observation_lag_v7")
    a=p.parse_args()
    hs.DB_PATH=Path(a.db)

    observed,adjusted=build_adjusted(a.country,a.item,a.min_quantity,a.full_quantity)
    clean=strict_rows(observed)
    samples=[adjusted_sample(r,observed,adjusted) for r in clean]
    if len(samples) <= a.min_train_cycles:
        raise SystemExit(f"Only {len(samples)} strict samples")

    preds=predictions(samples,observed,adjusted,a.min_train_cycles)
    eval_idx=list(range(a.min_train_cycles,len(samples)))
    mid=len(eval_idx)//2
    first=eval_idx[:mid]
    second=eval_idx[mid:]

    first_q=[w["first_observed_quantity"] for w in adjusted if w is not None]
    obs_width=[w["width"]/60 for w in observed]
    adj_width=[w["width"]/60 for w in adjusted if w is not None]

    report={
        "schema":"japan-xanax-observation-lag-v7",
        "created_at":int(time.time()),
        "development_only":True,
        "full_quantity_assumption":a.full_quantity,
        "clean_strict_samples":len(samples),
        "evaluation_opportunities":len(eval_idx),
        "coverage":1.0,
        "observation_lag":{
            "mean_first_observed_quantity":mean(first_q),
            "median_first_observed_quantity":median(first_q),
            "full_quantity_first_seen_count":sum(q==a.full_quantity for q in first_q),
            "observed_window_median_minutes":median(obs_width),
            "adjusted_window_median_minutes":median(adj_width),
        },
        "model":{
            "cooldown_center":"mean last 40 adjusted cooldowns",
            "lifetime":"25% current adjusted width + 75% historical adjusted mean",
            "residual":"25% median residual of last 10 fully resolved samples",
            "landing_shift_seconds":0,
        },
        "combined":metrics(samples,preds,eval_idx),
        "first_half":metrics(samples,preds,first),
        "later_half":metrics(samples,preds,second),
    }
    out=Path(a.output).with_suffix(".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    print(f"Saved {out}")


if __name__=="__main__":
    main()
