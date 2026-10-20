"""Isolated all24 specialist + physical-zero challenger capture. Research only.

No website, collector, existing journals, cache, timer or model routing writes.
Japan's legacy threshold-window restock anchor is explicitly incompatible;
its eight physical-zero challenger variants remain tested on every cycle.
"""
import argparse
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path

# Pin BEFORE v163 can be imported. Its VM compatibility bootstrap otherwise
# replaces research.__path__ with the older staged package; setting these
# variables later inside source_data cannot undo that earlier path mutation.
ROOT=Path(__file__).resolve().parents[1]
os.environ['TORNFREN_REPLAY_WORK']=str(ROOT)
os.environ['TORNFREN_REPLAY_PINNED_RESEARCH']=str(ROOT/'research')

from research.japan_xanax.renewal_shadow import History,source_data,rate_plan,MODES,STEP,WAIT
from research.matched_champion_audit import native_routes
from research.plushie_champions.common import TRAVEL_SECONDS

ARTIFACTS=Path('/home/ubuntu/torn-fren-private-models')
CACHE=Path('/var/lib/torn-fren-v47/online_expert_cache.db')
SPECIAL='specialist_control'


def normalize(raw,*,queried,published,heartbeat,flight):
    """Never move a stale target to publication and count it as the same plan."""
    dep=raw.get('departure');status=raw.get('status','MODEL_ABSTAINED')
    if dep is not None:
        if type(dep) is not int:raise ValueError('Noninteger departure')
        dep=max(dep,queried+15)
        if dep<published:dep=None;status='DEPARTURE_PASSED_BEFORE_PUBLICATION'
        elif dep>queried+WAIT:dep=None;status='OUTSIDE_EIGHT_HOUR_HORIZON'
    if not 0<=published-heartbeat<=180:dep=None;status='SOURCE_EXPIRED_BEFORE_PUBLICATION'
    eligible=(dep is not None and published<=dep<queried+STEP and dep-heartbeat<=180)
    return dict(status=status,departure=dep,arrival=dep+flight if dep is not None else None,
        executable_before_next_recheck=eligible,valid_until=min(queried+STEP,heartbeat+180))


def specialist(snapshot,key,queried):
    if key=='jap:Xanax':
        return dict(departure=None,status='LEGACY_30_STOCK_RESTOCK_ANCHOR_INCOMPATIBLE',
                    identity='V8_LEGACY_EXCLUDED; ZERO_CHALLENGERS_INCLUDED')
    child="""import importlib,json,sys,types
p=types.ModuleType('services.yata_api')
def forbidden(*a,**k):raise RuntimeError('HTTP forbidden in private shadow inference')
p.get_country_stock=forbidden
sys.modules['services.yata_api']=p
db,key,q=sys.argv[1],sys.argv[2],int(sys.argv[3]);country,item=key.split(':',1)
if key in ('arg:Monkey Plushie','swi:Chamois Plushie'):
 from research.v66_monkey_readonly_selector_probe import audit
 r=audit(db,sys.argv[4],target='monkey' if country=='arg' else 'chamois')
 dep=r.get('recommended_departure_timestamp');identity='CHECKPOINT4_EXACT_CACHE_AND_ONE_SLOT_PARITY'
elif key in ('chi:Panda Plushie','sou:Lion Plushie'):
 from research.v52_pair_trained_tick import predict
 from research.v81_pair_forward_comparison import PINS
 from pathlib import Path
 target='panda' if country=='chi' else 'lion'
 r=predict(db,target,q,Path(sys.argv[5])/(target+'_selector_artifact.json'),PINS[target])
 dep=r.get('research_departure_timestamp');identity='V50_PINNED_CAUSAL_SELECTOR_'+PINS[target]
else:
 from research.matched_champion_audit import native_routes
 route=native_routes()[key];r=importlib.import_module(route).predict(db,country,item,q)
 dep=r.get('recommended_departure_timestamp');identity=route
print(json.dumps(dict(departure=dep,status=r.get('status','MODEL_ABSTAINED'),identity=identity,diagnostic=r)))
"""
    try:
        p=subprocess.run([sys.executable,'-B','-c',child,str(snapshot),key,str(queried),str(CACHE),str(ARTIFACTS)],
                         capture_output=True,text=True,timeout=25,check=True)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (subprocess.TimeoutExpired,subprocess.CalledProcessError,ValueError,IndexError) as e:
        return dict(departure=None,status='SPECIALIST_ERROR_'+type(e).__name__)


