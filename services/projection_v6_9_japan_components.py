import argparse
import json
import math
import statistics
from pathlib import Path

from services.projection_engine_v4 import build_item_context


GAP_METHODS = (
    "last1","last2_mean","last3_mean","last5_mean","last5_median",
    "last10_median","all_median"
)
LIFE_METHODS = (
    "last1","last2_mean","last3_mean","last3_median","last5_median","all_median"
)


def _valid(c):
    return (
        c.get("restock_time") is not None
        and c.get("depletion_time") is not None
        and float(c["depletion_time"]) > float(c["restock_time"])
        and not c.get("_excluded_regime")
        and c.get("_valid_for_training", True)
    )


def _est(vals, method):
    if not vals:
        return None
    if method == "last1": return float(vals[-1])
    if method == "last2_mean": return float(statistics.mean(vals[-2:]))
    if method == "last3_mean": return float(statistics.mean(vals[-3:]))
    if method == "last5_mean": return float(statistics.mean(vals[-5:]))
    if method == "last3_median": return float(statistics.median(vals[-3:]))
    if method == "last5_median": return float(statistics.median(vals[-5:]))
    if method == "last10_median": return float(statistics.median(vals[-10:]))
    if method == "all_median": return float(statistics.median(vals))
    raise ValueError(method)


def _wilson(h, n, z=1.959963984540054):
    if n <= 0: return None
    p=h/n
    den=1+z*z/n
    center=p+z*z/(2*n)
    margin=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)
    return (center-margin)/den


def rows_for(ctx, gap_method, life_method, max_depth=5):
    rows=[]
    cycles=ctx.cycles
    for anchor_i, anchor in enumerate(cycles):
        if anchor_i < 1 or not _valid(anchor): continue
        gaps=[]; lives=[]
        for j in range(1, anchor_i+1):
            prev, cur = cycles[j-1], cycles[j]
            if not (_valid(prev) and _valid(cur)): continue
            gap=float(cur["restock_time"])-float(prev["depletion_time"])
            life=float(cur["depletion_time"])-float(cur["restock_time"])
            if gap>0 and life>0:
                gaps.append(gap); lives.append(life)
        if len(gaps) < ctx.min_history or len(lives) < ctx.min_history: continue
        ge=_est(gaps,gap_method); le=_est(lives,life_method)
        if not ge or not le: continue
        anchor_ts=float(anchor["depletion_time"])
        for depth in range(1,max_depth+1):
            ti=anchor_i+depth
            if ti>=len(cycles): break
            target=cycles[ti]
            if not _valid(target): continue
            predicted_r=anchor_ts + depth*ge + (depth-1)*le
            depart=predicted_r-float(ctx.travel_seconds) if ctx.travel_seconds else None
            actionable=depart is not None and depart>=anchor_ts
            ar=float(target["restock_time"]); ad=float(target["depletion_time"])
            rows.append({
                "anchor_timestamp":int(anchor_ts),"depth":depth,
                "gap_method":gap_method,"life_method":life_method,
                "gap_estimate_seconds":ge,"lifetime_estimate_seconds":le,
                "predicted_restock_timestamp":predicted_r,
                "recommended_departure_timestamp":depart,
                "actionable_from_anchor":int(actionable),
                "arrival_hit":int(ar<=predicted_r<ad),
                "early_arrival":int(predicted_r<ar),
                "late_arrival":int(predicted_r>=ad),
                "abs_error":abs(ar-predicted_r),
            })
    return rows


def summarize(rows):
    a=[r for r in rows if r["actionable_from_anchor"]]
    n=len(a)
    if not n:
        return {"actionable_n":0,"hit_rate":None,"wilson_lower_95":None,
                "early_rate":None,"late_rate":None,"median_abs_error_seconds":None}
    h=sum(r["arrival_hit"] for r in a)
    return {
        "actionable_n":n,"hit_rate":h/n,"wilson_lower_95":_wilson(h,n),
        "early_rate":sum(r["early_arrival"] for r in a)/n,
        "late_rate":sum(r["late_arrival"] for r in a)/n,
        "median_abs_error_seconds":statistics.median(r["abs_error"] for r in a),
    }


def active(rows):
    grouped={}
    for r in rows: grouped.setdefault(r["anchor_timestamp"],[]).append(r)
    out=[]
    for g in grouped.values():
        rr=sorted((r for r in g if r["actionable_from_anchor"]),key=lambda x:x["depth"])
        if rr: out.append(rr[0])
    return out


def main():
    p=argparse.ArgumentParser(description="V6.9 Japan component-decoupled gap/lifetime tournament")
    p.add_argument("country", nargs="?", default="jap")
    p.add_argument("item_name", nargs="?", default="Xanax")
    p.add_argument("--depth",type=int,default=5)
    p.add_argument("--output",default="data/projection_v6_9_japan_components.json")
    a=p.parse_args()

    ctx=build_item_context(a.country.lower(),a.item_name,max_depth=max(2,a.depth),min_history=8)
    target=0.75 if a.item_name.lower()=="xanax" else 0.80
    candidates=[]
    for gm in GAP_METHODS:
        for lm in LIFE_METHODS:
            rows=rows_for(ctx,gm,lm,max_depth=max(2,a.depth))
            train=[r for r in rows if r["anchor_timestamp"]<ctx.split_timestamp]
            hold=[r for r in rows if r["anchor_timestamp"]>=ctx.split_timestamp]
            ts=summarize(active(train)); hs=summarize(active(hold))
            n=int(ts.get("actionable_n") or 0); rate=ts.get("hit_rate")
            valid=bool(rate is not None and n>=20 and rate>=target)
            candidates.append({
                "gap_method":gm,"life_method":lm,
                "valid_on_train":valid,"train_active":ts,"holdout_active":hs,
            })
    candidates.sort(key=lambda c:(
        int(c["valid_on_train"]),
        c["train_active"].get("wilson_lower_95") or 0,
        c["train_active"].get("hit_rate") or 0,
        c["train_active"].get("actionable_n") or 0
    ),reverse=True)
    report={
        "country":a.country.lower(),"item_name":a.item_name,
        "target":target,"valid_cycles":len(ctx.cycles),
        "selected_on_train":candidates[0] if candidates else None,
        "top20":candidates[:20],
        "note":"Gap and stock-lifetime estimators are selected independently. Holdout is never used for selection."
    }
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    print(f"\nSaved full report to {out}")


if __name__=="__main__":
    main()
