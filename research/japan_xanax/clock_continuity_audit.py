"""Post-activation Japan country-clock audit; no forecast/continuity changes."""
import json
import sqlite3
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path
import numpy as np
from research.japan_xanax.renewal_shadow import KEY,History,source_data
from research.japan_xanax.training_audit import HalfPhases


def reported(row):
    t,source,update,status,n=row
    return type(t) is int and type(update) is int and status=='REPORTED' and 0<update<=t and type(n) is int and n>0


def quantiles(values):
    return dict(n=len(values),min=min(values),p50=float(np.quantile(values,.5)),p90=float(np.quantile(values,.9)),max=max(values)) if values else dict(n=0)


def analyze(clocks,stock,cutoff):
    if any(r[0]>cutoff for r in clocks) or any(r[0]>cutoff for r in stock):raise ValueError('Future evidence')
    if any(b[0]<a[0] for a,b in zip(clocks,clocks[1:])):raise ValueError('Unordered clock evidence')
    if not clocks:return dict(status='NO_RECENT_JAPAN_CLOCKS',clock_rows=0)
    providers={};previous={};last=None;switches=[];counts=Counter()
    for row in clocks:
        t,source,update,status,n=row
        c=providers.setdefault(source,dict(rows=0,statuses=Counter(),ages=[],repeated=0,regressed=0,updates=0,item_counts=[]))
        c['rows']+=1;c['statuses'][status]+=1;c['item_counts'].append(n)
        if reported(row):
            c['ages'].append(t-update)
            if t-update>180:counts['reported_age_over180']+=1
            prior=previous.get(source)
            if prior is not None:
                c['repeated']+=int(update==prior);c['regressed']+=int(update<prior);c['updates']+=int(update>prior)
            previous[source]=update
        if last is not None and source!=last[1]:
            counts['country_provider_switches']+=1
            detail=dict(received=t,previous_source=last[1],source=source,
                previous_report_age_at_switch=t-last[2] if reported(last) else None,
                new_report_age=t-update if reported(row) else None,
                report_clock_shift=update-last[2] if reported(row) and reported(last) else None)
            if reported(row) and reported(last) and update<last[2]:counts['switch_to_older_report_clock']+=1
            if len(switches)<20:switches.append(detail)
        last=row
    out={}
    for source,c in providers.items():
        out[source]=dict(rows=c['rows'],statuses=dict(c['statuses']),report_age_seconds=quantiles(c['ages']),
            repeated_updates=c['repeated'],within_provider_clock_regressions=c['regressed'],forward_update_changes=c['updates'],
            item_count_min=min(c['item_counts']),item_count_max=max(c['item_counts']))
    start=clocks[0][0];events=Counter();previous_stock=None
    for t,q,source in stock:
        if previous_stock is not None and t>=start:
            pt,pq,ps=previous_stock
            if source!=ps:
                events['item_delta_provider_switches']+=1
                if (pq==0)!=(q==0):events['cross_provider_physical_phase_conflicts']+=1
            elif pq==0<q:events['same_provider_zero_to_positive']+=1
            elif pq>0 and q==0:events['same_provider_positive_to_zero']+=1
        previous_stock=(t,q,source)
    gaps=[b[0]-a[0] for a,b in zip(clocks,clocks[1:])]
    return dict(status='CLOCK_EVIDENCE_AVAILABLE',clock_rows=len(clocks),first_receipt=start,last_receipt=clocks[-1][0],
        coverage_hours=(clocks[-1][0]-start)/3600,receipt_gap_seconds=quantiles(gaps),
        receipt_gaps_over180=sum(d>180 for d in gaps),providers=out,counts=dict(counts),switch_examples=switches,
        stock_event_counts_since_first_clock=dict(events),
        limitation='Stock transition counts describe adjacent deltas, not gap-certified event times. Country report clocks and aggregate item counts do not prove that Xanax appeared in every payload or certify game freshness. No carried item state becomes a new observed zero. Events across providers remain ambiguous.')


def run(source,*,model_sha):
    stock,polls,crosses,evidence,cutoff=source_data(source,item_key=KEY)
    with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='country_stock_observations'").fetchone()
        clocks=db.execute('''SELECT received_epoch,source,country_update_epoch,clock_status,item_count
            FROM country_stock_observations WHERE country='jap' AND received_epoch BETWEEN ? AND ?
            ORDER BY received_epoch,id LIMIT 200001''',(cutoff-86400,cutoff)).fetchall() if exists else []
    if len(clocks)>200000:raise ValueError('Country clock cap exceeded')
    result=analyze(clocks,stock,cutoff)
    h=History(crosses);halves=HalfPhases(crosses)
    for row in stock:h.add(row);halves.add(row)
    start=clocks[0][0] if clocks else cutoff
    result.update(model_sha=model_sha,item_key=KEY,cutoff=cutoff,clock_table_present=bool(exists),
        strict_completed_cycles_since_first_clock=sum(c.end>=start for c in h.cycles) if clocks else None,
        clean_completed_zero_halves_since_first_clock=sum(p['end']>=start for p in halves.low) if clocks else None,
        clean_completed_positive_halves_since_first_clock=sum(p['end']>=start for p in halves.high) if clocks else None,
        latest_strict_completed_cycle=h.cycles[-1].end if h.cycles else None,
        latest_strict_cycle_age_hours=(cutoff-h.cycles[-1].end)/3600 if h.cycles else None,
        prediction_models_changed=False,automatic_promotion=False,accuracy_results=False)
    return result