def setup(state,sha):
    state=Path(state).expanduser()
    if state.is_symlink() or state.parent.is_symlink():raise ValueError('Symlink state forbidden')
    state=state.resolve()
    if Path.home().resolve() not in state.parents:raise ValueError('Use a new state directory under your home')
    marker=state/'shadow-source.json';expected=dict(model_sha=sha,kind='ALL24_SPECIALIST_SHADOW_V1')
    if state.exists():
        if not marker.is_file() or json.loads(marker.read_text())!=expected:raise ValueError('Existing directory is not this isolated shadow')
    else:
        state.mkdir(mode=0o700,parents=True);marker.write_text(json.dumps(expected))
    for name in ('plans.sqlite','snapshot.sqlite','capture.lock'):
        if (state/name).is_symlink():raise ValueError('Symlink state file forbidden')
    return state


def store(db,*,key,mode,raw,queried,published,heartbeat,sha,commit=True):
    record=dict(raw,**normalize(raw,queried=queried,published=published,heartbeat=heartbeat,
                              flight=TRAVEL_SECONDS[key.split(':',1)[0]]))
    record.update(item_key=key,mode=mode,issued=queried,published=published,source_cutoff=heartbeat,
                  poll_age_seconds=queried-heartbeat,model_sha=sha,physical_depletion_quantity=0,
                  arrival_target=30,grace_seconds=10,actual_flights=False,website_publication=False)
    db.execute('INSERT INTO plans VALUES(?,?,?,?)',(queried,key,mode,json.dumps(record,sort_keys=True)))
    if commit:db.commit()


