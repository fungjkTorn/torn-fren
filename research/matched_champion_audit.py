"""Read-only, matched-hour native specialist versus renewal diagnostics.

Native workers receive a separate database containing ONLY evidence at the
issue clock. The sealed truth database is never passed to those workers.
Missing native adapters and timeouts are reported, never replaced by models.
This is a small development comparison, not a deployment qualification.
"""
import bisect
import importlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.japan_xanax.renewal_shadow import History, WAIT, source_data, rate_plan

ISSUES=(1792255500,)+tuple(range(1792256400,1792281601,3600))


def causal_copy(source, target, issued):
    """Copy sanitized stock tables only, cutting all evidence at issue time."""
    with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as src:
        src.execute('PRAGMA query_only=ON');src.execute('BEGIN')
        with closing(sqlite3.connect(target)) as dst:
            # Explicit schema excludes any ancillary future metadata or clocks.
            dst.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,
                timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT);
                CREATE TABLE poll_heartbeats(id INTEGER PRIMARY KEY,timestamp INTEGER,mode TEXT,success INTEGER);
                CREATE TABLE collection_gaps(id INTEGER PRIMARY KEY,start_timestamp INTEGER,end_timestamp INTEGER,reason TEXT);
                CREATE INDEX stock_item ON stock_history(country,item_name,timestamp);''')
            with dst:
                dst.executemany('INSERT INTO stock_history VALUES(?,?,?,?,?,?)',src.execute(
                    'SELECT id,timestamp,country,item_name,quantity,source FROM stock_history WHERE timestamp<=?',(issued,)))
                dst.executemany('INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,?,?)',src.execute(
                    'SELECT timestamp,mode,success FROM poll_heartbeats WHERE timestamp<=?',(issued,)))
                dst.executemany('INSERT INTO collection_gaps(start_timestamp,end_timestamp) VALUES(?,?)',src.execute(
                    'SELECT start_timestamp,CASE WHEN end_timestamp>? THEN NULL ELSE end_timestamp END FROM collection_gaps WHERE start_timestamp<=?',(issued,issued)))
    Path(target).chmod(0o400)


def native_routes():
    from research.v38_readonly_resource_probe import ALL
    return {**ALL,'uni:Red Fox Plushie':'research.v38_red_fox_single_tick',
            'can:Xanax':'research.v42_xanax_candidate_tick','uni:Xanax':'research.v42_xanax_candidate_tick'}


def native_plan(db,key,issued,timeout=12):
    route=native_routes().get(key)
    if route is None:return dict(status='NATIVE_ADAPTER_UNVERIFIED',departure=None)
    country,item=key.split(':',1)
    child="import importlib,json,sys; m=importlib.import_module(sys.argv[1]); print(json.dumps(m.predict(sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]))))"
    began=time.monotonic()
    try:
        p=subprocess.run([sys.executable,'-B','-c',child,route,str(db),country,item,str(issued)],
                         capture_output=True,text=True,timeout=timeout,check=True)
        result=json.loads(p.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        return dict(status='NATIVE_COMPUTE_TIMEOUT',departure=None,seconds=timeout)
    except (subprocess.CalledProcessError,ValueError,IndexError) as e:
        return dict(status='NATIVE_WORKER_ERROR',departure=None,error_type=type(e).__name__)
    dep=result.get('recommended_departure_timestamp')
    if dep is not None and (type(dep) is not int or not issued<=dep<=issued+WAIT):
        raise ValueError('Native departure outside fixed horizon')
    return dict(status=result.get('status'),departure=dep,route=route,
                native_generation=result.get('model_generation'),seconds=time.monotonic()-began)


def supply_audit(rows,crosses,cutoff,hours=24):
    """Observed carried-state time, NOT certified game occupancy or events."""
    start=cutoff-hours*3600; durations=Counter();events=Counter();windows=[]
    for a,b in zip(rows,rows[1:]):
        left=max(start,a[0]);right=min(cutoff,b[0])
        if right<=left:continue
        if a[2]!=b[2]:events['provider_switches']+=1
        if a[2]!=b[2] or crosses(a[0],b[0]):
            durations['ambiguous_seconds']+=right-left;continue
        durations['available_seconds' if a[1]>=30 else 'below30_seconds']+=right-left
        if a[1]>0 and b[1]==0:events['observed_true_zero_transitions']+=1
        if a[1]==0<b[1]:events['observed_restock_transitions']+=1
        if a[1]>=30>b[1]:events['observed_availability_losses']+=1
    h=History(crosses)
    for row in rows:h.add(row)
    for c in h.cycles:
        if start<=c.end<=cutoff:windows.append(dict(zero=c.zero,restock=c.restock,end=c.end,
            available_seconds=c.available,batch=c.batch))
    return dict(start=start,end=cutoff,observed_interval_seconds=dict(durations),events=dict(events),
                strict_completed_cycles=windows,
                latest_strict_cycle_age_hours=(cutoff-h.cycles[-1].end)/3600 if h.cycles else None,
                limitation='Adjacent item-delta evidence only; provider switches/gaps ambiguous. Last unclosed interval excluded. Physical depletion=0, availability target=30.')


def summarize(records):
    out={}
    for mode in sorted({r['mode'] for r in records}):
        selected=[r for r in records if r['mode']==mode];counts=Counter(r['outcome'] for r in selected)
        known=counts['SUCCESS']+counts['FAILURE'];departed=[r for r in selected if r['departure'] is not None]
        out[mode]=dict(issues=len(selected),outcomes=dict(counts),known=known,
            success_fraction=counts['SUCCESS']/known if known else None,proposal_coverage=len(departed)/len(selected),
            distinct_departure_epochs=len({r['departure'] for r in departed}),
            mean_wait_seconds=sum(r['departure']-r['issued'] for r in departed)/len(departed) if departed else None,
            statuses=dict(Counter(r['status'] for r in selected)))
    return out


def paired_native(records):
    native={r['issued']:r for r in records if r['mode']=='native_specialist'}
    out={}
    for mode in sorted({r['mode'] for r in records}-{'native_specialist'}):
        counts=Counter()
        for r in (r for r in records if r['mode']==mode):
            n=native[r['issued']]
            if r['outcome'] in ('SUCCESS','FAILURE') and n['outcome'] in ('SUCCESS','FAILURE'):
                counts['both_known']+=1
                counts['challenger_success']+=int(r['outcome']=='SUCCESS')
                counts['native_success']+=int(n['outcome']=='SUCCESS')
                counts['challenger_only_success']+=int(r['outcome']=='SUCCESS' and n['outcome']=='FAILURE')
                counts['native_only_success']+=int(n['outcome']=='SUCCESS' and r['outcome']=='FAILURE')
        out[mode]=dict(counts)
    return out


def run(source,out,*,model_sha):
    from deploy.scripts.v163_readonly_event_first_preview import exact_roster,OBS
    from research.plushie_champions.common import TRAVEL_SECONDS
    from research.quantity_rate_cycles import QuantityRateCycles
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    # Bootstrap checkout-pinned imports before loading older model adapters.
    _,_,_,_,cutoff=source_data(source)
    keys=['can:Xanax','jap:Xanax']+[k for k in sorted(exact_roster()) if k not in ('can:Xanax','jap:Xanax')]
    data={k:source_data(source,now=cutoff,item_key=k) for k in keys}
    if any(d[4]!=cutoff for d in data.values()):raise ValueError('Truth cutoff changed')
    if cutoff<ISSUES[-1]+WAIT+max(TRAVEL_SECONDS.values())+190:raise ValueError('Immature fixed window')
    all_records={k:[] for k in keys};began=time.monotonic()
    for n,issued in enumerate(ISSUES):
        causal=out/('causal-%02d.sqlite'%n)
        try:
            causal_copy(source,causal,issued)
            for key in keys:
                rows,polls,crosses,evidence,_=data[key];h=History(crosses);rate=QuantityRateCycles(crosses)
                for row in rows:
                    if row[0]>issued:break
                    h.add(row);rate.add(OBS(*row))
                pi=bisect.bisect_right(polls,issued)-1;age=issued-polls[pi] if pi>=0 else None
                flight=TRAVEL_SECONDS[key.split(':',1)[0]]
                chosen=h.plans(issued,poll_age=age,flight_seconds=flight)
                chosen['rate_current_quarter']=rate_plan(rate,key,issued,age)
                chosen['native_specialist']=native_plan(causal,key,issued)
                for mode,p in chosen.items():
                    dep=p['departure'];dep=max(dep,issued+15) if dep is not None else None
                    status=p['status']
                    if dep is not None and dep>issued+WAIT:dep=None;status='ABSTAIN_OUTSIDE_EIGHT_HOUR_HORIZON'
                    outcome,reason,_=evidence.score(dep+flight) if dep is not None else ('ABSTAIN',status,None)
                    all_records[key].append(dict(issued=issued,mode=mode,departure=dep,status=status,outcome=outcome,reason=reason))
                report=dict(item_key=key,model_sha=model_sha,truth_cutoff=cutoff,issue_epochs=ISSUES,
                    policies=summarize(all_records[key]),paired_vs_native=paired_native(all_records[key]),records=all_records[key],
                    supply=supply_audit(rows,crosses,cutoff) if key in ('can:Xanax','jap:Xanax') else None,
                    frozen_proposals=True,future_departure_reconfirmation_tested=False,automatic_promotion=False,
                    exact_owner_journal_reproduction=False,
                    limitation='Nine matched historical issue clocks, not exact owner journal timestamps. Correlated cohorts, development diagnostic only. Native unsupported/error/timeout explicit. Other models are generic challengers.')
                (out/('item-%02d.json'%keys.index(key))).write_text(json.dumps(report,sort_keys=True))
                print('MATCHED',n+1,key,json.dumps(report['policies']['native_specialist']),flush=True)
        finally:
            if causal.exists():causal.chmod(0o600);causal.unlink()
    return dict(model_sha=model_sha,items=len(keys),issue_epochs=ISSUES,seconds=time.monotonic()-began,
                native_supported=len(native_routes()),automatic_promotion=False)
