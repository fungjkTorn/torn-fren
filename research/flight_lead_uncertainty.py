"""Fixed-clock lead diagnostics; no flight/departure optimization or promotion."""
import argparse
import bisect
import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.continuous_departure_replay import ArrivalEvidence,selected_items,MAX_POLLS
from research.true_zero_cycles import ZeroCycles,model
from research.quantity_rate_cycles import QuantityRateCycles
from research.zero_component_hybrids import ComponentHybrid


def q(values,p):
    return sorted(values)[max(0,math.ceil(len(values)*p)-1)] if values else None


def point_available(stream,target):
    windows=list(stream.get('restock_events') or [])
    if stream.get('current_stock_window'):windows.append(stream['current_stock_window'])
    return any(w['predicted_restock_epoch']<=target+model.GRACE<w['predicted_stock_below_30_epoch'] for w in windows)


def selected_events(events,observed,issued,target):
    """Keep next-after-clock and ordinal identity comparisons distinct."""
    chosen=next(((i,e) for i,e in enumerate(events) if e['predicted_restock_epoch']>target),None)
    if chosen is None:return None,None,None
    i,pred=chosen
    next_index=bisect.bisect_right(observed,target)
    ordinal_index=bisect.bisect_right(observed,issued)+i
    bound=issued+28800
    next_truth=observed[next_index] if next_index<len(observed) and observed[next_index]<=bound else None
    ordinal_truth=observed[ordinal_index] if ordinal_index<len(observed) and observed[ordinal_index]<=bound else None
    return pred,next_truth,ordinal_truth


