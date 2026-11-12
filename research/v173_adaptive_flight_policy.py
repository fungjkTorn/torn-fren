"""V173 25-item causal RECENCY challenger using frozen V169 as-issued forecasts.

Never calls the original heavy specialists again. Compares unchanged V169
recommendations with causal trailing-completed-cycle / regime-shift challengers,
scoring altered departure times from the separate sanitized SQLite truth data.

The actual history is read for outcomes ONLY after each as-issued decision is
locked. No production services, websites, models, or forward ledgers are altered.
"""
from __future__ import annotations

import argparse
import bisect
from collections import Counter
from contextlib import closing
import json
import hashlib
import math
from pathlib import Path
import sqlite3
from statistics import median

from research.japan_xanax.renewal_shadow import source_data
from research.plushie_champions.common import TRAVEL_SECONDS, GRACE, STEP
from research.v167_all24_live_policy_replay import ROUTES

START=1791504000
END=1792533131
SPECIAL_WINDOWS={"can:Xanax":(300,600),"jap:Xanax":(600,1200,1800)}
STRATEGIES=("V169_INCUMBENT","CURRENT_STOCK_GUARD",
            "V169_BIAS_ADJUSTED","CURRENT_STOCK_GUARD_BIAS",
            "RECENT6","RECENT10","RECENT20","REGIME_AUTO")
RECENCY_N={"RECENT6":6,"RECENT10":10,"RECENT20":20}


def weighted_quantile(values, n, percentile=.5):
    """Decay by completed episodes, not elapsed polls (stable with dense sales)."""
    recent=[float(x) for x in values[-n:] if x>0]
    if len(recent)<3:return None
    half=max(2,n/2)
    weights=[.5**((len(recent)-1-i)/half) for i in range(len(recent))]
    weighted=sorted(zip(recent,weights))
    threshold=percentile*sum(weights)
    total=0.
    for value,weight in weighted:
        total+=weight
        if total>=threshold:return value
    return weighted[-1][0]


class CausalCycles:
    """Advance a single source row at a time; only completed cycles train."""
    def __init__(self,rows,gaps_crosses):
        self.rows=rows
        self.crosses=gaps_crosses
        self.pos=0
        self.last=None
        self.high_start=None
        self.zero_start=None
        self.last_physical=None
        self.available_durations=[]
        self.zero_durations=[]
        self.restock_intervals=[]
        self.stock_openings=[]
        self.stock_data_drift_alerts=0

    def advance(self,issued):
        while self.pos<len(self.rows) and self.rows[self.pos][0]<=issued:
            t,q,provider=self.rows[self.pos]
            prev=self.last
            if prev is None or prev[2]!=provider or self.crosses(prev[0],t):
                # A provider change/gap must not manufacture a restock cycle.
                # An observation at the beginning of coverage or following
                # a provider switch/gap is left-censored, not a phase onset.
                self.high_start=None
                self.zero_start=None
                self.last_physical=None
            else:
                pt,pq,_=prev
                if pq<30<=q:
                    self.high_start=t
                    # Opening threshold is not automatically a physical restock.
                    if pq==0:self.stock_openings.append(t)
                if pq>=30>q:
                    if self.high_start is not None and t>self.high_start:
                        self.available_durations.append(t-self.high_start)
                    self.high_start=None
                if pq>0 and q==0:
                    self.zero_start=t
                if pq==0 and q>0:
                    if self.last_physical is not None and t>self.last_physical:
                        self.restock_intervals.append(t-self.last_physical)
                    self.last_physical=t
                    if self.zero_start is not None and t>self.zero_start:
                        self.zero_durations.append(t-self.zero_start)
                    self.zero_start=None
            self.last=(t,q,provider)
            self.pos+=1

    def regime(self):
        signals=0
        for xs in (self.restock_intervals,self.available_durations,
                   self.zero_durations):
            if len(xs)>=14:
                recent=median(xs[-6:])
                older=median(xs[-24:-6])
                if older>0 and not .78<=recent/older<=1.25:
                    signals+=1
        return signals>0

    def viable_current(self,issued,flight,n,required=.65):
        if self.last is None or self.last[1]<30 or self.high_start is None:
            return False
        values=self.available_durations[-n:]
        if len(values)<5:return False
        age=issued-self.high_start
        # Kaplan-Meier-like conservative at-risk empirical check:
        # finished cycles <= age cannot survive the full required flight.
        success=sum(duration>=age+flight+GRACE for duration in values)
        return success/len(values)>=required

    def next_departure(self,issued,flight,n,buffer_seconds=0,conservative=False):
        if self.last is None:return None,None
        intervals=self.restock_intervals
        durations=self.available_durations
        if len(intervals)<4 or len(durations)<4:
            return None,None
        period=weighted_quantile(intervals,n,.5)
        lifetime=weighted_quantile(durations,n,.25 if conservative else .5)
        if period is None or lifetime is None:
            return None,None
        if self.last[1]==0 and self.zero_start is not None:
            low=weighted_quantile(self.zero_durations,n,.5)
            if low is not None:
                remaining=[x-(issued-self.zero_start)
                           for x in self.zero_durations[-n:]
                           if x>issued-self.zero_start]
                target=issued+(median(remaining) if len(remaining)>=3
                               else max(60,low-(issued-self.zero_start)))
            else:
                target=None
        else:
            target=None
        if target is None:
            if self.last_physical is None:return None,None
            elapsed=max(0,issued-self.last_physical)
            remaining=[x-elapsed for x in intervals[-n:] if x>elapsed]
            target=issued+(median(remaining) if len(remaining)>=3
                           else max(60,self.last_physical+period-issued))
        # If current restock remains in stock, it is still valid to launch
        # toward NEXT restock. No requirement to wait for current depletion.
        # Guard against runway violations without applying a product 8h cap.
        for _ in range(8):
            landing=max(issued,target+buffer_seconds-flight)+flight
            if landing+GRACE<target+lifetime:
                dep=max(issued,math.ceil(target+buffer_seconds-flight))
                return dep,int(target)
            target+=period
        return None,None


