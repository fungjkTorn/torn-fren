"""Physical restock clocks -> chronological stock windows -> flight decisions.

Research only. Uses existing prequential interval regressions, rather than
optimizing arbitrary future arrival bins. No fitting uses an unfinished cycle.
"""
import argparse
import bisect
from collections import Counter
import json
import math
from pathlib import Path
import time

from research.restock_predictability_audit import cycles_from_rows, cycle_predictions, quantile
from research.true_zero_cycles import ZeroCycles, model

STEP=300
WAIT=28800
MODES=('phase_empirical','interval_median','interval_ridge')


def continuous_source(rows,crosses):
    switches=[b.epoch for a,b in zip(rows,rows[1:]) if a.source!=b.source]
    def invalid(start,end):
        i=bisect.bisect_right(switches,start)
        return crosses(start,end) or i<len(switches) and switches[i]<=end
    return invalid


def departure(forecast, *, issued, flight, conservative=False):
    """Select FIRST reachable event; require stock at landing through +10s.

    The next item drop remains first in the forecast even when unreachable.
    A future departure is tentative and must be rechecked on the next issue.
    """
    windows=[]
    if forecast.get('current_stock_window'):
        windows.append((0,forecast['current_stock_window']))
    windows.extend((i+1,w) for i,w in enumerate(forecast.get('restock_events',[])))
    for index,w in windows:
        if conservative:
            start=w.get('restock_late_epoch')
            end=w.get('early_stock_end_epoch')
            if start is None or end is None:continue
        else:
            start=w['predicted_restock_epoch'];end=w['predicted_stock_below_30_epoch']
        dep=max(issued,start-flight)
        if dep<=issued+WAIT and dep+flight>=start and dep+flight+10<end:
            return dict(departure=dep,event_index=index,landing=dep+flight,
                        arrival_plus_10=dep+flight+10,stock_window_start=start,stock_window_end=end)
    return dict(departure=None,event_index=None,landing=None,arrival_plus_10=None)


class IntervalClock:
    """Last observed physical restock anchors the first event, never stock=30.

    First interval uses an existing birth-time fit plus past prequential errors.
    Later cycles use completed empirical intervals, with widening event bounds.
    Future projected cycles are not represented as observed training records.
    """
    def __init__(self,rows,crosses,cutoff):
        crosses=continuous_source(rows,crosses)
        self.trials,_=cycles_from_rows(rows,crosses,cutoff)
        self.starts=[t['start'] for t in self.trials]
        self.fits=[cycle_predictions(self.trials,t['start'],t['feature']) for t in self.trials]
        self.crosses=crosses
        self.last_training_end=None

    def forecast(self,key,tracker,issued,family):
        if family not in ('median','ridge'):raise ValueError('Unknown fixed clock')
        if tracker.last is not None and tracker.last.epoch>issued:raise ValueError('Future tracker state')
        base=dict(item_key=key,asof_epoch=issued,status='INSUFFICIENT_CLOCK_HISTORY',
            restock_events=[],true_restock_events=[],current_stock_window=None,physical_depletion_quantity=0,
            arrival_stock_threshold=30,calibrated_success_probability=None,
            model_name='physical_restock_interval_'+family,first_event_is_next_physical_drop=True)
        i=bisect.bisect_right(self.starts,issued)-1
        if i<0:return base
        active=self.trials[i];fit=self.fits[i]
        if (fit is None or active.get('invalidated_at',issued+1)<=issued
                or tracker.last is None or issued-tracker.last.epoch>86400):return base
        past=[(t,f) for t,f in zip(self.trials,self.fits)
              if t['outcome']=='CLOSED' and t['end']<=issued and f is not None][-64:]
        if len(past)<8:return base
        ratios=[math.log(t['duration']/f[family]) for t,f in past]
        totals=[max(1,round(fit[family]*math.exp(r))) for r in ratios]
        age=issued-active['start'];survivors=[d for d in totals if d>age]
        if not survivors:return dict(base,status='CLOCK_OVERRAN_CALIBRATION_HISTORY')
        available=tracker.available_durations[-64:]
        purchasing=(len(available)>=3 and quantile(tracker.restock_quantities[-64:],.5)>=30)
        # Endpoints, current state and training labels all precede this issue.
        latest=max(t['end'] for t,f in past)
        if latest>issued or fit['latest_training_end']>active['start']:
            raise ValueError('Future clock training label')
        base.update(status='EVENT_TIMELINE_FORECAST_AVAILABLE',anchor_restock_epoch=active['start'],
            latest_training_end=latest,fit_latest_training_end=fit['latest_training_end'],
            calibration_cycles=len(past),conditioned_survivors=len(survivors))
        # Separate purchase-availability phase, with no change to physical clock.
        a=tracker.availability.asof()
        if purchasing and tracker.last.quantity>=30 and a.get('phase_onset') is not None:
            remaining=[d-(issued-a['phase_onset']) for d in available if d>issued-a['phase_onset']]
            physical_state=tracker.physical.asof()
            onset=physical_state.get('phase_onset')
            physical_remaining=([d-(issued-onset) for d in physical_state['stocked_durations']
                if d>issued-onset] if onset is not None else [])
            if remaining and physical_remaining:
                base['current_stock_window']=dict(predicted_restock_epoch=issued,restock_late_epoch=issued,
                    predicted_stock_below_30_epoch=issued+min(quantile(remaining,.5),quantile(physical_remaining,.5)),
                    early_stock_end_epoch=issued+min(quantile(remaining,.25),quantile(physical_remaining,.25)))
        first={q:active['start']+quantile(survivors,q) for q in (.25,.5,.75)}
        periods=[t['duration'] for t,f in past]
        for index in range(64):
            if first[.5]>issued+WAIT:break
            event=dict(event_index=index+1,
                predicted_restock_epoch=first[.5],restock_early_epoch=first[.25],
                restock_late_epoch=first[.75])
            base['true_restock_events'].append(dict(event))
            if purchasing:
                physical=tracker.physical.asof()['stocked_durations'][-64:]
                event.update(predicted_stock_below_30_epoch=first[.5]+min(quantile(available,.5),quantile(physical,.5)),
                    early_stock_end_epoch=first[.25]+min(quantile(available,.25),quantile(physical,.25)))
                base['restock_events'].append(event)
            first={q:first[q]+quantile(periods,q) for q in (.25,.5,.75)}
        if not purchasing:base['status']='INSUFFICIENT_SEPARATE_PURCHASE_WINDOW_HISTORY'
        return base