def evaluate_item(key,obs,polls,gaps,*,cutoff,start,end,trace=None):
    crosses=model._gap_index(gaps,cutoff);evidence=ArrivalEvidence(obs,polls,gaps,cutoff)
    observed=[b.epoch for a,b in zip(obs,obs[1:]) if a.epoch<b.epoch and a.quantity==0<b.quantity
              and a.source==b.source and not crosses(a.epoch,b.epoch)]
    switches=[b.epoch for a,b in zip(obs,obs[1:]) if a.source!=b.source]
    conflicts=[b.epoch for a,b in zip(obs,obs[1:])
        if a.source!=b.source and (a.quantity>0)!=(b.quantity>0)]
    def contains(times,a,b):return bisect.bisect_right(times,b)>bisect.bisect_right(times,a)
    def uncertain(a,b):
        return crosses(a,b) or contains(switches,a,b)
    flight=model.TRAVEL_SECONDS[key.split(':',1)[0]]
    leads=sorted({0,900,1800,3600,5400,flight,10800,14400})
    trackers={'zero':ZeroCycles(crosses),'rate':QuantityRateCycles(crosses),
              'hybrid':ComponentHybrid(crosses,'current_rate')}
    data={(family,lead):dict(counts=Counter(),errors=[],widths=[],ordinal_errors=[],ordinal_widths=[])
          for family in trackers for lead in leads}
    cursor=0
    for issued in range((start//3600+1)*3600,end+1,3600):
        while cursor<len(obs) and obs[cursor].epoch<=issued:
            for tracker in trackers.values():tracker.add(obs[cursor])
            cursor+=1
        pi=bisect.bisect_right(polls,issued)-1
        healthy=pi>=0 and issued-polls[pi]<=180 and not crosses(issued,issued)
        streams={family:tracker.forecast(key,asof=issued) for family,tracker in trackers.items()}
        if trace is not None:trace.append(dict(issued=issued,forecasts=streams))
        for family,stream in streams.items():
            events=stream.get('true_restock_events',[])
            for lead in leads:
                d=data[family,lead];c=d['counts'];c['issues']+=1;target=issued+lead
                if not healthy:c['unhealthy_issue']+=1;continue
                if stream['status']!='EVENT_TIMELINE_FORECAST_AVAILABLE':
                    c['forecast_abstain']+=1;continue
                c['supported']+=1
                outcome,_,_=evidence.score(target)
                c['arrival_'+outcome]+=1
                if outcome in ('SUCCESS','FAILURE'):
                    predicted=point_available(stream,target);actual=outcome=='SUCCESS'
                    c['true_positive' if predicted and actual else 'false_positive' if predicted else 'false_negative' if actual else 'true_negative']+=1
                # Count complete physical restocks before the fixed lead.
                # This diagnoses cycle slips; no nearest-outcome event match.
                gap=crosses(issued,target);switch=contains(switches,issued,target)
                conflict=contains(conflicts,issued,target)
                c['cycle_count_unknown_collection_gap']+=gap
                c['cycle_count_provider_switch']+=switch
                c['cycle_count_provider_phase_conflict']+=conflict
                if gap or switch:c['cycle_count_unknown']+=1
                else:
                    predicted_count=sum(issued<e['predicted_restock_epoch']<=target for e in events)
                    true_count=bisect.bisect_right(observed,target)-bisect.bisect_right(observed,issued)
                    c['cycle_count_known']+=1
                    c['cycle_count_exact']+=predicted_count==true_count
                    c['cycle_count_absolute_difference_sum']+=abs(predicted_count-true_count)
                pred,truth,ordinal=selected_events(events,observed,issued,target)
                if pred is None:c['no_next_forecast_in_8h']+=1;continue
                # Ordinal pairing preserves forecast event index. Benign
                # same-phase switches follow existing V145 continuity rules;
                # gaps and physical phase contradictions remain unknown.
                if ordinal is None:c['ordinal_no_observed_event_in_8h']+=1
                elif crosses(issued,max(ordinal,pred['predicted_restock_epoch'])) or contains(conflicts,issued,max(ordinal,pred['predicted_restock_epoch'])):
                    c['ordinal_unknown_gap_or_phase_conflict']+=1
                else:
                    err=pred['predicted_restock_epoch']-ordinal
                    d['ordinal_errors'].append(err)
                    d['ordinal_widths'].append(pred['restock_late_epoch']-pred['restock_early_epoch'])
                    c['ordinal_compared']+=1
                    c['ordinal_inside_proposed_bounds']+=pred['restock_early_epoch']<=ordinal<=pred['restock_late_epoch']
                    for tolerance in (15,60,300,600):c['ordinal_error_within_'+str(tolerance)]+=abs(err)<=tolerance
                if truth is None:c['no_next_observed_restock_in_8h']+=1;continue
                if uncertain(target,truth):
                    c['next_event_unknown_gap_or_provider_switch']+=1
                    c['next_event_unknown_collection_gap']+=crosses(target,truth)
                    c['next_event_provider_switch']+=contains(switches,target,truth)
                    continue
                error=pred['predicted_restock_epoch']-truth;d['errors'].append(error)
                lo,hi=pred['restock_early_epoch'],pred['restock_late_epoch']
                d['widths'].append(hi-lo)
                c['next_event_compared']+=1;c['next_event_inside_proposed_bounds']+=lo<=truth<=hi
                for tolerance in (15,60,300,600):c['next_error_within_'+str(tolerance)]+=abs(error)<=tolerance
        # Complete availability history only; no ongoing eventual lifetime.
    output={}
    for (family,lead),d in data.items():
        c=d['counts'];n=sum(c[k] for k in ('true_positive','false_positive','false_negative','true_negative'))
        positive=c['true_positive']+c['false_negative'];negative=n-positive
        sensitivity=c['true_positive']/positive if positive else None
        specificity=c['true_negative']/negative if negative else None
        output.setdefault(family,{})[str(lead)]=dict(c,
            occupancy_scored=n,actual_available_fraction=positive/n if n else None,
            always_unavailable_accuracy=negative/n if n else None,
            point_positive_precision=c['true_positive']/(c['true_positive']+c['false_positive']) if c['true_positive']+c['false_positive'] else None,
            point_positive_recall=sensitivity,point_specificity=specificity,
            point_balanced_accuracy=(sensitivity+specificity)/2 if sensitivity is not None and specificity is not None else None,
            cycle_count_exact_fraction=c['cycle_count_exact']/c['cycle_count_known'] if c['cycle_count_known'] else None,
            next_event_absolute_error_p50=q([abs(e) for e in d['errors']],.5),
            next_event_absolute_error_p90=q([abs(e) for e in d['errors']],.9),
            next_event_signed_error_p50=q(d['errors'],.5),proposed_interval_width_p50=q(d['widths'],.5),
            next_event_proposed_interval_capture=c['next_event_inside_proposed_bounds']/c['next_event_compared'] if c['next_event_compared'] else None,
            ordinal_absolute_error_p50=q([abs(e) for e in d['ordinal_errors']],.5),
            ordinal_absolute_error_p90=q([abs(e) for e in d['ordinal_errors']],.9),
            ordinal_signed_error_p50=q(d['ordinal_errors'],.5),
            ordinal_interval_width_p50=q(d['ordinal_widths'],.5),
            ordinal_interval_capture=c['ordinal_inside_proposed_bounds']/c['ordinal_compared'] if c['ordinal_compared'] else None)
    rows=[r for r in obs if start<r.epoch<=end]
    return dict(flight_seconds=flight,models=output,
        source_diagnostics=dict(stock_delta_rows_by_provider=dict(Counter(r.source for r in rows)),
            switches_in_issue_window=sum(start<t<=end for t in switches),
            physical_phase_conflicts_on_switch=sum(start<t<=end for t in conflicts)),
        completed_buying_window_median=q(trackers['zero'].available_durations,.5),
        warning='Next-after-lead predicted and observed events are selected separately by clock, not nearest truth; cycle slips can compare different event identities. Not event-conditioned recall or player flight accuracy.')


def audit(source,*,days=7,item_keys=None,model_sha='unversioned'):
    if type(days) is not int or not 1<=days<=7:raise ValueError('days must be1..7')
    selected=selected_items(item_keys)
    path=Path(source).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        metadata=dict(db.execute('SELECT key,value FROM research_metadata'))
        cutoff=int(metadata['source_cutoff_epoch']);end=cutoff-28800;start=end-days*86400
        gaps=db.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp',(cutoff,)).fetchall()
        polls=[int(r[0]) for r in db.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp LIMIT ?",(cutoff,MAX_POLLS+1))]
        if len(polls)>MAX_POLLS:raise ValueError('poll cap exceeded')
        items={}
        for key in selected:
            country,name=key.split(':',1)
            raw=db.execute('''SELECT timestamp,quantity,source FROM stock_history
                WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=?
                ORDER BY timestamp,id LIMIT ?''',(country,name,cutoff,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
            if len(raw)>model.MAX_ITEM_CHANGE_ROWS:raise ValueError('stock row cap exceeded')
            if any(type(t) is not int or type(quantity) is not int or quantity<0 or not source for t,quantity,source in raw):raise ValueError('invalid stock row')
            items[key]=evaluate_item(key,[model.OBS(*r) for r in raw],polls,gaps,cutoff=cutoff,start=start,end=end)
        has_country=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='country_stock_observations'").fetchone() is not None
        country_count=db.execute('SELECT count(*) FROM country_stock_observations WHERE received_epoch<=?',(cutoff,)).fetchone()[0] if has_country else 0
    return dict(kind='FIXED_UTC_HOURLY_LEAD_UNCERTAINTY_AUDIT',model_sha=model_sha,asof_epoch=cutoff,
        issue_start_epoch=start,issue_end_epoch=end,days=days,items=items,
        country_clock_rows=country_count,country_clock_evidence_available=country_count>0,
        true_depletion_quantity=0,arrival_stock_threshold=30,
        warning='Correlated fixed hourly cohorts. No departure selection, no model promotion, no calibrated probabilities. Missing country clocks are unknown, never backfilled.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    p.add_argument('--output',required=True);p.add_argument('--model-sha',default='unversioned')
    p.add_argument('--item-key',action='append');a=p.parse_args()
    r=audit(a.source,item_keys=a.item_key,model_sha=a.model_sha)
    Path(a.output).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    for key,item in r['items'].items():
        print('LEAD_ITEM',key,json.dumps({family:rows[str(item['flight_seconds'])] for family,rows in item['models'].items()},sort_keys=True))