def historical_openings(rows,crosses):
    """Provider-continuous 0 -> >=30 direct openings for *grading only*."""
    output=[]
    for prev,cur in zip(rows,rows[1:]):
        if (prev[1]==0 and cur[1]>=30 and prev[2]==cur[2]
                and not crosses(prev[0],cur[0])):
            output.append(cur[0])
    return output


def wait_window_grade(arrival,state,windows,openings,evidence):
    """Secondary 'could wait' categories, never inflate landing success.

    Confirmation is >=30 stock at a supported poll-backed point after opening.
    If too few polls confirm a claimed restock, status remains unknown.
    """
    if not windows:return {}
    if state=="SUCCESS":
        return {str(w):"ARRIVAL_SUCCESS_NOT_WAIT" for w in windows}
    if state not in ("FAILURE",):
        return {str(w):"UNKNOWN_ARRIVAL" for w in windows}
    first=bisect.bisect_right(openings,arrival)
    if first>=len(openings) or openings[first]-arrival>max(windows):
        return {str(w):"NO_QUALIFYING_RESTOCK" for w in windows}
    opening=openings[first]
    # 0->>=30 observation proves a stock opportunity at a point in time;
    # a poll-backed independent check avoids trusting a one-line anomaly.
    observed=evidence.score(opening+120)[0]
    if observed=="SUCCESS":
        return {str(w):("POST_ARRIVAL_RESTOCK_WITHIN_WINDOW"
                if opening-arrival<=w else "NO_QUALIFYING_RESTOCK") for w in windows}
    if observed in ("UNKNOWN","PENDING"):
        return {str(w):("UNCONFIRMED_RESTOCK_EVIDENCE"
                if opening-arrival<=w else "NO_QUALIFYING_RESTOCK") for w in windows}
    return {str(w):"RESTOCK_SEEN_BUT_STOCK_SOLD_OUT" if opening-arrival<=w
            else "NO_QUALIFYING_RESTOCK" for w in windows}


