"""Versioned simulated trips: revise before departure, then freeze exactly once.

Arrival success does not depend on identifying a restock. Original forecasts,
old outcomes and old target links are never edited or discarded.
"""
import bisect
from collections import Counter
from copy import deepcopy
import json
import sqlite3
from services.restock_signatures import learn,events,clean_pairs

POLICY='RECOMMENDED_DEPARTURE_FREEZE_V4'


def initialize(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS simulation_profiles(item TEXT,model_sha TEXT,policy TEXT,payload TEXT,
        PRIMARY KEY(item,model_sha,policy));
    CREATE TABLE IF NOT EXISTS simulation_cursors(item TEXT,model_sha TEXT,policy TEXT,issued INTEGER,payload TEXT,
        PRIMARY KEY(item,model_sha,policy));
    CREATE TABLE IF NOT EXISTS simulated_trips(item TEXT,model_sha TEXT,policy TEXT,id TEXT,payload TEXT,
        PRIMARY KEY(item,model_sha,policy,id));
    CREATE TABLE IF NOT EXISTS simulated_trip_outcomes(item TEXT,model_sha TEXT,policy TEXT,id TEXT,cutoff INTEGER,payload TEXT,
        PRIMARY KEY(item,model_sha,policy,id,cutoff));
    CREATE TABLE IF NOT EXISTS simulation_changes(item TEXT,model_sha TEXT,policy TEXT,issued INTEGER,id TEXT,kind TEXT,payload TEXT,
        PRIMARY KEY(item,model_sha,policy,issued,id,kind));
    CREATE TABLE IF NOT EXISTS simulation_restocks(item TEXT,model_sha TEXT,policy TEXT,epoch INTEGER,payload TEXT,
        PRIMARY KEY(item,model_sha,policy,epoch));
    ''')
    for table in ('simulation_profiles','simulated_trips','simulated_trip_outcomes','simulation_changes','simulation_restocks'):
        for verb in ('UPDATE','DELETE'):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{verb.lower()} BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT,'simulation evidence is append-only'); END")


def history(source,key,cutoff):
    country,item=key.split(':',1)
    rows=source.execute('''SELECT timestamp,quantity,source FROM stock_history
        WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id''',(country,item,cutoff)).fetchall()
    gaps=source.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=?',(cutoff,)).fetchall()
    return rows,gaps


def profile(db,source,key,sha,start):
    old=db.execute('SELECT payload FROM simulation_profiles WHERE item=? AND model_sha=? AND policy=?',(key,sha,POLICY)).fetchone()
    if old:return json.loads(old[0])
    rows,gaps=history(source,key,start)
    result=learn(rows,gaps,start)
    db.execute('INSERT INTO simulation_profiles VALUES(?,?,?,?)',(key,sha,POLICY,json.dumps(result,sort_keys=True)))
    return result


def candidate(row,observed):
    d=row.get('decision') or {};dep=d.get('estimated_departure_epoch');arr=d.get('estimated_arrival_epoch')
    if type(dep) is not int or type(arr) is not int:return None
    selected=d.get('selected_restock_event_index');f=row.get('forecast') or {}
    event=(f.get('current_stock_window') or {}) if selected==0 else next((e for e in d.get('forecast_events',[]) if e['index']==selected),{})
    start=event.get('predicted_restock_epoch',arr);end=event.get('predicted_stock_below_30_epoch',d.get('estimated_departure_deadline_epoch',dep)+(arr-dep))
    stamp=row.get('published_epoch',row['asof_epoch'])
    # The native forecast only knew source data through its issue time.
    # A restock between inference and publication must not shift event 1
    # onto the following physical restock.
    prior=[e for e in observed if e['epoch']<=row['asof_epoch']]
    return {'departure_epoch':dep,'arrival_epoch':arr,'issued_epoch':row['asof_epoch'],
        'published_epoch':stamp,'selected_event_index':selected,
        'window_start':start,'window_end':max(end,arr),
        'restock_anchor':prior[-1]['epoch'] if selected==0 and prior and prior[-1]['epoch']>=row.get('_availability_anchor',0) else None,
        'episode_anchor':('restock:'+str(prior[-1]['epoch']) if prior and prior[-1]['epoch']>=row.get('_availability_anchor',0) else 'availability:'+str(row.get('_availability_anchor',0))) if selected==0 else None,
        'origin_opening':row.get('_availability_anchor',0),
        'target_offset':selected if type(selected) is int and selected>0 else 0,
        'valid_until':d.get('valid_until_epoch',row.get('valid_until_epoch',stamp+180)),
        'reason':d.get('reason'),'forecast':event}


def same_episode(a,b):
    # A newly observed reset creates a fresh current-stock test, even if stock
    # never crossed 30. A future forecast becoming current remains one test.
    if a.get('episode_anchor') is not None and b.get('episode_anchor') is not None:
        return a['episode_anchor']==b['episode_anchor']
    if a['selected_event_index']==0 and b['selected_event_index']!=0:return False
    if a['selected_event_index']!=0 and b['selected_event_index']==0 and a.get('resolved_opening') is not None:
        return a['resolved_opening']==b['origin_opening'] and (b['restock_anchor'] is None or b['restock_anchor']==b['origin_opening'])
    if a['selected_event_index']!=0 and b['selected_event_index']!=0:
        if a.get('resolved_opening') is not None:return False
        return a.get('remaining_offset',a['target_offset'])==b['target_offset']
    return max(a['window_start'],b['window_start'])<=min(a['window_end'],b['window_end'])


def advance(state,row,observed,now):
    """Pure chronological state machine; no arrival outcomes influence choices."""
    state=deepcopy(state);changes=[];frozen=[]
    available=row.get('_availability_openings',[]) if row else []
    for plan in state['completed']+([state['active']] if state.get('active') else []):
        if plan.get('target_offset') and available:
            before=bisect.bisect_right(available,plan['origin_opening'])
            resolved=before+plan['target_offset']-1
            if resolved<len(available):plan['resolved_opening']=available[resolved]
            else:plan['remaining_offset']=plan['target_offset']-(len(available)-before)
    def change(kind,plan,**extra):changes.append(dict(kind=kind,id=plan['id'],**extra))
    def freeze(plan):
        if plan['departure_epoch']>plan['valid_until']:
            change('WITHDRAWN_STALE_BEFORE_DEPARTURE',plan);return
        if any(same_episode(old,plan) for old in state['completed']):
            change('SUPPRESSED_ALREADY_TESTED_TARGET',plan);return
        frozen.append(deepcopy(plan))
        # Keep durable target identities even after their predicted window
        # expires. A later extension cannot authorize another test.
        identity={k:deepcopy(v) for k,v in plan.items() if k not in ('forecast','reason','issued_epoch','published_epoch','valid_until','departure_epoch','arrival_epoch')}
        state['completed'].append(identity)
        change('FROZEN_AT_RECOMMENDED_DEPARTURE',plan)
    active=state.get('active')
    if active and active['departure_epoch']<now:
        freeze(active);active=None
    if row is not None:
        new=candidate(row,observed)
        if new and new['departure_epoch']<now:
            new=None
        if new is None:
            if active:change('WITHDRAWN_NO_ADVICE',active)
            active=None
        else:
            if active and same_episode(active,new):
                new['id']=active['id']
                if (active['departure_epoch'],active['arrival_epoch'])!=(new['departure_epoch'],new['arrival_epoch']):
                    change('REVISED_BEFORE_DEPARTURE',new,old_departure=active['departure_epoch'],new_departure=new['departure_epoch'])
                    if new['departure_epoch']>active['departure_epoch']:
                        change('POSTPONED_BEFORE_DEPARTURE',new,old_departure=active['departure_epoch'],new_departure=new['departure_epoch'])
                active=new
            else:
                if active:change('WITHDRAWN_TARGET_CHANGED',active)
                if any(same_episode(old,new) for old in state['completed']):active=None
                else:
                    new['id']=str(row['asof_epoch']);active=new;change('NEW_RECOMMENDATION',new)
    if active and active['departure_epoch']<=now:
        freeze(active);active=None
    state['active']=active
    return state,frozen,changes


def grade_trip(arrival,rows,polls,gaps,cutoff,country_receipts):
    if cutoff<arrival+180:return {'status':'PENDING','reason':'ARRIVAL_NOT_MATURE'}
    i=bisect.bisect_right(polls,arrival)-1;j=bisect.bisect_left(polls,arrival)
    if i<0 or j>=len(polls):return {'status':'UNKNOWN','reason':'NO_POLL_BRACKET'}
    before,after=polls[i],polls[j]
    if arrival-before>180 or after-arrival>180:return {'status':'UNKNOWN','reason':'MISSING_ARRIVAL_POLLS'}
    if any(lo<=after and (hi is None or hi>=before) for lo,hi in gaps):return {'status':'UNKNOWN','reason':'ARRIVAL_COLLECTION_GAP'}
    receipts=[r for r in country_receipts if r[0]<=arrival]
    if not receipts or receipts[-1][2]!='REPORTED' or receipts[-1][1] is None or not 0<=arrival-receipts[-1][1]<=180 or arrival-receipts[-1][0]>180:
        return {'status':'UNKNOWN','reason':'COUNTRY_EVIDENCE_UNAVAILABLE_AT_ARRIVAL'}
    times=[r[0] for r in rows];a=bisect.bisect_right(times,before)-1;b=bisect.bisect_right(times,after)-1
    if a<0 or b<0:return {'status':'UNKNOWN','reason':'NO_ITEM_STATE_AT_ARRIVAL'}
    segment=rows[a:b+1]
    if len({r[1]>30 for r in segment})!=1:return {'status':'UNKNOWN','reason':'AVAILABILITY_CHANGED_INSIDE_POLL_BRACKET'}
    return {'status':'SUCCESS' if segment[0][1]>30 else 'FAILURE',
        'reason':'POLL_BACKED_SIMULATED_ARRIVAL','pre_quantity':rows[a][1],
        'post_quantity':rows[b][1],'pre_poll':before,'post_poll':after,
        'failure_class':None if segment[0][1]>30 else 'ZERO_STOCK' if all(r[1]==0 for r in segment) else 'LOW_STOCK_1_TO_30'}


def summary(db,source,*,item_key,model_sha,cutoff):
    key=item_key;sha=model_sha;args=(key,sha,POLICY)
    start=db.execute('SELECT MIN(issued) FROM issues WHERE item=? AND model_sha=?',(key,sha)).fetchone()[0]
    if start is None:return {'label':'Last 10 simulated trips','evidence_policy':POLICY,'trips':[],'known':0,'successes':0,'failures':0,'unknown':0,'pending':0,'success_fraction':None}
    sig=profile(db,source,key,sha,start);rows,gaps=history(source,key,cutoff);observed=events(rows,gaps,sig)
    for event in observed:
        if event['epoch']>=start:
            db.execute('INSERT OR IGNORE INTO simulation_restocks VALUES(?,?,?,?,?)',(*args,event['epoch'],json.dumps(event,sort_keys=True)))
    checkpoint=db.execute('SELECT issued,payload FROM simulation_cursors WHERE item=? AND model_sha=? AND policy=?',args).fetchone()
    state=json.loads(checkpoint[1]) if checkpoint else {'active':None,'completed':[]}
    last=checkpoint[0] if checkpoint else -1
    entries=db.execute('''SELECT i.issued,i.payload,p.published FROM issues i JOIN publications p ON p.issued=i.issued
        WHERE i.item=? AND i.model_sha=? AND i.issued>? AND p.published<=? ORDER BY p.published,i.issued''',(key,sha,last,cutoff)).fetchall()
    def save(frozen,changes,issued):
        for trip in frozen:
            db.execute('INSERT OR IGNORE INTO simulated_trips VALUES(?,?,?,?,?)',(*args,trip['id'],json.dumps(trip,sort_keys=True)))
        for c in changes:
            db.execute('INSERT OR IGNORE INTO simulation_changes VALUES(?,?,?,?,?,?,?)',(*args,issued,c['id'],c['kind'],json.dumps(c,sort_keys=True)))
    availability=[b[0] for a,b in clean_pairs(rows,gaps) if a[1]<=30<b[1]]
    for entry in entries:
        row=json.loads(entry[1]);row['published_epoch']=entry[2]
        pos=bisect.bisect_right(availability,entry[0])-1
        row['_availability_anchor']=availability[pos] if pos>=0 else 0
        row['_availability_openings']=availability[:bisect.bisect_right(availability,entry[2])]
        state,frozen,changes=advance(state,row,observed,entry[2]);save(frozen,changes,entry[0])
        db.execute('''INSERT INTO simulation_cursors VALUES(?,?,?,?,?) ON CONFLICT(item,model_sha,policy)
            DO UPDATE SET issued=excluded.issued,payload=excluded.payload''',(*args,entry[0],json.dumps(state,sort_keys=True)))
    # A scheduled departure can fall between publications. Wait for the next
    # chronological publication before advancing past it, so backfill and live
    # execution follow exactly the same revision order.
    polls=[r[0] for r in source.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp",(cutoff,))]
    has_clock=source.execute("SELECT 1 FROM sqlite_master WHERE name='country_stock_observations'").fetchone()
    receipts=source.execute('SELECT received_epoch,country_update_epoch,clock_status FROM country_stock_observations WHERE country=? AND received_epoch<=? ORDER BY received_epoch,id',(key.split(':')[0],cutoff)).fetchall() if has_clock else []
    trips=[]
    for entry in db.execute('SELECT id,payload FROM simulated_trips WHERE item=? AND model_sha=? AND policy=?',args).fetchall():
        trip=json.loads(entry[1]);old=db.execute('SELECT payload FROM simulated_trip_outcomes WHERE item=? AND model_sha=? AND policy=? AND id=? ORDER BY cutoff DESC LIMIT 1',(*args,entry[0])).fetchone()
        outcome=json.loads(old[0]) if old else None
        if not outcome or outcome['status']=='PENDING':
            outcome=grade_trip(trip['arrival_epoch'],rows,polls,gaps,cutoff,receipts)
            db.execute('INSERT OR IGNORE INTO simulated_trip_outcomes VALUES(?,?,?,?,?,?)',(*args,entry[0],cutoff,json.dumps(outcome,sort_keys=True)))
        trip['outcome']=outcome;trip['restock_identity_status']='OBSERVED' if trip['restock_anchor'] else 'UNCONFIRMED_SEPARATE_FROM_ARRIVAL'
        trips.append(trip)
    trips.sort(key=lambda r:r['departure_epoch'],reverse=True);latest=trips[:10]
    counts=Counter(t['outcome']['status'] for t in latest);known=counts['SUCCESS']+counts['FAILURE']
    changes={r[0]:r[1] for r in db.execute('SELECT kind,COUNT(*) FROM simulation_changes WHERE item=? AND model_sha=? AND policy=? GROUP BY kind',args)}
    restocks=[json.loads(r[0]) for r in db.execute('SELECT payload FROM simulation_restocks WHERE item=? AND model_sha=? AND policy=? ORDER BY epoch',args)]
    tested={t['restock_anchor'] for t in trips if t['restock_anchor'] is not None}
    identities=Counter(('observed:'+str(plan['resolved_opening']) if plan.get('resolved_opening') is not None else
        'observed:'+plan['episode_anchor'].split(':',1)[1] if plan.get('episode_anchor') is not None else
        'future:'+str(plan['origin_opening'])+':'+str(plan['target_offset'])) for plan in state['completed'])
    duplicate_identities={identity:count for identity,count in identities.items() if count>1}
    return {'label':'Last 10 frozen simulated trips','evidence_policy':POLICY,'trips':latest,
        'known':known,'successes':counts['SUCCESS'],'failures':counts['FAILURE'],
        'unknown':counts['UNKNOWN'],'pending':counts['PENDING'],
        'success_fraction':counts['SUCCESS']/known if known else None,
        'simulated_trips_total':len(trips),'recorded_forecast_revisions':db.execute('SELECT COUNT(*) FROM issues WHERE item=? AND model_sha=?',(key,sha)).fetchone()[0],
        'observed_restocks_since_start':len(restocks) if sig['status']=='LEARNED' else None,'restock_profile':sig,
        'restock_events':restocks[-10:],'revision_counts':changes,
        'restocks_without_confirmed_test_link':sum(e['epoch'] not in tested for e in restocks),
        'restock_identity_does_not_gate_arrival_outcome':True,
        'active_recommendation':state['active'],'coverage_start_epoch':start,
        'target_identity_audit':{'duplicate_target_groups':len(duplicate_identities),'duplicates':duplicate_identities,
            'retained_completed_identities':len(state['completed'])},
        'percentage_withheld_for_unmatched_misses':False,
        'rate_status':'KNOWN_SIMULATED_TRIPS' if known else 'UNKNOWN_RESULTS' if counts['UNKNOWN'] else 'AWAITING_ARRIVALS' if counts['PENDING'] else 'AWAITING_DEPARTURE',
        'actual_player_trips_required':False,'historical_rates_included':False}
