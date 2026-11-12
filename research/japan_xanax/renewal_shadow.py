"""Paired-cycle and block-continuation shadow challengers. Research only.

Completed physical-zero -> restock -> physical-zero tuples retain their
separate >=30 availability duration. No website assignments or game actions.
"""
import argparse
import bisect
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections import namedtuple
from contextlib import closing
from pathlib import Path

import numpy as np

KEY='jap:Xanax';FLIGHT=8940;GRACE=10;WAIT=28800;STEP=300
# Historical research extension only. V163's production 24-item roster and
# private export roster remain unchanged.
RESEARCH_ONLY_ADDITIONAL_ITEMS=frozenset({'sou:Xanax'})
ROOT=Path(__file__).resolve().parents[2]
FAMILIES=('paired_recent','sequence_blocks','quantity_blocks')
MODES=tuple(f+'_'+gate for f in FAMILIES for gate in ('peak','60'))+('leave_now_control','rate_current_quarter')
Cycle=namedtuple('Cycle','zero restock end available batch')


class History:
    def __init__(self,crosses):
        self.crosses=crosses;self.last=None;self.low=None;self.restock=None
        self.batch=None;self.buy_end=None;self.cycles=[];self.phase_start=None

    def add(self,row):
        t,q,source=row;prev=self.last
        broken=(prev is None or t<=prev[0] or source!=prev[2]
                or self.crosses(prev[0],t) or (q>prev[1]>0))
        if broken:
            self.low=self.restock=self.batch=self.buy_end=self.phase_start=None
        else:
            if prev[1]>=30>q and self.restock is not None and self.buy_end is None:self.buy_end=t
            if prev[1]>0 and q==0:
                if self.low is not None and self.restock is not None:
                    available=max(0,(self.buy_end or t)-self.restock) if self.batch>=30 else 0
                    self.cycles.append(Cycle(self.low,self.restock,t,available,self.batch))
                self.low=t;self.phase_start=t;self.restock=self.batch=self.buy_end=None
            elif prev[1]==0 and q>0:
                self.restock=t;self.phase_start=t;self.batch=q;self.buy_end=None
        self.last=row

    def plans(self,issued,*,poll_age,flight_seconds=FLIGHT,diagnostics=None,
              cycle_limit=96,half_life_seconds=3*86400,stable_scenarios=False):
        if type(cycle_limit) is not int or not 16<=cycle_limit<=96:
            raise ValueError('Bounded cycle memory required')
        if type(half_life_seconds) is not int or not 21600<=half_life_seconds<=3*86400:
            raise ValueError('Bounded recency half life required')
        if self.last is not None and self.last[0]>issued:raise ValueError('Future stock observation')
        empty={m:dict(departure=None,status='INSUFFICIENT_PAST_CYCLES') for m in MODES}
        if poll_age is None or not 0<=poll_age<=180 or self.crosses(issued,issued):return empty
        empty['leave_now_control']=dict(departure=issued,status='SHADOW_CONTROL')
        cycles=[c for c in self.cycles if c.end<=issued][-cycle_limit:]
        if len(cycles)<16 or self.phase_start is None or issued-self.last[0]>86400:return empty
        high=self.last[1]>0;age=issued-self.phase_start
        durations=np.array([(c.end-c.restock) if high else (c.restock-c.zero) for c in cycles])
        eligible=np.flatnonzero(durations>age)
        if len(eligible)<4:return empty
        delays=np.arange(0,WAIT+1,60);land=issued+delays+flight_seconds
        current_q=self.last[1]
        for family in FAMILIES:
            seed=int.from_bytes(hashlib.sha256(f'{family}:{issued}'.encode()).digest()[:8],'big')
            rng=np.random.default_rng(seed);support=np.zeros(len(delays))
            weights=np.exp2(-(issued-np.array([c.end for c in cycles]))/half_life_seconds)
            weights/=weights.sum();initial=weights[eligible];initial/=initial.sum()
            for scenario in range(64):
                if stable_scenarios:
                    # Common random numbers across successive issues in the
                    # same observed phase. Separate scenario streams prevent
                    # horizon-length changes from shifting every later draw.
                    stable_seed=int.from_bytes(hashlib.sha256(f'{family}:{self.phase_start}:{scenario}'.encode()).digest()[:8],'big')
                    rng=np.random.default_rng(stable_seed)
                index=int(rng.choice(eligible,p=initial));c=cycles[index]
                if high:
                    remaining=c.end-c.restock-age
                    if family=='quantity_blocks':
                        fraction=current_q/max(current_q,self.batch or current_q)
                        remaining=max(1,round(.5*remaining+.5*(c.end-c.restock)*fraction))
                        available=remaining*max(0,current_q-29)/max(1,current_q)
                    else:available=max(0,c.available-age) if current_q>=30 else 0
                    available=min(remaining,available)
                    support+=(land>=issued)&(land+GRACE<issued+available)
                    zero=issued+remaining
                else:
                    start=issued+(c.restock-c.zero-age)
                    support+=(land>=start)&(land+GRACE<start+c.available)
                    zero=start+c.end-c.restock
                for _ in range(1024):
                    if zero>int(land[-1])+GRACE:break
                    next_index=index+1
                    if family!='paired_recent' and next_index<len(cycles) and cycles[next_index].zero==c.end:
                        index=next_index
                    else:index=int(rng.choice(len(cycles),p=weights))
                    c=cycles[index];start=zero+c.restock-c.zero
                    support+=(land>=start)&(land+GRACE<start+c.available)
                    zero=start+c.end-c.restock
                if zero<=int(land[-1])+GRACE:raise ValueError('Simulation cycle cap exceeded')
            support/=64
            if diagnostics is not None:
                diagnostics[family]=dict(delays=delays.tolist(),support=support.tolist())
            # Fixed gates are uncalibrated scenario agreement, never a probability.
            peak=float(support.max())
            for gate in ('peak','60'):
                threshold=max(.15,peak-.03) if gate=='peak' else .6
                ids=np.flatnonzero(support>=threshold);j=int(ids[0]) if len(ids) else None
                empty[family+'_'+gate]=dict(departure=issued+int(delays[j]) if j is not None else None,
                    status='SHADOW_ESTIMATE' if j is not None else 'ABSTAIN_LOW_SCENARIO_SUPPORT',
                    uncalibrated_support=float(support[j]) if j is not None else None,
                    maximum_support=peak,completed_cycles=len(cycles),latest_training_cycle_end=max(c.end for c in cycles),
                    depletion_stock_quantity=0,arrival_target=30,calibrated_probability=None)
        return empty


