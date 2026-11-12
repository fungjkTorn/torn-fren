"""Predeclared later-period execution check; research only, no promotion.

October18 09:00-12:00 UTC starts were not scored in the preceding native
comparison. Four hourly starts are primary; thirteen quarter-hour starts are
secondary, correlated sensitivity checks. This small window is NOT a release
qualification by itself. Generic challengers never stand in for specialists.
"""
import bisect
import json
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path

from research.matched_champion_audit import native_plan,native_routes,summarize
from research.causal_replay_slice import CausalReplaySlice
from research.execution_offset_study import bounded_departure,concentration
from research.japan_xanax.renewal_shadow import source_data,rate_plan,WAIT,STEP
from research.plushie_champions.common import TRAVEL_SECONDS

START=int(datetime(2026,10,18,9,tzinfo=timezone.utc).timestamp())
END=START+3*3600
PRIMARY=tuple(range(START,END+1,3600))
STARTS=tuple(range(START,END+1,900))
WEAK={'can:Xanax','jap:Xanax','uni:Nessie Plushie'}


def eligible(issued,dep,age,deadline):
    return (dep is not None and issued<=dep<issued+STEP and dep<=deadline
            and age is not None and 0<=age+dep-issued<=180)


class Cohorts:
    """Scheduling decisions depend on departure eligibility, never truth labels."""
    def __init__(self,modes,starts=STARTS):
        self.modes=modes;self.starts=set(starts);self.active=[];self.departed=[];self.abstained=[]

    def begin(self,issued):
        if issued in self.starts:
            self.active.extend(dict(issued=issued,mode=m) for m in self.modes)
        remain=[]
        for c in self.active:
            if issued>c['issued']+WAIT:self.abstained.append(dict(c,departure=None,status='EIGHT_HOUR_ABSTENTION'))
            else:remain.append(c)
        self.active=remain

    def advance(self,issued,choices,age):
        remain=[]
        for c in self.active:
            dep=choices.get(c['mode'])
            if eligible(issued,dep,age,c['issued']+WAIT):
                self.departed.append(dict(c,departure=dep,status='HISTORICAL_REPLANNED'))
            else:remain.append(c)
        self.active=remain

    def needs(self,modes):return any(c['mode'] in modes for c in self.active)

    def score(self,evidence,flight):
        if self.active:raise ValueError('Unresolved replay cohorts')
        records=[]
        for c in self.departed+self.abstained:
            outcome=evidence.score(c['departure']+flight)[0] if c['departure'] is not None else 'ABSTAIN'
            if outcome=='PENDING':raise ValueError('Immature holdout truth')
            records.append(dict(c,outcome=outcome))
        if len(records)!=len(self.starts)*len(self.modes):raise ValueError('Dropped cohorts')
        return sorted(records,key=lambda r:(r['mode'],r['issued']))


def banana_choices(db,issued):
    child="""import json,sys,types
p=types.ModuleType('services.yata_api')
def forbidden(*a,**k):raise RuntimeError('HTTP forbidden in release check')
p.get_country_stock=forbidden
sys.modules['services.yata_api']=p
from research.template_window_study import strong_choices
print(json.dumps(strong_choices(sys.argv[1],'cay:Banana Orchid',int(sys.argv[2]))))
"""
    try:
        p=subprocess.run([sys.executable,'-B','-c',child,str(db),str(issued)],
                         capture_output=True,text=True,timeout=20,check=True)
        r=json.loads(p.stdout.strip().splitlines()[-1])
        return {'native_specialist':r['native'],'banana_earliest85':r['earliest85']},'OK'
    except (subprocess.TimeoutExpired,subprocess.CalledProcessError,ValueError,KeyError,IndexError) as e:
        return {},'NATIVE_ERROR_'+type(e).__name__