def fit_restock_bias(records,fit_end,flight):
    """Frozen event-level timing calibration using only matured EARLIER outcomes.

    Deduplicate five-minute forecast updates by observed target event. Never
    treat 400 correlated issue rows as 400 independent restock training labels.
    Restrict to events that physically occurred before the fixed fit boundary.
    This stage is NOT used to score or select a model. Selection uses the next
    chronological slice and final holdout remains untouched.
    """
    by_event={}
    for rec in records:
        issued=rec["issued_epoch"]
        if issued>=fit_end-flight-180:break
        event=rec.get("selected_event") or {}
        predicted=event.get("predicted_restock_epoch")
        actual=rec.get("actual_target_restock_epoch")
        if (not isinstance(predicted,int) or not isinstance(actual,int)
            or event.get("event_index",0)<1
            or actual>fit_end or actual<=issued
            or abs(actual-predicted)>3*3600):
            continue
        # Earliest historical issued forecast per independent restock target.
        if actual not in by_event:
            by_event[actual]=actual-predicted
    deltas=list(by_event.values())
    if len(deltas)<4:
        return {"offset_seconds":0,"independent_events":len(deltas),
                "supported":False,"fit_before_epoch":fit_end}
    value=int(max(-1800,min(1800,round(median(deltas)/60)*60)))
    return {"offset_seconds":value,"independent_events":len(deltas),
            "supported":True,"fit_before_epoch":fit_end}


def plan_at_issue(name,rec,clock,flight,bias_seconds=0):
    issued=rec["issued_epoch"]
    legacy=rec.get("recommended_departure_epoch")
    event=rec.get("selected_event")
    if name in ("V169_INCUMBENT","V169_BIAS_ADJUSTED",
                "CURRENT_STOCK_GUARD","CURRENT_STOCK_GUARD_BIAS"):
        guard=name in ("CURRENT_STOCK_GUARD","CURRENT_STOCK_GUARD_BIAS")
        use_bias=name in ("V169_BIAS_ADJUSTED","CURRENT_STOCK_GUARD_BIAS")
        if guard and event and event.get("event_index")==0 and legacy is not None:
            if not clock.viable_current(issued,flight,10):
                # UNIVERSAL RULE: leave during any currently stocked phase
                # if the NEXT predicted replenishment will be reachable.
                return clock.next_departure(issued,flight,10,
                                            buffer_seconds=180,conservative=True)
        if use_bias and event and event.get("event_index",0)>=1 and legacy is not None:
            p=event.get("predicted_restock_epoch")
            if isinstance(p,int):
                return max(issued,legacy+bias_seconds),p+bias_seconds
        return legacy,("CURRENT" if event and event.get("event_index")==0
                       else event.get("predicted_restock_epoch") if event else None)
    n=RECENCY_N.get(name,6 if clock.regime() else 20)
    if event and event.get("event_index")==0:
        if clock.viable_current(issued,flight,n,
                               required=.7 if name=="REGIME_AUTO" else .6):
            return issued,"CURRENT"
    return clock.next_departure(
        issued,flight,n,buffer_seconds=(120 if name in ("RECENT6","REGIME_AUTO")
                                       else 300 if name=="RECENT10" else 600),
        conservative=name in ("RECENT6","REGIME_AUTO"))


def find_original_report(root,key,start,end,south_report=None):
    p=Path(root).expanduser().resolve(strict=True)
    filename=key.replace(":","__").replace(" ","_")+".json"
    if key=="sou:Xanax" and south_report is not None:
        options=[Path(south_report).expanduser().resolve(strict=True)]
    else:
        options=list(p.rglob(filename))
    matches=[]
    for f in options:
        try:
            d=json.loads(f.read_text(encoding="utf-8"))
            if d.get("item_key")==key and d.get("start")==start and d.get("end")==end:
                matches.append((f,d))
        except (ValueError,OSError):
            pass
    if not matches:
        raise FileNotFoundError("No exact-window as-issued V169 report for "+key+
                                " under "+str(p))
    # Do not guess among incompatible duplicate source reports.
    if len(matches)>1 and len({m[0].read_bytes() for m in matches})>1:
        raise ValueError("Multiple different baseline reports for "+key)
    return matches[0][1]


def summary(counts,windows):
    n=counts["issues"]
    known=counts["arrival_success"]+counts["arrival_failure"]
    out={"issues":n,"proposals":counts["proposals"],
         "executions":counts["executions"],
         "arrival_known":known,
         "arrival_success":counts["arrival_success"],
         "arrival_failure":counts["arrival_failure"],
         "arrival_unknown":counts["arrival_unknown"],
         "proposal_coverage":counts["proposals"]/n if n else None,
         "arrival_success_fraction":counts["arrival_success"]/known if known else None,
         "success_per_issue":counts["arrival_success"]/n if n else None}
    for seconds in windows:
        success=counts[f"wait_{seconds}_success"]
        out[f"wait_{seconds}_seconds_extra_success"]=success
        out[f"landing_or_wait_{seconds}_seconds_success_fraction"]=(
            (counts["arrival_success"]+success)/known if known else None)
        out[f"landing_or_wait_{seconds}_seconds_success_per_issue"]=(
            (counts["arrival_success"]+success)/n if n else None)
        out[f"wait_{seconds}_seconds_unknown"]=counts[f"wait_{seconds}_unknown"]
    return out


