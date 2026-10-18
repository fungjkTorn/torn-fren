"""Causal multi-day Nessie patterns and earlier native score windows.

Original model controls remain intact. No posthoc best-item routing, website
publication, zero-event relabeling, or future reference data is permitted.
"""
import bisect
import importlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from research.japan_xanax.renewal_shadow import source_data,STEP,WAIT
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END
from research.matched_champion_audit import ISSUES,causal_copy,summarize
from research.execution_offset_study import fixed_records,concentration,bounded_departure
from research.plushie_champions.common import Timeline,TemplatePlanner,TRAVEL_SECONDS,DAY
from research.v46_fast_template import FastTemplatePlanner

STRONG=('uni:Red Fox Plushie','uae:Camel Plushie','uni:Xanax','uni:Heather',
        'haw:Orchid','can:Wolverine Plushie','cay:Banana Orchid')


class PrefixRows:
    def __init__(self,rows,issued):
        self.rows=[r for r in rows if r[0]<=issued]
    def execute(self,query,args):
        if 'from stock_history' not in query.lower():raise ValueError('Unexpected template query')
        return self
    def fetchall(self):return self.rows


class GuardedTimeline(Timeline):
    def __init__(self,rows,gaps,key,issued):
        self.issued=issued
        known=[(a,b if b is not None and b<=issued else 9999999999) for a,b in gaps if a<=issued]
        gs=np.array([a for a,b in known],float);ge=np.array([b for a,b in known],float)
        country,item=key.split(':',1)
        super().__init__(PrefixRows(rows,issued),gs,ge,country,item)
    def vals(self,t):
        if np.any(np.asarray(t)>self.issued):raise ValueError('Future template observation requested')
        return super().vals(t)


def curve(planner,issued):
    refs=[];delays=np.arange(0,WAIT+1,STEP)
    numerator=np.zeros(len(delays));denominator=np.zeros(len(delays))
    for lag in planner.lags:
        fit,shift,raw=planner._best_ref(issued,lag)
        if fit<planner.minfit:continue
        refs.append((lag,shift,fit,raw))
        values=planner._states(issued+planner.travel+delays-lag*DAY-shift)
        valid=np.isfinite(values);weight=fit*fit/lag
        numerator[valid]+=weight*values[valid];denominator[valid]+=weight
    mask=denominator>0
    return dict(delays=delays[mask],scores=numerator[mask]/denominator[mask],refs=refs)


def plateau_choice(values,issued,position='center'):
    if not len(values['delays']):return issued # exact original no-ref fallback
    scores=values['scores'];delays=values['delays'];best=float(scores.max())
    ids=np.flatnonzero(scores>=best-.04)
    groups=np.split(ids,np.where(np.diff(delays[ids])>STEP)[0]+1)
    group=max(groups,key=lambda g:(sum(float(scores[i]) for i in g)/len(g),len(g),-int(delays[g[0]])))
    k=len(group)//2 if position=='center' else len(group)//4 if position=='quarter' else 0
    return issued+int(delays[group[k]])


def nessie_choices(timeline,issued):
    key=('uni','Nessie Plushie');ctx=SimpleNamespace(timelines={key:timeline})
    result={};diagnostics={}
    for label,lags in (('day1',(1,)),('day12',(1,2)),('day127',(1,2,7))):
        p=FastTemplatePlanner(ctx,*key,lags=lags,lookback=7200,shift_range=3600,minfit=.5)
        values=curve(p,issued);diagnostics[label]=dict(references=len(values['refs']),
            maximum_score=float(values['scores'].max()) if len(values['scores']) else None)
        result[label+'_center']=plateau_choice(values,issued)
        result[label+'_quarter']=plateau_choice(values,issued,'quarter')
        if label=='day1':result['day1_left']=plateau_choice(values,issued,'left')
        if label=='day127':
            state=timeline.vals(np.arange(issued-7200,issued+1,STEP))[0]
            identified=np.count_nonzero(state==1)>=2 and np.count_nonzero(state==0)>=2
            supported=len(values['refs'])>=2 and len(values['scores']) and values['scores'].max()>=.65
            result['day127_identified_quarter']=result[label+'_quarter'] if identified and supported else None
    return result,diagnostics