def item_check(source,out,key,model_sha):
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    began=time.monotonic();rows,polls,crosses,evidence,cutoff=source_data(source,item_key=key)
    flight=TRAVEL_SECONDS[key.split(':',1)[0]]
    if cutoff<END+WAIT+flight+190:raise ValueError('Holdout not yet mature')
    supported=key in native_routes()
    native_modes=['native_specialist'] if supported else []
    if key=='cay:Banana Orchid':native_modes.append('banana_earliest85')
    modes=['rate_current_quarter','leave_now_control']+native_modes
    cohorts=Cohorts(modes);rate=QuantityRateCycles(crosses);cursor=0;calls=Counter()
    work=Path(out)/key.split(':',1)[0]/key.split(':',1)[1].replace(' ','_');work.mkdir(parents=True,exist_ok=True)
    with CausalReplaySlice(source,work/'causal.sqlite') as mirror:
        for issued in range(START,END+WAIT+STEP+1,STEP):
            cohorts.begin(issued)
            if not cohorts.active:continue
            while cursor<len(rows) and rows[cursor][0]<=issued:
                rate.add(OBS(*rows[cursor]));cursor+=1
            pi=bisect.bisect_right(polls,issued)-1;age=issued-polls[pi] if pi>=0 else None
            fresh=age is not None and 0<=age+15<=180 and not crosses(issued,issued)
            choices={}
            if fresh:
                if cohorts.needs(['rate_current_quarter']):
                    choices['rate_current_quarter']=bounded_departure(issued,rate_plan(rate,key,issued,age)['departure'])
                choices['leave_now_control']=issued+15
                if native_modes and cohorts.needs(native_modes):
                    db=work/'causal.sqlite'
                    mirror.advance(issued)
                    if key=='cay:Banana Orchid':raw,status=banana_choices(db,issued)
                    else:
                        r=native_plan(db,key,issued,timeout=20)
                        raw={'native_specialist':r['departure']};status=r['status']
                    calls[status]+=1
                    for mode,dep in raw.items():choices[mode]=bounded_departure(issued,dep)
            cohorts.advance(issued,choices,age)
    records=cohorts.score(evidence,flight)
    primary=[r for r in records if r['issued'] in PRIMARY]
    errors=sum(v for k,v in calls.items() if 'ERROR' in k or 'TIMEOUT' in k)
    report=dict(item_key=key,model_sha=model_sha,truth_cutoff=cutoff,
        primary=summarize(primary),primary_distinct=concentration(primary),
        quarter_hour_sensitivity=summarize(records),distinct=concentration(records),records=records,
        native_supported=supported,native_route=native_routes().get(key),native_status_counts=dict(calls),
        worker_errors=errors,release_approved=False,
        review_status=('MISSING_ORIGINAL_SPECIALIST_STATE' if not supported else
                       'WEAK_MODEL_CONTROL' if key in WEAK else
                       'NATIVE_COMPUTE_ERRORS' if errors else 'SMALL_SAMPLE_REQUIRES_CANARY'),
        seconds=time.monotonic()-began)
    (Path(out)/('item-'+key.replace(':','-').replace(' ','_')+'.json')).write_text(json.dumps(report,sort_keys=True))
    print('ITEM_COMPLETE',key,json.dumps(report['primary']),flush=True)
    return report


def run(source,out,*,model_sha,item_keys=None):
    from deploy.scripts.v163_readonly_event_first_preview import exact_roster
    roster=set(exact_roster())
    if len(roster)!=24:raise ValueError('Exact24 roster required')
    missing_with_control={'arg:Ceibo Flower','uae:Camel Plushie','uni:Nessie Plushie','uni:Red Fox Plushie','uni:Xanax'}
    if item_keys is not None and (len(item_keys)!=5 or set(item_keys)!=missing_with_control):
        raise ValueError('Follow-up must contain the exact four missing items and fixed parity control')
    keys=sorted(roster if item_keys is None else item_keys);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    # Two item workers only; both access isolated, immutable research evidence.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda k:item_check(source,out,k,model_sha),keys))
    return dict(model_sha=model_sha,item_count=len(results),primary_starts=PRIMARY,
        full_roster_run=item_keys is None,
        secondary_starts=STARTS,native_supported=sum(r['native_supported'] for r in results),
        items={r['item_key']:dict(primary=r['primary'],primary_distinct=r['primary_distinct'],
             review_status=r['review_status'],worker_errors=r['worker_errors']) for r in results},
        physical_depletion_quantity=0,arrival_target=30,grace_seconds=10,
        replan_seconds=STEP,source_expiry_seconds=180,maximum_wait_seconds=WAIT,
        automatic_promotion=False,actual_flights=False,release_approved=False,
        limitation='Four primary starts in a later period; quarter-hour sensitivity is correlated. Fixed existing models, no holdout model selection. Historical release check only; all24 canary and missing specialist state still required.')
