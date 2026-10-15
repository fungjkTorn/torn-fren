"""Past-only cycle regression and clock-phase diagnostics; never flight proof."""
import argparse
import bisect
import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

import numpy as np

from research.continuous_departure_replay import selected_items,MAX_POLLS
from research.true_zero_cycles import model

PERIODS=(300,600,900,1800,3600,7200)


def quantile(values,p):
    return sorted(values)[max(0,math.ceil(len(values)*p)-1)] if values else None


def features(history,epoch,quantity,source):
    if len(history)<4:return None
    recent=history[-16:];center=quantile([r['duration'] for r in recent],.5)
    batch=quantile([max(1,r['quantity']) for r in recent],.5)
    row=[1]+[math.log(r['duration']/center) for r in history[-4:]]
    row += [math.log(center/3600),math.log(max(1,history[-1]['stock_seconds'])/600),
            math.log(max(1,history[-1]['empty_seconds'])/600),math.log(max(1,quantity)/batch)]
    for period in (86400,3600):
        angle=2*math.pi*(epoch%period)/period;row.extend((math.sin(angle),math.cos(angle)))
    return row+[int(source=='prometheus')]


def cycles_from_rows(rows,crosses,cutoff):
    """Complete cycles must include an observed physical positive->0 boundary."""
    history=[];trials=[];restocks=[];active=None;previous=None
    for obs in rows:
        if obs.epoch>cutoff:break
        if previous is not None:
            invalid=(obs.epoch<=previous.epoch or crosses(previous.epoch,obs.epoch)
                or (obs.source!=previous.source and (obs.quantity>0)!=(previous.quantity>0)))
            if invalid and active is not None:
                active['outcome']='UNKNOWN';active=None
            restock=(not invalid and previous.quantity==0<obs.quantity and previous.source==obs.source)
            if restock:
                restocks.append(obs.epoch)
                if active is not None and active['zero_epoch'] is not None:
                    active.update(outcome='CLOSED',end=obs.epoch,duration=obs.epoch-active['start'],
                        stock_seconds=active['zero_epoch']-active['start'],empty_seconds=obs.epoch-active['zero_epoch'])
                    history.append(active)
                active=dict(start=obs.epoch,quantity=obs.quantity,source=obs.source,zero_epoch=None,
                    feature=features(history,obs.epoch,obs.quantity,obs.source),outcome='PENDING')
                trials.append(active)
            elif not invalid and active is not None and previous.quantity>0 and obs.quantity==0:
                active['zero_epoch']=obs.epoch
        previous=obs
    return trials,restocks


def cycle_predictions(trials,issued,feature):
    # Offline precomputation cannot expose a label ending after this issue.
    train=[r for r in trials if r['outcome']=='CLOSED' and r['end']<=issued and r['feature'] is not None][-64:]
    if feature is None or len(train)<24:return None
    x=np.asarray([r['feature'] for r in train],dtype=float)
    y=np.log([r['duration'] for r in train]);weights=np.exp2(-np.arange(len(train)-1,-1,-1)/32)
    mean=np.average(x,axis=0,weights=weights);scale=np.sqrt(np.average((x-mean)**2,axis=0,weights=weights))
    scale=np.maximum(scale,.1);mean[0]=0;scale[0]=1
    x=(x-mean)/scale;penalty=np.eye(x.shape[1])*8;penalty[0,0]=0
    beta=np.linalg.solve(x.T@(x*weights[:,None])+penalty,x.T@(weights*y))
    value=float(((np.asarray(feature)-mean)/scale)@beta)
    value=min(float(np.max(y)),max(float(np.min(y)),value))
    duration=max(1,round(math.exp(value)))
    baseline=quantile([r['duration'] for r in train],.5)
    return dict(median=baseline,ridge=duration,training_cycles=len(train),latest_training_end=max(r['end'] for r in train))


def circular_distance(x,center,period):
    delta=np.abs(x-center)%period
    return np.minimum(delta,period-delta)