def rate_plan(tracker,key,issued,age):
    from services.travel_window_policy import project_policy
    decision=project_policy(tracker.forecast(key,asof=issued),now=issued,poll_age_seconds=age,kind='current_quarter')
    return dict(departure=decision['estimated_departure_epoch'],status=decision['status'],
                calibrated_probability=None,depletion_stock_quantity=0,arrival_target=30)


def source_data(source,now=None,*,item_key=KEY):
    # Explicit checkout pin defeats the VM's older staged research default.
    os.environ['TORNFREN_REPLAY_WORK']=str(ROOT);os.environ['TORNFREN_REPLAY_PINNED_RESEARCH']=str(ROOT/'research')
    from research.continuous_departure_replay import ArrivalEvidence,model,MAX_POLLS
    if item_key not in (set(model.exact_roster()) | RESEARCH_ONLY_ADDITIONAL_ITEMS):
        raise ValueError('Unverified item key')
    country,name=item_key.split(':',1)
    clock=int(time.time()) if now is None else now
    with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=12)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        heartbeat=model.read_heartbeat(db)
        if heartbeat is None:raise ValueError('Missing successful heartbeat')
        cutoff=min(clock,heartbeat)
        rows=db.execute("SELECT timestamp,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT ?",(country,name,cutoff,model.MAX_ITEM_CHANGE_ROWS+1)).fetchall()
        polls=[r[0] for r in db.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=? ORDER BY timestamp LIMIT ?",(cutoff,MAX_POLLS+1))]
        gaps=db.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? ORDER BY start_timestamp LIMIT ?',(cutoff,model.MAX_GAPS+1)).fetchall()
        if len(rows)>model.MAX_ITEM_CHANGE_ROWS or len(polls)>MAX_POLLS or len(gaps)>model.MAX_GAPS:raise ValueError('Source evidence cap exceeded')
        if any(type(t) is not int or type(q) is not int or q<0 or not s for t,q,s in rows):raise ValueError('Invalid stock observations')
    crosses=model._gap_index(gaps,cutoff)
    evidence=ArrivalEvidence([model.OBS(*r) for r in rows],polls,gaps,cutoff)
    return rows,polls,crosses,evidence,cutoff


def benchmark(source,*,days=3,model_sha,item_key=KEY):
    if days not in (1,3,7):raise ValueError('Bounded benchmark duration required')
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,item_key=item_key)
    from research.plushie_champions.common import TRAVEL_SECONDS
    flight=TRAVEL_SECONDS[item_key.split(':',1)[0]]
    end=((cutoff-flight-WAIT-190-300)//STEP)*STEP
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    start=end-days*86400+STEP;history=History(crosses);rate=QuantityRateCycles(crosses);cursor=0
    plans={m:[] for m in MODES}
    for issued in range(start,end+WAIT+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            history.add(rows[cursor]);rate.add(OBS(*rows[cursor]));cursor+=1
        i=bisect.bisect_right(polls,issued)-1;age=issued-polls[i] if i>=0 else None
        selected=history.plans(issued,poll_age=age,flight_seconds=flight)
        selected['rate_current_quarter']=rate_plan(rate,item_key,issued,age)
        for mode,p in selected.items():
            # Fixed publication floor; never assume immediate plans were available instantly.
            dep=max(p['departure'],issued+15) if p['departure'] is not None else None
            plans[mode].append((issued,dep,age))
    cohorts={};results={}
    for mode,values in plans.items():
        c=[];results[mode]=evaluate_all_starts(values,cutoff=cutoff,flight_seconds=flight,
            score=evidence.score,start_before=end,cohorts=c);cohorts[mode]=c
    return dict(item_key=item_key,model_sha=model_sha,truth_cutoff=cutoff,issue_start=start,issue_end=end,
        days=days,flight_seconds=flight,arrival_target=30,depletion_stock_quantity=0,grace_seconds=10,
        publication_floor_seconds=15,policies=results,
        paired_vs_leave_now={m:compare_cohorts(cohorts['leave_now_control'],v) for m,v in cohorts.items() if m!='leave_now_control'},
        genuine_live_issuance=False,automatic_promotion=False,
        warning='Exploratory fixed-family historical benchmark; correlated starts, uncalibrated support, no website recommendations.')


def record(source,journal,*,model_sha,duration=28800,item_keys=None):
    if not 60<=duration<=86400:raise ValueError('Invalid bounded recording duration')
    source=Path(source).resolve(strict=True);journal=Path(journal).resolve()
    if source==journal or journal.suffix!='.sqlite' or journal.is_symlink():raise ValueError('Separate shadow journal required')
    if journal.exists():raise ValueError('Use a new full-roster shadow journal; never overwrite earlier trials')
    # Load only numeric/read-only helpers, not the application's history service.
    source_data(source)
    from deploy.scripts.v163_readonly_event_first_preview import exact_roster
    from research.plushie_champions.common import TRAVEL_SECONDS
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    keys=sorted(exact_roster() if item_keys is None else item_keys)
    if not keys or len(set(keys))!=len(keys) or not set(keys)<=set(exact_roster()):raise ValueError('Invalid shadow roster')
    os.umask(0o077)
    with closing(sqlite3.connect(journal)) as db:
        db.executescript('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE plans(issued INTEGER,item_key TEXT,mode TEXT,record TEXT,PRIMARY KEY(issued,item_key,mode));')
        db.execute('INSERT INTO metadata VALUES(?,?)',('model_sha',model_sha));db.commit()
        until=time.monotonic()+duration
        while time.monotonic()<until:
            began=time.monotonic();issued=int(time.time())
            try:
                prepared=[]
                for key in keys:
                    rows,polls,crosses,_,cutoff=source_data(source,now=issued,item_key=key)
                    if not 0<=issued-cutoff<=180:raise ValueError('Stale shadow source')
                    history=History(crosses);rate=QuantityRateCycles(crosses)
                    for row in rows:history.add(row);rate.add(OBS(*row))
                    flight=TRAVEL_SECONDS[key.split(':',1)[0]]
                    selected=history.plans(issued,poll_age=issued-cutoff,flight_seconds=flight)
                    selected['rate_current_quarter']=rate_plan(rate,key,issued,issued-cutoff)
                    prepared.append((key,flight,selected,cutoff))
                published=int(time.time())
                if published-issued>30:raise ValueError('Shadow publication exceeded30s budget')
                if any(not 0<=published-cutoff<=180 for _,_,_,cutoff in prepared):
                    raise ValueError('Shadow source expired before publication')
                with db:
                    for key,flight,selected,cutoff in prepared:
                        for mode,plan in selected.items():
                            dep=plan['departure'];actual=max(dep,published) if dep is not None else None
                            # Apply the same fixed wait horizon to every family,
                            # including rate forecasts with distant event windows.
                            bounded_plan=dict(plan)
                            if actual is not None and actual>issued+WAIT:
                                actual=None
                                bounded_plan['status']='ABSTAIN_OUTSIDE_EIGHT_HOUR_HORIZON'
                            r=dict(bounded_plan,mode=mode,departure=actual,published=published,model_sha=model_sha,item_key=key,
                                issued=issued,source_cutoff=cutoff,poll_age_seconds=issued-cutoff,
                                arrival=actual+flight if actual is not None else None,
                                flight_seconds=flight,target_quantity=30,grace_seconds=10,
                                execution='FROZEN_SHADOW_PLAN_FUTURE_RECONFIRMATION_UNTESTED',
                                actual_gameplay=False,website_publication=False)
                            db.execute('INSERT INTO plans VALUES(?,?,?,?)',(issued,key,mode,json.dumps(r,sort_keys=True)))
                print(json.dumps({'status':'FULL_ROSTER_SHADOW_RECORDED','issued':issued,'items':len(keys),'models_per_item':len(MODES),'japan_xanax_included':KEY in keys,'publication_seconds':published-issued}),flush=True)
            except (OSError,ValueError,sqlite3.Error) as e:
                print(json.dumps({'status':'FULL_ROSTER_SHADOW_UNAVAILABLE','issued':issued,'error':str(e)[:150]}),flush=True)
            elapsed=time.monotonic()-began
            time.sleep(min(max(0,until-began-elapsed),max(1,STEP-elapsed)))


def score_journal(source,journal,*,expected_sha=None,progress=None):
    source=Path(source).resolve(strict=True);journal=Path(journal).resolve(strict=True)
    if source==journal:raise ValueError('Separate shadow journal required')
    with closing(sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True)) as db:
        metadata=db.execute("SELECT value FROM metadata WHERE key='model_sha'").fetchone()
        if metadata is None:raise ValueError('Missing shadow model identity')
        sha=metadata[0]
        if expected_sha is not None and sha!=expected_sha:raise ValueError('Journal differs from declared model source')
        raw=db.execute('SELECT issued,item_key,mode,record FROM plans ORDER BY issued,item_key,mode LIMIT 100001').fetchall()
    if len(raw)>100000:raise ValueError('Shadow journal cap exceeded')
    from collections import Counter,defaultdict
    records=[];missing_clocks=0
    for issued,key,mode,encoded in raw:
        r=json.loads(encoded)
        if (r.get('issued'),r.get('item_key'),r.get('mode'),r.get('model_sha'))!=(issued,key,mode,sha):
            raise ValueError('Shadow record identity mismatch')
        clock=r.get('source_cutoff');age=r.get('poll_age_seconds')
        if clock is None and age is None:missing_clocks+=1
        elif (type(clock) is not int or type(age) is not int or type(r.get('published')) is not int
              or age!=issued-clock or not 0<=age<=180 or not issued<=r['published']
              or not 0<=r['published']-clock<=180):
            raise ValueError('Invalid recorded source clock')
        records.append(r)
    first={}
    for r in records:first.setdefault((r['item_key'],r['mode'],r['issued']//3600),r)
    # Mode is deliberately stored in the DB identity as well as the record.
    groups=defaultdict(Counter);evidence={}
    for r in first.values():
        key=r['item_key']
        if key not in evidence:
            began=time.monotonic()
            # Freeze the truth clock across the roster instead of evaluating
            # later items against later collector heartbeats.
            data=source_data(source,now=truth_cutoff if evidence else None,item_key=key)
            if not evidence:truth_cutoff=data[4]
            if data[4]!=truth_cutoff:raise ValueError('Source heartbeat moved backwards during scoring')
            evidence[key]=data[3]
            if progress is not None:progress(dict(status='SCORING_ITEM',item_key=key,
                evidence_load_seconds=time.monotonic()-began,truth_cutoff=truth_cutoff))
        c=groups[(key,r['mode'])];c['issues']+=1
        outcome='ABSTAIN' if r['arrival'] is None else evidence[key].score(r['arrival'])[0]
        c[outcome]+=1
    return dict(model_sha=sha,records=len(records),truth_cutoff=truth_cutoff if evidence else None,
        records_missing_source_clock=missing_clocks,
        source_clock_limitation='Older records without source clocks cannot establish source freshness at departure; frozen arrival scoring only.',
        metric='First observed item/model/UTC-hour frozen shadow plan; future reconfirmation untested',
        actual_flights=False,website_publication=False,items={key:{mode:dict(c,known=c['SUCCESS']+c['FAILURE'],success_fraction=c['SUCCESS']/(c['SUCCESS']+c['FAILURE']) if c['SUCCESS']+c['FAILURE'] else None) for (k,mode),c in groups.items() if k==key} for key in sorted({k for k,_ in groups})})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('benchmark','record','score'))
    p.add_argument('--source',required=True);p.add_argument('--model-sha',required=True)
    p.add_argument('--days',type=int,default=3);p.add_argument('--journal');p.add_argument('--duration-seconds',type=int,default=28800)
    p.add_argument('--item-key',default=KEY)
    p.add_argument('--progress',action='store_true',help='Score progress on stderr; JSON result stays on stdout')
    a=p.parse_args()
    sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    # Read-only scoring may inspect an older producer's journal. Keep its
    # recorded model identity distinct from this checkout's scorer identity.
    if a.action!='score' and sha!=a.model_sha:raise ValueError('Pinned checkout differs from declared model source')
    if a.action=='benchmark':print(json.dumps(benchmark(a.source,days=a.days,model_sha=sha,item_key=a.item_key),sort_keys=True))
    else:
        if not a.journal:p.error('--journal required')
        if a.action=='record':record(a.source,a.journal,model_sha=sha,duration=a.duration_seconds)
        else:
            result=score_journal(a.source,a.journal,expected_sha=a.model_sha,
                progress=(lambda r:print(json.dumps(r,sort_keys=True),file=sys.stderr,flush=True)) if a.progress else None)
            result['scorer_sha']=sha
            print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':main()
