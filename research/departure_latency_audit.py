"""Fixed publication-delay diagnostic, not a model or deployment promotion.

Every five-minute issued plan is assessed separately. These are NOT the
all-start trip/replanning cohorts: future plans need another check. The late
execution arm is an explicitly unsafe counterfactual until validated; it does
not change the strict point recommendation used by the website.
"""
import argparse
import bisect
import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from research.continuous_departure_replay import ArrivalEvidence,MAX_POLLS,model
from research.causal_stock_paths import CausalStockPaths
from research.true_zero_cycles import ZeroCycles
from research.build_travel_event_snapshot import PATH_POLICIES

DELAYS=(0,5,15,30,60,90,120,180)


def outcome(issued,departure,source_age,*,delay,flight,score,allow_late=False):
    if type(delay) is not int or delay<0:
        raise ValueError('invalid publication delay')
    if departure is None:
        return 'ABSTAIN',None
    if not issued<=departure<=issued+28800:
        raise ValueError('invalid model departure')
    if departure>=issued+300:
        return 'FUTURE_RECHECK',None
    delivered=issued+delay
    if departure<delivered and not allow_late:
        return 'MISSED_POINT',None
    actual=max(departure,delivered)
    if actual>=issued+300 or source_age is None or not 0<=source_age+actual-issued<=180:
        return 'STALE',None
    result=score(actual+flight)[0]
    if result not in ('SUCCESS','FAILURE','UNKNOWN','PENDING'):
        raise ValueError('invalid arrival outcome')
    return result,actual-issued


def summarize(counts):
    n=counts.get('SUCCESS',0)+counts.get('FAILURE',0)
    departed=sum(counts.get(k,0) for k in ('SUCCESS','FAILURE','UNKNOWN','PENDING'))
    return dict(counts,resolved=n,departed=departed,
        success_fraction=counts.get('SUCCESS',0)/n if n else None,
        actionable_fraction=departed/counts['issues'] if counts['issues'] else None)