def source_gaps(source):
    with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('PRAGMA query_only=ON')
        return c.execute('SELECT start_timestamp,end_timestamp FROM collection_gaps ORDER BY start_timestamp').fetchall()


def nessie_study(source,*,model_sha):
    from research.departure_reconfirmation import evaluate_all_starts
    key='uni:Nessie Plushie';rows,polls,crosses,evidence,cutoff=source_data(source,item_key=key)
    gaps=source_gaps(source);flight=TRAVEL_SECONDS['uni'];plans={};checks=[]
    for issued in range(ISSUE_START,ISSUES[-1]+WAIT+STEP,STEP):
        timeline=GuardedTimeline(rows,gaps,key,issued)
        selected,info=nessie_choices(timeline,issued)
        pi=bisect.bisect_right(polls,issued)-1;age=issued-polls[pi] if pi>=0 else None
        fresh=age is not None and 0<=age+15<=180 and not crosses(issued,issued)
        for mode,dep in selected.items():
            plans.setdefault(mode,[]).append((issued,bounded_departure(issued,dep) if fresh else None,age))
        if issued in ISSUES:
            native=TemplatePlanner(SimpleNamespace(timelines={('uni','Nessie Plushie'):timeline}),
                'uni','Nessie Plushie',lags=(1,),lookback=7200,shift_range=3600,minfit=.5).plan(issued)
            if int(native[0])!=selected['day1_center']:raise ValueError('Original Nessie parity failure')
            checks.append(dict(issued=issued,diagnostics=info,original_departure=int(native[0])))
    earlier={}
    for mode,values in plans.items():
        earlier[mode]=evaluate_all_starts(values,cutoff=cutoff,flight_seconds=flight,
            score=evidence.score,start_before=ISSUE_END)
    records=fixed_records(plans,ISSUES,cutoff,flight,evidence.score)
    frozen=[]
    for mode,values in plans.items():
        lookup={r[0]:r for r in values}
        for issued in ISSUES:
            dep=lookup[issued][1];outcome=evidence.score(dep+flight)[0] if dep is not None else 'ABSTAIN'
            frozen.append(dict(issued=issued,mode=mode,departure=dep,outcome=outcome,status='FROZEN'))
    return dict(model_sha=model_sha,item_key=key,truth_cutoff=cutoff,
        earlier_three_day=earlier,failed_nine_replanned=summarize(records),
        failed_nine_distinct=concentration(records),failed_nine_records=records,
        failed_nine_frozen=summarize(frozen),frozen_records=frozen,original_parity_checks=checks,
        future_observation_guard=True,automatic_promotion=False,raw_scores_calibrated=False)