def clock_fit(train,polls,asof,period):
    events=np.asarray([t for t in train if t<=asof][-64:],dtype=np.int64)
    if len(events)<24:return None
    centers=np.arange(0,period,30)
    near=circular_distance(events[:,None]%period,centers[None,:],period)<=60
    fraction=near.mean(axis=0);j=int(np.argmax(fraction));center=int(centers[j]);halves=np.array_split(near[:,j],2)
    stable=float(fraction[j])>=.4 and all(float(h.mean())>=.35 for h in halves)
    lo=bisect.bisect_left(polls,int(events[0]));hi=bisect.bisect_right(polls,asof)
    control=np.asarray(polls[lo:hi],dtype=np.int64)
    mass=float(np.mean(circular_distance(control%period,center,period)<=60)) if len(control) else None
    coverage=len(np.unique((control%period)//30))/len(centers) if len(control) else 0
    admitted=stable and mass is not None and coverage>=.8 and fraction[j]-mass>=.15
    return dict(center=center,training_fraction=float(fraction[j]),poll_control_fraction=mass,
        poll_phase_coverage=coverage,admitted=bool(admitted),training_events=len(events),latest_training_event=int(events[-1]))


def summarize_errors(errors):
    a=[abs(e) for e in errors]
    return dict(n=len(a),mae_seconds=sum(a)/len(a) if a else None,
        absolute_error_p50=quantile(a,.5),absolute_error_p90=quantile(a,.9),
        signed_error_p50=quantile(errors,.5),
        within_seconds={str(t):sum(e<=t for e in a) for t in (15,60,300,600)})


def evaluate(key,rows,polls,gaps,*,cutoff,days=7,trace=None):
    start=cutoff-days*86400;crosses=model._gap_index(gaps,cutoff)
    trials,restocks=cycles_from_rows(rows,crosses,cutoff)
    errors={name:[] for name in ('median','ridge')};counts=Counter();daily={};paired=Counter()
    for trial in trials:
        if not start<trial['start']<=cutoff:continue
        counts['issues']+=1;counts[trial['outcome']]+=1
        prediction=cycle_predictions(trials,trial['start'],trial['feature'])
        if trace is not None:trace.append(dict(start=trial['start'],prediction=prediction))
        if prediction is None:counts['abstain']+=1;continue
        counts['predicted']+=1
        if trial['outcome']!='CLOSED':continue
        day=(trial['start']-start)//86400;d=daily.setdefault(day,{name:[] for name in errors})
        for name in errors:
            err=prediction[name]-trial['duration'];errors[name].append(err);d[name].append(err)
        gain=abs(errors['median'][-1])-abs(errors['ridge'][-1])
        paired['ridge_better']+=gain>0;paired['median_better']+=gain<0;paired['ties']+=gain==0
    summary={name:summarize_errors(v) for name,v in errors.items()}
    base=summary['median'];new=summary['ridge']
    gain=1-new['mae_seconds']/base['mae_seconds'] if base['mae_seconds'] else None
    signal=(new['n']>=30 and gain is not None and gain>=.1 and new['absolute_error_p90']<=base['absolute_error_p90']
        and paired['ridge_better']>paired['median_better'])
    lattice={}
    flight=model.TRAVEL_SECONDS[key.split(':',1)[0]]
    for period in PERIODS:
        c=Counter();masses=[];training=[]
        for event in restocks:
            if not start<event<=cutoff:continue
            c['observed_restocks']+=1
            asof=event-flight
            fit=clock_fit(restocks,polls,asof,period)
            if fit is None:c['insufficient_history']+=1;continue
            c['trained']+=1;training.append(fit['training_fraction'])
            if not fit['admitted']:c['gate_rejected']+=1;continue
            c['admitted']+=1;masses.append(fit['poll_control_fraction'])
            c['heldout_phase_hits']+=bool(circular_distance(event%period,fit['center'],period)<=60)
        lattice[str(period)]=dict(c,heldout_phase_hit_fraction=c['heldout_phase_hits']/c['admitted'] if c['admitted'] else None,
            poll_control_fraction_mean=sum(masses)/len(masses) if masses else None,
            median_best_training_fraction=quantile(training,.5))
    return dict(flight_seconds=flight,cycle_regression=dict(counts,models=summary,paired=dict(paired),
            mae_relative_gain=gain,signal_for_departure_experiment=bool(signal),
            days={str(d):{n:summarize_errors(e) for n,e in day.items()} for d,day in sorted(daily.items())}),
        clock_phase=lattice,
        note='Cycle forecasts are issued after observed true restocks and predict one following full physical cycle, not a flight decision. Clock-phase tests are event-conditioned at event-flight and are NOT forecast precision or flight success.')


def audit(source,*,item_keys=None,days=7,model_sha='unversioned'):
    if type(days) is not int or not 1<=days<=7:raise ValueError('invalid days')
    keys=selected_items(item_keys);path=Path(source).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        metadata=dict(db.execute('SELECT key,value FROM research_metadata'));cutoff=int(metadata['source_cutoff_epoch'])
        gaps=db.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp',(cutoff,)).fetchall()
        polls=[r[0] for r in db.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp LIMIT ?",(cutoff,MAX_POLLS+1))]
        if len(polls)>MAX_POLLS:raise ValueError('poll cap exceeded')
        result={}
        for key in keys:
            country,name=key.split(':',1)
            raw=db.execute('''SELECT timestamp,quantity,source FROM stock_history WHERE country=?
                AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT ?''',
                (country,name,cutoff,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
            if len(raw)>model.MAX_ITEM_CHANGE_ROWS:raise ValueError('stock row cap exceeded')
            if any(type(t) is not int or type(qty) is not int or qty<0 or type(src) is not str or not src for t,qty,src in raw):raise ValueError('invalid stock row')
            result[key]=evaluate(key,[model.OBS(*r) for r in raw],polls,gaps,cutoff=cutoff,days=days)
    return dict(kind='PAST_ONLY_RESTOCK_PREDICTABILITY_AUDIT',model_sha=model_sha,asof_epoch=cutoff,days=days,
        items=result,physical_depletion_quantity=0,clock_periods_seconds=list(PERIODS),
        production_promotion=False,warning='Exploratory sampled-event diagnostics. Event-conditioned clock hit rates are not flight success. Cycle regression requires departure replay and fresh validation before use.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--output',required=True);p.add_argument('--model-sha',default='unversioned');p.add_argument('--item-key',action='append')
    a=p.parse_args();r=audit(a.source,item_keys=a.item_key,model_sha=a.model_sha)
    Path(a.output).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    for key,item in r['items'].items():print('PREDICTABILITY_ITEM',key,json.dumps(item,sort_keys=True))