def rank(d,windows=()):
    # Minimum coverage/denominator is essential; don't choose a model from
    # 5 successes out of just 5 heavily cherry-picked opportunities.
    enough=(d["proposals"]>=max(12,d["issues"]*.1)
            and d["arrival_known"]>=20
            and d["executions"]>=25)
    # For Canada/Japan ONLY, prioritize stocked landing OR qualified next
    # restock within the largest explicitly accepted waiting window.
    # Other items keep the landing-only objective.
    union=(d.get(f"landing_or_wait_{max(windows)}_seconds_success_per_issue")
           if windows else d["success_per_issue"])
    return (int(enough), union or 0,
            d["success_per_issue"] or 0,
            d["arrival_success_fraction"] or 0,
            d["proposal_coverage"] or 0)


def release_gate(name,incumbent,challenger,windows):
    """Choose keep-or-propose one fixed development-selected challenger.

    This is an offline recommendation, NOT automatic deployment. The final
    chronological holdout is evaluated once, after all configuration choices
    are locked. A promotion requires meaningful per-issue improvement while
    retaining adequate on-landing reliability and comparable coverage.
    """
    if name=="V169_INCUMBENT":
        return {"policy":"V169_INCUMBENT","decision":"KEEP_BASELINE_SELECTED",
                "deploy_automatically":False}
    suffix=f"landing_or_wait_{max(windows)}_seconds_success_per_issue" if windows else "success_per_issue"
    a=incumbent.get(suffix);b=challenger.get(suffix)
    if (a is None or b is None or
        challenger.get("arrival_known",0)<30 or
        challenger.get("executions",0)<30 or
        challenger.get("proposal_coverage",0)<.25):
        return {"policy":"V169_INCUMBENT","decision":"RETAIN_INSUFFICIENT_HOLDOUT",
                "metric":suffix,"deploy_automatically":False}
    n0=incumbent.get("arrival_success_fraction")
    n1=challenger.get("arrival_success_fraction")
    if n0 is None or n1 is None or n1<n0-.03:
        return {"policy":"V169_INCUMBENT","decision":"RETAIN_STOCKED_ARRIVAL_RELIABILITY",
                "metric":suffix,"deploy_automatically":False}
    if b<a+.005 or challenger["proposal_coverage"]<.75*incumbent["proposal_coverage"]:
        return {"policy":"V169_INCUMBENT","decision":"RETAIN_NO_MEANINGFUL_GAIN",
                "metric":suffix,"holdout_metric_delta":round(b-a,6),
                "deploy_automatically":False}
    return {"policy":name,"decision":"CHALLENGER_CANDIDATE_FOR_LIVE_REVIEW",
            "metric":suffix,"holdout_metric_delta":round(b-a,6),
            "deploy_automatically":False}