def capture_inputs(source,keys,*,now=None):
    """One readonly transaction; shared poll/gap checks once for all24.

    Capture needs rows and gap guards, not 25 arrival-truth evaluators. Retain
    the same evidence limits/row validation as source_data, without repeatedly
    materializing the identical successful-poll history for every item.
    """
    from research.continuous_departure_replay import model,MAX_POLLS
    if len(keys)!=24 or set(keys)!=set(model.exact_roster()):raise ValueError('Exact24 capture inputs required')
    clock=int(time.time()) if now is None else now
    with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=12)) as c:
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        heartbeat=model.read_heartbeat(c)
        if heartbeat is None:raise ValueError('Missing successful heartbeat')
        cutoff=min(clock,heartbeat)
        polls=c.execute("SELECT COUNT(*) FROM (SELECT 1 FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? LIMIT ?)",
                        (cutoff,MAX_POLLS+1)).fetchone()[0]
        gaps=c.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?',
                       (cutoff,model.MAX_GAPS+1)).fetchall()
        if polls>MAX_POLLS or len(gaps)>model.MAX_GAPS:raise ValueError('Source evidence cap exceeded')
        rows={}
        for key in keys:
            country,item=key.split(':',1)
            values=c.execute('SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT ?',
                             (country,item,cutoff,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
            if len(values)>model.MAX_ITEM_CHANGE_ROWS:raise ValueError('Source evidence cap exceeded')
            if any(type(t) is not int or type(q) is not int or q<0 or not s for t,q,s in values):raise ValueError('Invalid stock observations')
            rows[key]=values
    return rows,model._gap_index(gaps,cutoff),cutoff


def tick(source,state,sha,db):
    from research.v65_private_mirror_shadow_tick import snapshot_with_retry
    from research.v38_capacity_guard import inspect as capacity
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import exact_roster,OBS
    keys=sorted(exact_roster())
    if len(keys)!=24 or len(native_routes())!=19:raise ValueError('Roster/source identity changed')
    admission=capacity()
    if not admission['allowed']:
        return dict(status='ALL24_SHADOW_DEFERRED_CPU_PRESSURE',items_recorded=0,
                    capacity=admission,next_check_seconds=30)
    snapshot=state/'snapshot.sqlite';started=time.monotonic()
    snap=snapshot_with_retry(source,snapshot)
    if snap.get('status')!='PRIVATE_SNAPSHOT_READY' or not snap.get('published'):
        raise ValueError('Fresh isolated snapshot unavailable')
    inputs,crosses,heartbeat=capture_inputs(snapshot,keys)
    cutoffs={};generic_rows=0;statuses=Counter()
    # All24 receive all8 physical-zero challengers before native compute.
    for key in keys:
        queried=int(time.time());rows=inputs[key]
        cutoffs[key]=heartbeat;history=History(crosses);rate=QuantityRateCycles(crosses)
        if not 0<=queried-heartbeat<=180:raise ValueError('Snapshot expired before full roster generation')
        for row in rows:history.add(row);rate.add(OBS(*row))
        selected=history.plans(queried,poll_age=queried-heartbeat,flight_seconds=TRAVEL_SECONDS[key.split(':',1)[0]])
        selected['rate_current_quarter']=rate_plan(rate,key,queried,queried-heartbeat)
        if set(selected)!=set(MODES):raise ValueError('Generic family roster changed')
        published=int(time.time())
        for mode,raw in selected.items():
            store(db,key=key,mode=mode,raw=dict(raw,identity='PHYSICAL_ZERO_CHALLENGER'),queried=queried,
                  published=published,heartbeat=heartbeat,sha=sha,commit=False);generic_rows+=1
    for key in keys:
        queried=int(time.time());heartbeat=cutoffs[key]
        raw=(specialist(snapshot,key,queried) if queried-heartbeat<=150 else
             dict(departure=None,status='SOURCE_TOO_OLD_FOR_SPECIALIST_COMPUTE'))
        published=int(time.time());r=normalize(raw,queried=queried,published=published,heartbeat=heartbeat,
                                             flight=TRAVEL_SECONDS[key.split(':',1)[0]])
        statuses[r['status']]+=1
        store(db,key=key,mode=SPECIAL,raw=raw,queried=queried,published=published,heartbeat=heartbeat,sha=sha,commit=False)
    return dict(status='ALL24_SPECIALIST_SHADOW_RECORDED',items=24,generic_models_per_item=8,
        specialist_rows=24,generic_rows=generic_rows,specialist_statuses=dict(statuses),
        japan_zero_models_tested=8,legacy_japan_excluded=True,seconds=round(time.monotonic()-started,2),
        accuracy_verified=False,website_publication=False)


def capture(source,state,sha,*,duration=28800,once=False,startup_wait=3600,clock=time.monotonic,sleeper=time.sleep):
    from research.v60_private_snapshot_probe import approved_collector_source
    if not approved_collector_source(source):raise ValueError('Only approved collector source allowed')
    os.umask(0o077);state=setup(state,sha)
    with (state/'capture.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with closing(sqlite3.connect(state/'plans.sqlite')) as db:
            db.executescript('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE IF NOT EXISTS plans(issued INTEGER,item_key TEXT,mode TEXT,record TEXT,PRIMARY KEY(issued,item_key,mode));CREATE TABLE IF NOT EXISTS cycles(attempted_at INTEGER PRIMARY KEY,status TEXT,summary TEXT);')
            db.execute('INSERT OR IGNORE INTO metadata VALUES(?,?)',('model_sha',sha));db.commit()
            if db.execute("SELECT value FROM metadata WHERE key='model_sha'").fetchone()[0]!=sha:raise ValueError('Journal source mismatch')
            waiting_until=clock()+startup_wait;until=None
            while clock()<(until if until is not None else waiting_until):
                began=clock();attempted=int(time.time());failure=None
                try:result=tick(source,state,sha,db)
                except (OSError,ValueError,sqlite3.Error) as e:
                    db.rollback() # A failed cycle must not expose a subset of the roster.
                    failure=e;result=dict(status='FULL_ROSTER_CAPTURE_UNAVAILABLE',error_type=type(e).__name__)
                db.execute('INSERT INTO cycles VALUES(?,?,?)',(attempted,result['status'],json.dumps(result,sort_keys=True)));db.commit()
                print(json.dumps(result,sort_keys=True),flush=True)
                if once:
                    return result
                if until is None and result.get('status')=='ALL24_SPECIALIST_SHADOW_RECORDED':
                    until=clock()+duration
                    print(json.dumps(dict(status='ALL24_COLLECTION_WINDOW_STARTED',duration_seconds=duration)),flush=True)
                deadline=until if until is not None else waiting_until
                interval=30 if until is None else STEP
                sleeper(min(max(0,deadline-clock()),max(1,interval-(clock()-began))))
            if until is None:
                result=dict(status='ALL24_STARTUP_WAIT_EXPIRED',startup_wait_seconds=startup_wait,collection_started=False)
                print(json.dumps(result),flush=True)
                return result


def status(state,sha):
    state=Path(state).expanduser()
    if not state.exists():return dict(status='ALL24_STATE_NOT_CREATED_YET',recorded_items=0,collection_started=False)
    state=state.resolve(strict=True)
    if json.loads((state/'shadow-source.json').read_text()).get('model_sha')!=sha:raise ValueError('Wrong shadow identity')
    with closing(sqlite3.connect((state/'plans.sqlite').as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('PRAGMA query_only=ON')
        latest=c.execute('SELECT attempted_at,status,summary FROM cycles ORDER BY attempted_at DESC LIMIT 1').fetchone()
        counts=dict(c.execute('SELECT status,COUNT(*) FROM cycles GROUP BY status'))
        items,rows=c.execute('SELECT COUNT(DISTINCT item_key),COUNT(*) FROM plans').fetchone()
        last_record=c.execute('SELECT record FROM plans ORDER BY rowid DESC LIMIT 1').fetchone()
        last=json.loads(last_record[0]).get('published') if last_record else None
    running=False
    with (state/'capture.lock').open('r') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:running=True
    from research.v38_idle_admission import inspect as measured_cpu
    measured=measured_cpu(sample_seconds=1)
    diagnostics={k:measured[k] for k in ('idle_fraction','psi_some_avg10','psi_full_avg10','steal_fraction','cpu_slots','one_minute_load','reason') if k in measured}
    return dict(status='ALL24_SHADOW_STATUS',recorder_running=running,recorded_items=items,plan_rows=rows,
        measured_cpu_diagnostics_only=diagnostics,
        last_publication=last,attempt_statuses=counts,last_attempt=latest[0] if latest else None,
        last_attempt_status=latest[1] if latest else None,
        last_attempt_detail=json.loads(latest[2]) if latest else None,
        collection_started=counts.get('ALL24_SPECIALIST_SHADOW_RECORDED',0)>0)


def score(source,state,sha):
    journal=Path(state).expanduser().resolve(strict=True)/'plans.sqlite'
    with closing(sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        if c.execute("SELECT value FROM metadata WHERE key='model_sha'").fetchone()[0]!=sha:raise ValueError('Wrong model source')
        raw=c.execute('SELECT issued,item_key,mode,record FROM plans ORDER BY rowid LIMIT 100001').fetchall()
        has_cycles=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cycles'").fetchone()
        attempt_rows=c.execute('SELECT attempted_at,status FROM cycles ORDER BY attempted_at LIMIT 10001').fetchall() if has_cycles else []
        if len(attempt_rows)>10000:raise ValueError('Capture attempt cap exceeded')
        attempts=dict(Counter(status for _,status in attempt_rows)) if has_cycles else None
    if len(raw)>100000:raise ValueError('Journal cap exceeded')
    records=[]
    for issued,key,mode,encoded in raw:
        r=json.loads(encoded)
        if (r['issued'],r['item_key'],r['mode'],r['model_sha'])!=(issued,key,mode,sha):raise ValueError('Journal record identity mismatch')
        if (r.get('physical_depletion_quantity'),r.get('arrival_target'),r.get('grace_seconds'))!=(0,30,10):raise ValueError('Journal stock contract mismatch')
        records.append(r)
    from research.full_roster_capture_review import review
    from deploy.scripts.v163_readonly_event_first_preview import exact_roster
    capture_diagnostics=review(records,attempt_rows,roster=sorted(exact_roster()),modes=MODES+(SPECIAL,))
    first={};near={};statuses=Counter()
    for r in sorted(records,key=lambda r:(r['issued'],r['item_key'],r['mode'])):
        identity=(r['item_key'],r['mode'],r['issued']//3600)
        first.setdefault(identity,r);statuses[r['status']]+=1
        if r['executable_before_next_recheck']:near.setdefault(identity,r)
    evidence={};cutoff=None
    for records in (first,near):
        for r in records.values():
            key=r['item_key']
            if key not in evidence:
                data=source_data(source,now=cutoff,item_key=key)
                if cutoff is None:cutoff=data[4]
                if cutoff!=data[4]:raise ValueError('Truth clock moved backwards')
                evidence[key]=data[3]
    def counts(records):
        groups=defaultdict(Counter)
        for identity,denominator in first.items():
            key=denominator['item_key']+'|'+denominator['mode'];c=groups[key];c['hourly_opportunities']+=1
            r=records.get(identity)
            if r is None:c['NO_NEAR_TERM_ELIGIBILITY']+=1;continue
            if r['arrival'] is not None:c['proposals']+=1
            outcome=evidence[r['item_key']].score(r['arrival'])[0] if r['arrival'] is not None else 'ABSTAIN'
            c[outcome]+=1
        result={}
        for key,c in sorted(groups.items()):
            known=c['SUCCESS']+c['FAILURE']
            result[key]=dict(c,known=known,success_fraction=c['SUCCESS']/known if known else None,
                proposal_coverage=c['proposals']/c['hourly_opportunities'])
        return result
    return dict(model_sha=sha,records=len(raw),truth_cutoff=cutoff,capture_attempt_statuses=attempts,capture_diagnostics=capture_diagnostics,first_hourly_frozen=counts(first),
        first_hourly_near_term_eligible=counts(near),statuses=dict(statuses),actual_flights=False,
        limitation='Near-term eligibility is not actual execution. Frozen future plans require later reconfirmation; no calibrated probability or automatic promotion.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('preflight','record','score','status'))
    p.add_argument('--source',default='/opt/torn-fren/data/stock_history.db');p.add_argument('--state',required=True)
    p.add_argument('--model-sha',required=True);p.add_argument('--duration-seconds',type=int,default=28800)
    p.add_argument('--startup-wait-seconds',type=int,default=3600)
    p.add_argument('--compact',action='store_true')
    a=p.parse_args();head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    if a.action!='score' and head!=a.model_sha:raise ValueError('Pinned checkout differs')
    if not 60<=a.duration_seconds<=86400:raise ValueError('Bounded duration required')
    if not 30<=a.startup_wait_seconds<=7200:raise ValueError('Bounded startup wait required')
    if a.action=='status':print(json.dumps(status(a.state,a.model_sha),sort_keys=True))
    elif a.action=='score':
        result=score(a.source,a.state,a.model_sha)
        if not a.compact:print(json.dumps(result,sort_keys=True))
        else:
            from deploy.scripts.v163_readonly_event_first_preview import exact_roster
            groups=result['first_hourly_near_term_eligible']
            def cell(key,mode):
                r=groups.get(key+'|'+mode,{})
                return '%s/%s %s/%s %s/%s'%(r.get('SUCCESS',0),r.get('known',0),r.get('proposals',0),
                    r.get('hourly_opportunities',0),r.get('UNKNOWN',0),r.get('PENDING',0))
            print('First near-term advice per item/model/UTC-hour; sampled arrivals, NOT actual flights.')
            print('Cells: success/known eligible/hourly-opportunities unknown/pending.')
            print('Item | specialist | physical-zero rate | specialist statuses (all captured rows)')
            for key in sorted(exact_roster()):
                statuses=result['capture_diagnostics']['models'][key+'|'+SPECIAL]['statuses']
                print(key+' | '+cell(key,SPECIAL)+' | '+cell(key,'rate_current_quarter')+' | '+json.dumps(statuses,sort_keys=True))
            print('Japan: legacy specialist excluded; all eight physical-zero challenger models are tested:')
            for mode in MODES:print(mode+' | '+cell('jap:Xanax',mode))
            print(json.dumps(dict(records=result['records'],truth_cutoff=result['truth_cutoff'],model_sha=a.model_sha,
                                  capture_attempt_statuses=result['capture_attempt_statuses'],
                                  complete24_row_batches=result['capture_diagnostics']['complete24_row_batches'],
                                  incomplete_row_batches=result['capture_diagnostics']['incomplete_row_batches'],
                                  observed_active_window_hours=result['capture_diagnostics']['active_window_observed_hours'],
                                  hours_without_any_capture=len(result['capture_diagnostics']['active_hours_without_any_capture']))))
    else:
        result=capture(a.source,a.state,a.model_sha,duration=a.duration_seconds,once=a.action=='preflight',startup_wait=a.startup_wait_seconds)
        if a.action=='preflight' and result.get('status')!='ALL24_SPECIALIST_SHADOW_RECORDED':raise SystemExit(2)
        if result and result.get('status')=='ALL24_STARTUP_WAIT_EXPIRED':raise SystemExit(3)


if __name__=='__main__':main()