def strong_choices(db,key,issued):
    """Called in an isolated child, on an issue-truncated database only."""
    country,item=key.split(':',1)
    if key=='uni:Red Fox Plushie':
        from research.plushie_champions.common import ResearchContext,AnalogPlanner
        from research.v103_champion_score_curves import analog_scores,analog_champion_from_curve
        ctx=ResearchContext.build(db,asof=issued,readonly=True)
        try:
            p=AnalogPlanner(ctx,country,item,k=18,global_weight=.5,cutoff=issued)
            values=analog_scores(p,issued);native=p.plan(issued)
            reconstructed=analog_champion_from_curve(issued,values)
            if (native is None)!=(reconstructed is None):raise ValueError('Red Fox parity')
            if native is None:return dict(native=None,quarter=None,left=None)
            if int(native[0])!=reconstructed[0]:raise ValueError('Red Fox parity')
            prob=values['availability_score'];rob=values['robust_score'];delays=values['delay_seconds']
            near=np.flatnonzero((rob>=rob.max()-.025)&(prob>=prob.max()-.04))
            if not len(near):g=np.array([int(np.argmax(rob))])
            else:
                groups=np.split(near,np.where(np.diff(near)>1)[0]+1)
                g=max(groups,key=lambda v:(float(rob[v].mean()),float(prob[v].mean()),len(v),-int(v[0])))
            return dict(native=int(native[0]),quarter=issued+int(delays[g[len(g)//4]]),left=issued+int(delays[g[0]]))
        finally:ctx.con.close()
    if key=='uae:Camel Plushie':
        from research.plushie_champions.common import connect,load_gaps
        from research.v38_camel_single_tick import EXPERTS
        c=connect(db,readonly=True)
        try:
            gs,ge=load_gaps(c);tl=Timeline(c,gs,ge,country,item)
            ctx=SimpleNamespace(timelines={(country,item):tl});bank=[]
            for lags,look,shift in EXPERTS:
                p=FastTemplatePlanner(ctx,country,item,lags=lags,lookback=look,shift_range=shift)
                choice=p.plan(issued);bank.append((choice[1],choice[2]['maxfit'],-choice[0],p,choice))
            winner=max(bank,key=lambda b:b[:3]);p,choice=winner[-2:];values=curve(p,issued)
            if plateau_choice(values,issued)!=int(choice[0]):raise ValueError('Camel curve parity')
            return dict(native=int(choice[0]),quarter=plateau_choice(values,issued,'quarter'),left=plateau_choice(values,issued,'left'))
        finally:c.close()
    from research.matched_champion_audit import native_routes
    from services import plushie_flower_dynamic_planner_v18 as engine
    captured=[];original=engine._score_delay_from_ranked
    def capture(*args,**kwargs):
        value=original(*args,**kwargs)
        if value is not None:captured.append(value)
        return value
    engine._score_delay_from_ranked=capture
    try:result=importlib.import_module(native_routes()[key]).predict(db,country,item,issued)
    finally:engine._score_delay_from_ranked=original
    return dict(native=result.get('recommended_departure_timestamp'),
        earliest70=next((issued+int(v['delay']) for v in captured if v['prob']>=.70),None),
        earliest85=next((issued+int(v['delay']) for v in captured if v['prob']>=.85),None))


def strong_study(source,out,*,model_sha):
    out=Path(out);data={key:source_data(source,item_key=key) for key in STRONG};results={k:[] for k in STRONG}
    child="""import json,sys,types
provider=types.ModuleType('services.yata_api')
def forbidden(*a,**k):raise RuntimeError('HTTP forbidden in native historical study')
provider.get_country_stock=forbidden
sys.modules['services.yata_api']=provider
from research.template_window_study import strong_choices
print(json.dumps(strong_choices(sys.argv[1],sys.argv[2],int(sys.argv[3]))))
"""
    for i,issued in enumerate(ISSUES):
        db=out/('strong-causal-%02d.sqlite'%i)
        try:
            causal_copy(source,db,issued)
            for key in STRONG:
                p=subprocess.run([sys.executable,'-B','-c',child,str(db),key,str(issued)],
                    capture_output=True,text=True,timeout=20,check=True)
                choices=json.loads(p.stdout.strip().splitlines()[-1]);flight=TRAVEL_SECONDS[key.split(':',1)[0]]
                for mode,value in choices.items():
                    dep=bounded_departure(issued,value);outcome=data[key][3].score(dep+flight)[0] if dep is not None else 'ABSTAIN'
                    results[key].append(dict(issued=issued,mode=mode,departure=dep,outcome=outcome,status='FROZEN_NATIVE_WINDOW'))
        finally:
            if db.exists():db.chmod(0o600);db.unlink()
    return dict(model_sha=model_sha,items={k:dict(policies=summarize(v),distinct=concentration(v),records=v) for k,v in results.items()},
        automatic_promotion=False,future_reconfirmation_tested=False,
        limitation='Nine frozen diagnostic starts; native score-window variants, not calibrated probabilities or a release qualification.')