def replay_item(source,report,key,start,end):
    if report["item_key"]!=key or report["start"]!=start or report["end"]!=end:
        raise ValueError("as-issued baseline identity/window mismatch")
    rows,polls,crosses,evidence,cutoff=source_data(source,item_key=key)
    flight=TRAVEL_SECONDS[key.split(":",1)[0]]
    if end+flight+GRACE+180>cutoff:
        raise ValueError("historical arrival observations immature: "+key)
    records=report["records"]
    if not records or records[0]["issued_epoch"]!=start:
        raise ValueError("missing first baseline as-issued observation")
    clock=CausalCycles(rows,crosses)
    # Grade truth labels from full history but never give openings to a plan.
    opening_evidence=historical_openings(rows,crosses)
    windows=SPECIAL_WINDOWS.get(key,())
    fit_end=start+int(.3*(end-start))
    split=start+int(.6*(end-start))
    bias=fit_restock_bias(records,fit_end,flight)
    counters={stage:{name:Counter() for name in STRATEGIES}
              for stage in ("development","validation")}
    prev={name:None for name in STRATEGIES}
    flags=0
    for i,rec in enumerate(records):
        issued=rec["issued_epoch"]
        if issued<start or issued>end:raise ValueError("baseline timestamp outside fixed split")
        if i and issued!=records[i-1]["issued_epoch"]+STEP:
            raise ValueError("not an uninterrupted five-minute issue tape")
        clock.advance(issued)
        flags+=int(clock.regime())
        stage=("calibration" if issued<fit_end else
               "development" if issued<split else "validation")
        if stage=="calibration":
            # Calibration is not a selection score. The model is fitted on
            # just this earlier 30%, and all finalist comparisons start later.
            continue
        for name in STRATEGIES:
            c=counters[stage][name]
            c["issues"]+=1
            dep,target=plan_at_issue(
                name,rec,clock,flight,bias_seconds=bias["offset_seconds"])
            if dep is None:continue
            if dep<issued:raise ValueError("proposed departure before issuance")
            c["proposals"]+=1
            if not issued<=dep<issued+STEP:
                prev[name]=(issued,target)
                continue
            if name in ("V169_INCUMBENT","CURRENT_STOCK_GUARD",
                        "V169_BIAS_ADJUSTED","CURRENT_STOCK_GUARD_BIAS") and (
                name=="V169_INCUMBENT" or
                (rec.get("selected_event") and rec["selected_event"].get("event_index")!=0)
            ) and dep==rec.get("recommended_departure_epoch"):
                confirmed=(rec.get("target_stable_from_previous_replan") or
                           (rec.get("selected_event") or {}).get("event_index")==0)
            else:
                old=prev[name]
                confirmed=(target=="CURRENT" or
                           (old is not None and old[0]==issued-STEP
                            and isinstance(target,(int,float))
                            and isinstance(old[1],(int,float))
                            and abs(target-old[1])<=900))
            prev[name]=(issued,target)
            if not confirmed:continue
            c["executions"]+=1
            arrival=int(dep)+flight
            actual=evidence.score(arrival)[0]
            if actual in ("SUCCESS","FAILURE"):
                c["arrival_"+actual.lower()]+=1
            else:
                c["arrival_unknown"]+=1
            if windows:
                grades=wait_window_grade(arrival,actual,windows,
                                         opening_evidence,evidence)
                for w in windows:
                    if grades[str(w)]=="POST_ARRIVAL_RESTOCK_WITHIN_WINDOW":
                        c[f"wait_{w}_success"]+=1
                    if grades[str(w)] in ("UNKNOWN_ARRIVAL",
                                          "UNCONFIRMED_RESTOCK_EVIDENCE"):
                        c[f"wait_{w}_unknown"]+=1
    reports={stage:{name:summary(c,windows)
                    for name,c in counters[stage].items()}
             for stage in counters}
    # One pre-registered selection using ONLY earlier 60%; no validation
    # winner tuning / retrospective threshold selection.
    chosen=max(STRATEGIES,key=lambda name:rank(reports["development"][name],windows))
    gate=release_gate(chosen,reports["validation"]["V169_INCUMBENT"],
                      reports["validation"][chosen],windows)
    return {
        "item_key":key,"chosen_using_development_only":chosen,
        "recommended_release_policy":gate,
        "incumbent_validation":reports["validation"]["V169_INCUMBENT"],
        "challenger_validation":reports["validation"][chosen],
        "all_policies":reports,"regime_shift_issue_flags":flags,
        "per_item_early_period_event_level_bias":bias,
        "calibration_period_end_epoch":fit_end,
        "selection_period_start_epoch":fit_end,
        "untouched_validation_start_epoch":split,
        "special_post_arrival_wait_windows_seconds":list(windows),
        "model_selection_target":(
            "LANDING_OR_CONFIRMED_RESTOCK_WITHIN_MAX_SPECIAL_WAIT"
            if windows else "STOCKED_ARRIVAL_ONLY"),
        "source_rows":len(rows),"baseline_records":len(records),
        "production_modified":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--v169-root",required=True,
                   help="Folder containing the original 24 V169 reports and separate sou__Xanax")
    p.add_argument("--output",required=True)
    p.add_argument("--south-africa-report",default=None,
                   help="Original separately completed sou__Xanax.json (no copying)")
    p.add_argument("--start-epoch",type=int,default=START)
    p.add_argument("--end-epoch",type=int,default=END)
    p.add_argument("--item-key",action="append")
    a=p.parse_args()
    source=Path(a.source).expanduser().resolve(strict=True)
    keys=sorted(a.item_key or ROUTES)
    if len(set(keys))!=len(keys) or not set(keys)<=set(ROUTES):
        p.error("only unique keys in the original 25-item research roster")
    out=Path(a.output).expanduser().resolve()
    if out.exists():raise FileExistsError("preserve prior experiment; choose a new output")
    out.parent.mkdir(parents=True,exist_ok=True)
    src_stat=source.stat()
    run_code_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
    source_id=hashlib.sha256(
        f"{source}:{src_stat.st_size}:{src_stat.st_mtime_ns}".encode()).hexdigest()[:12]
    # Research checkpoints persist after every completed item. Safe to resume
    # after interruption without repeating completed comparisons or swapping
    # source databases. This is NOT a website or VM write.
    partdir=out.parent/(out.stem+"_parts_"+source_id+"_"+run_code_hash)
    partdir.mkdir(parents=True,exist_ok=True)
    results={}
    for index,key in enumerate(keys,1):
        baseline=find_original_report(
            a.v169_root,key,a.start_epoch,a.end_epoch,
            south_report=a.south_africa_report)
        baseline_fingerprint=hashlib.sha256(
            json.dumps(baseline,sort_keys=True,separators=(",",":")).encode()
        ).hexdigest()
        checkpoint=partdir/(key.replace(":","__").replace(" ","_")+".json")
        identity={"source_id":source_id,"code_id":run_code_hash,
                  "baseline_sha256":baseline_fingerprint,
                  "item_key":key,"start":a.start_epoch,"end":a.end_epoch}
        if checkpoint.exists():
            saved=json.loads(checkpoint.read_text(encoding="utf-8"))
            if saved.get("identity")!=identity:
                raise ValueError("checkpoint identity mismatch: "+str(checkpoint))
            results[key]=saved["result"]
            resumed=True
        else:
            results[key]=replay_item(source,baseline,key,a.start_epoch,a.end_epoch)
            with checkpoint.open("x",encoding="utf-8") as handle:
                json.dump({"identity":identity,"result":results[key]},handle,
                          sort_keys=True)
                handle.write("\n")
            resumed=False
        d=results[key]
        print(json.dumps({"progress":f"{index}/{len(keys)}","item":key,
            "resumed":resumed,"choice":d["chosen_using_development_only"],
            "release_policy":d["recommended_release_policy"]["policy"],
            "incumbent_validation":d["incumbent_validation"]["arrival_success_fraction"],
            "challenger_validation":d["challenger_validation"]["arrival_success_fraction"]},
            sort_keys=True),flush=True)
    result={
        "status":"V173_CAUSAL_25_ITEM_RECENCY_REGIME_ADAPTIVE_REPLAY",
        "start":a.start_epoch,"end":a.end_epoch,"items_requested":len(keys),
        "items_completed":len(results),"split":"FIRST_30_BIAS_CALIBRATION_NEXT_30_SELECTION_LAST_40_UNTOUCHED",
        "source":"SANITIZED_25_ITEM_HISTORICAL_SQLITE",
        "baseline":"V169_AS_ISSUED_FROZEN_FORECASTS",
        "decisions_replanned_every_seconds":STEP,
        "success_requires_at_least_30_stock_at_landing_plus_grace":True,
        "grace_seconds":GRACE,
        "extra_wait_results_are_distinct_from_arrival_success":True,
        "wait_windows_seconds":SPECIAL_WINDOWS,
        "recent_completed_cycle_windows":[6,10,20],
        "per_item_restock_bias_fit":"EARLIER_30_PERCENT_EVENT_DEDUPLICATED_CAPPED_PLUS_MINUS_30_MIN",
        "drift_guard":"LAST6_VS_PRIOR18_MEDIAN_RATIO_OUTSIDE_0.78_TO_1.25",
        "past_outcomes_never_used_to_fit_same_issued_decision":True,
        "selection_never_uses_validation_results":True,
        "holdout_used_once_for_retain_or_propose_gate":True,
        "release_candidates_require_human_review_and_live_producer":True,
        "candidate_results_correlated_by_repeated_decisions":True,
        "not_independent_restock_success_rates":True,
        "per_item_checkpoint_directory":str(partdir),
        "checkpoint_resumable":True,
        "production_modified":False,"results":results}
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("V173_COMPLETE",len(results),"OUTPUT",out,flush=True)


if __name__=="__main__":
    main()