def item_benchmark(source,key,*,days=6):
    from research.japan_xanax.renewal_shadow import source_data
    from research.departure_reconfirmation import evaluate_utc,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,item_key=key)
    observations=[model.OBS(*r) for r in rows]
    observation_times=[o.epoch for o in observations]
    crosses=continuous_source(observations,crosses)
    clock=IntervalClock(observations,crosses,cutoff)
    tracker=ZeroCycles(crosses);flight=model.TRAVEL_SECONDS[key.split(':')[0]]
    end=((cutoff-flight-WAIT-190-STEP)//STEP)*STEP
    start=end-days*86400+STEP
    split=start+(days//2)*86400
    # All cohorts get their full eight-hour follow-up and mature arrival truth.
    stop=end+WAIT+STEP
    plans={m+'_'+p:[] for m in MODES for p in ('expected','bounded')};plans['leave_now']=[]
    timing={m:[] for m in MODES};cursor=0;statuses={m:Counter() for m in MODES}
    for issued in range(start,stop+1,STEP):
        while cursor<len(observations) and observations[cursor].epoch<=issued:
            tracker.add(observations[cursor]);cursor+=1
        pi=bisect.bisect_right(polls,issued)-1;age=issued-polls[pi] if pi>=0 else None
        healthy=age is not None and 0<=age+15<=180 and not crosses(issued,issued)
        streams={'phase_empirical':tracker.forecast(key,asof=issued)}
        available=tracker.available_durations[-64:]
        if available:
            for event in streams['phase_empirical'].get('restock_events',[]):
                event['early_stock_end_epoch']=event['restock_early_epoch']+quantile(available,.25)
            current=streams['phase_empirical'].get('current_stock_window')
            a=tracker.availability.asof()
            if current and a.get('phase_onset') is not None:
                remaining=[d-issued+a['phase_onset'] for d in available if d>issued-a['phase_onset']]
                if remaining:current['early_stock_end_epoch']=issued+quantile(remaining,.25)
        streams.update({'interval_'+f:clock.forecast(key,tracker,issued,f) for f in ('median','ridge')})
        for mode,f in streams.items():
            statuses[mode][f['status']]+=1
            for kind in ('expected','bounded'):
                choice=departure(f,issued=issued,flight=flight,conservative=kind=='bounded')
                dep=choice['departure'] if healthy and f['status']=='EVENT_TIMELINE_FORECAST_AVAILABLE' else None
                plans[mode+'_'+kind].append((issued,max(issued+15,dep) if dep is not None else None,age))
            # Fixed first-issue/hour forecast, ranked before evaluating truth.
            if issued<=end and issued%3600==0:
                events=f.get('true_restock_events',f.get('restock_events',[]))
                timing[mode].append(dict(issued=issued,predicted=events[0]['predicted_restock_epoch'] if events else None,
                    healthy=healthy,training_end=f.get('latest_training_end')))
        plans['leave_now'].append((issued,issued+15 if healthy else None,age))
    # No observed target timestamps or stock outcome labels enter planning.
    # Strict ordinal next-event label; never select the nearest matching drop.
    physical=[b.epoch for a,b in zip(observations,observations[1:])
        if a.quantity==0<b.quantity and a.source==b.source and not crosses(a.epoch,b.epoch)]
    restock={}
    for mode,records in timing.items():
        errors=[];counts=Counter();targets=set()
        for r in records:
            counts['hourly_issues']+=1
            if not r['healthy'] or r['predicted'] is None:counts['abstain']+=1;continue
            j=bisect.bisect_right(physical,r['issued'])
            if j>=len(physical):counts['pending']+=1;continue
            actual=physical[j]
            if crosses(r['issued'],actual):counts['unknown_gap']+=1;continue
            # Do not certify intervals containing a provider switch, even if
            # physical states happen to agree on both sides of the switch.
            lo=bisect.bisect_right(observation_times,r['issued'])-1
            hi=bisect.bisect_right(observation_times,actual)
            if lo<0 or len({o.source for o in observations[lo:hi]})!=1:
                counts['unknown_provider']+=1;continue
            errors.append((r['issued'],abs(r['predicted']-actual),actual));targets.add(actual)
        restock[mode]=dict(counts,scored=len(errors),distinct_target_restocks=len(targets),
            mean_absolute_error_minutes=sum(e for t,e,a in errors)/len(errors)/60 if errors else None,
            median_absolute_error_minutes=quantile([e for t,e,a in errors],.5)/60 if errors else None,
            within_5_minutes=sum(e<=300 for t,e,a in errors),within_10_minutes=sum(e<=600 for t,e,a in errors))
        restock[mode]['chronological_slices']={}
        for label,predicate in (('earlier_development',lambda t:t<split),('later_validation',lambda t:t>=split)):
            values=[(t,e,a) for t,e,a in errors if predicate(t)]
            restock[mode]['chronological_slices'][label]=dict(scored=len(values),
                distinct_target_restocks=len({a for t,e,a in values}),
                mean_absolute_error_minutes=sum(e for t,e,a in values)/len(values)/60 if values else None)
        restock[mode]['resolved_errors']={t:e for t,e,a in errors}
    reference=restock['phase_empirical']['resolved_errors']
    for mode,r in restock.items():
        paired=set(reference)&set(r['resolved_errors'])
        r['matched_vs_phase_empirical']={}
        for label,predicate in (('all',lambda t:True),('earlier_development',lambda t:t<split),('later_validation',lambda t:t>=split)):
            times=[t for t in paired if predicate(t)]
            r['matched_vs_phase_empirical'][label]=dict(pairs=len(times),
                baseline_mae_minutes=sum(reference[t] for t in times)/len(times)/60 if times else None,
                challenger_mae_minutes=sum(r['resolved_errors'][t] for t in times)/len(times)/60 if times else None)
    for r in restock.values():del r['resolved_errors']
    summaries={};cohorts={}
    for mode,values in plans.items():
        cohorts[mode]=[]
        summaries[mode]=evaluate_utc(values,cutoff=cutoff,flight_seconds=flight,
            score=evidence.score,start_before=end,cohorts=cohorts[mode])
    slices={}
    for label,predicate in (('earlier_development',lambda t:t<split),('later_validation',lambda t:t>=split)):
        selected={m:[r for r in records if predicate(r['start'])] for m,records in cohorts.items()}
        slices[label]={}
        for mode,rec in selected.items():
            counts=Counter(r['outcome'] for r in rec);known=counts['SUCCESS']+counts['FAILURE']
            waits=[r['wait'] for r in rec if r['wait'] is not None]
            slices[label][mode]=dict(counts,starts=len(rec),scored=known,
                success_fraction=counts['SUCCESS']/known if known else None,
                departure_coverage=len(waits)/len(rec) if rec else None,
                mean_wait_minutes=sum(waits)/len(waits)/60 if waits else None,
                matched_vs_now=compare_cohorts(selected['leave_now'],rec))
    return dict(item_key=key,cutoff=cutoff,cohort_start=start,cohort_end=end,chronological_split=split,
        restock_timing=restock,departure=summaries,chronological_slices=slices,
        status_counts={m:dict(c) for m,c in statuses.items()},physical_depletion_quantity=0,
        buying_threshold=30,arrival_plus_10=True,production_promotion=False,
        note='Historical correlated hourly cohorts; sampled poll truth, not provider-certified game events. No model routing selected.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--out',required=True)
    p.add_argument('--model-sha',required=True);p.add_argument('--item-key',action='append')
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    keys=sorted(a.item_key or model.exact_roster())
    if len(set(keys))!=len(keys) or not set(keys)<=set(model.exact_roster()):raise ValueError('Invalid roster')
    request=dict(model_sha=a.model_sha,items=keys,days=6,variants=MODES,automatic_promotion=False)
    (out/'request.json').write_text(json.dumps(request,indent=2)+'\n')
    for key in keys:
        began=time.monotonic();r=item_benchmark(a.source,key)
        r['seconds']=time.monotonic()-began
        (out/(key.replace(':','-').replace(' ','_')+'.json')).write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps(dict(item_key=key,seconds=r['seconds'],restock_timing=r['restock_timing'])),flush=True)


if __name__=='__main__':main()