def assess(plans,*,flight,score):
    totals={};days={};offsets={};paired={}
    for delay in DELAYS:
        for arm in ('strict','late_counterfactual'):
            key=f'{arm}_{delay}s';totals[key]=Counter();days[key]={};offsets[key]={}
        paired[str(delay)]=Counter()
    for issued,departure,source_age in plans:
        for delay in DELAYS:
            outcomes={}
            for arm in ('strict','late_counterfactual'):
                result,wait=outcome(issued,departure,source_age,delay=delay,
                    flight=flight,score=score,allow_late=arm=='late_counterfactual')
                outcomes[arm]=result
                key=f'{arm}_{delay}s'
                for c in (totals[key],days[key].setdefault(str(issued//86400),Counter()),
                          offsets[key].setdefault(str(issued%3600//60),Counter())):
                    c['issues']+=1;c[result]+=1
                    if wait is not None:c['departure_delay_seconds_sum']+=wait
            # Compare exact zero-latency issuance outcome with the shifted arm.
            baseline=outcome(issued,departure,source_age,delay=0,flight=flight,score=score)[0]
            shifted=outcomes['late_counterfactual'];c=paired[str(delay)]
            c[baseline+'__'+shifted]+=1
            if baseline in ('SUCCESS','FAILURE') and shifted in ('SUCCESS','FAILURE'):
                c['matched_resolved']+=1
                c['shift_only_success']+=baseline=='FAILURE' and shifted=='SUCCESS'
                c['baseline_only_success']+=baseline=='SUCCESS' and shifted=='FAILURE'
    return {'arms':{k:dict(summarize(c),utc_days={d:summarize(v) for d,v in days[k].items()},
                 utc_minute_offsets={d:summarize(v) for d,v in offsets[k].items()}) for k,c in totals.items()},
            'paired_late_vs_zero_latency':{k:dict(v) for k,v in paired.items()}}


def audit(*,source,assignments,model_sha,days=7,progress=None):
    if type(days) is not int or not 1<=days<=7:
        raise ValueError('invalid days')
    roster=set(model.exact_roster())
    if not isinstance(assignments,dict) or set(assignments)!=roster:
        raise ValueError('exact verified assignment roster required')
    selected={k:c['departure_policy'] for k,c in assignments.items() if c.get('departure_policy')!='disabled'}
    if not selected or any(p not in PATH_POLICIES for p in selected.values()):
        raise ValueError('unsupported assigned policy')
    with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        meta=dict(db.execute('SELECT key,value FROM research_metadata'))
        cutoff=int(meta['source_cutoff_epoch'])
        # All departures scored here occur before the next five-minute issue.
        end=(cutoff-max(model.TRAVEL_SECONDS[k.split(':',1)[0]] for k in selected)-490)//300*300
        first=end-days*86400+300
        gaps=db.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?',(cutoff,model.MAX_GAPS+1)).fetchall()
        if len(gaps)>model.MAX_GAPS:raise ValueError('gap cap exceeded')
        crosses=model._gap_index(gaps,cutoff)
        polls=[r[0] for r in db.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp LIMIT ?",(cutoff,MAX_POLLS+1))]
        if len(polls)>MAX_POLLS:raise ValueError('poll cap exceeded')
        items={}
        for index,(key,policy) in enumerate(sorted(selected.items()),1):
            country,name=key.split(':',1)
            raw=db.execute('SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT ?',(country,name,cutoff,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
            if len(raw)>model.MAX_ITEM_CHANGE_ROWS or any(type(t) is not int or type(q) is not int or q<0 or not s for t,q,s in raw):raise ValueError('invalid stock rows')
            rows=[model.OBS(*r) for r in raw];flight=model.TRAVEL_SECONDS[country]
            evidence=ArrivalEvidence(rows,polls,gaps,cutoff)
            score=lru_cache(maxsize=65536)(evidence.score)
            paths=CausalStockPaths(rows,polls,crosses,cutoff=cutoff,flight_seconds=flight,score=score)
            tracker=ZeroCycles(crosses);cursor=0;plans=[]
            for issued in range(first,end+1,300):
                while cursor<len(rows) and rows[cursor].epoch<=issued:
                    tracker.add(rows[cursor]);cursor+=1
                pi=bisect.bisect_right(polls,issued)-1
                age=issued-polls[pi] if pi>=0 else None
                if crosses(issued,issued):age=None
                plan=paths.plans(issued,tracker,poll_age=age)[policy.removeprefix('zero_path_')]
                plans.append((issued,plan['departure_epoch'],age))
            items[key]=dict(assess(plans,flight=flight,score=score),policy=policy,flight_seconds=flight)
            if progress:progress(key,index,len(selected))
    return {'status':'PUBLICATION_DELAY_DIAGNOSTIC','model_sha':model_sha,
        'source_cutoff_epoch':cutoff,'issue_start_epoch':first,'issue_end_epoch':end,
        'days':days,'delays_seconds':DELAYS,'items':items,
        'assignment_sha256':hashlib.sha256(json.dumps(assignments,sort_keys=True).encode()).hexdigest(),
        'cohort_unit':'Each fixed five-minute issued plan, NOT trip-start replanning cohorts',
        'interpretation':'Retrospective sampled arrivals; correlated issues; late arm is counterfactual, not permission to execute late',
        'physical_depletion_quantity':0,'arrival_threshold':30,
        'production_model_changed':False,'actual_player_flights':False,'automatic_promotion':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True);parser.add_argument('--assignments',required=True)
    parser.add_argument('--model-sha',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=audit(source=args.source,assignments=json.loads(Path(args.assignments).read_text()),model_sha=args.model_sha,
        progress=lambda key,n,total:print('PROGRESS',n,total,key,flush=True))
    Path(args.output).write_text(json.dumps(result,sort_keys=True))
