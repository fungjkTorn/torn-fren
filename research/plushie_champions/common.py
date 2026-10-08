from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

STEP = 300
DAY = 86400
MAX_WAIT = 8 * 3600
MIN_QTY = 30
GRACE = 10
TRAVEL_SECONDS = {
    'mex': 1020, 'cay': 1380, 'can': 1620, 'haw': 5340,
    'uni': 6360, 'arg': 6660, 'swi': 6960, 'jap': 8940,
    'chi': 9600, 'uae': 10800, 'sou': 11820,
}
PLUSHIES = [
    ('mex','Jaguar Plushie'),('cay','Stingray Plushie'),('can','Wolverine Plushie'),
    ('uni','Nessie Plushie'),('uni','Red Fox Plushie'),('arg','Monkey Plushie'),
    ('swi','Chamois Plushie'),('chi','Panda Plushie'),('uae','Camel Plushie'),
    ('sou','Lion Plushie'),
]

def connect(db: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(Path(db)))

def load_gaps(con):
    rows=con.execute("select start_timestamp, coalesce(end_timestamp,9999999999) from collection_gaps order by start_timestamp").fetchall()
    if not rows:return np.array([],float),np.array([],float)
    a=np.array(rows,float);return a[:,0],a[:,1]

def gap_overlap(gs,ge,a,b):
    if len(gs)==0:return False
    lo,hi=sorted((float(a),float(b)));j=int(np.searchsorted(gs,hi,'right')-1)
    return bool(j>=0 and ge[j]>=lo)

def clean_rows(con,country,item,bounce_seconds=180):
    rows=con.execute("select timestamp,quantity,source from stock_history where country=? and lower(item_name)=lower(?) order by timestamp",(country,item)).fetchall();bad=set()
    for k in range(1,len(rows)-1):
        a,b,c=rows[k-1],rows[k],rows[k+1]
        if b[0]-a[0]<=bounce_seconds and c[0]-b[0]<=bounce_seconds and (b[2]!=a[2] or b[2]!=c[2]):
            if (b[1]==0 and a[1]>0 and c[1]>0) or (b[1]>0 and a[1]==0 and c[1]==0):bad.add(k)
    return [x for k,x in enumerate(rows) if k not in bad]

class Timeline:
    def __init__(self,con,gs,ge,country,item):
        self.country,self.item=country,item;self.gs,self.ge=gs,ge
        rows=clean_rows(con,country,item)
        if not rows:raise ValueError(f'no rows for {country}:{item}')
        self.rows=rows;self.ts=np.array([r[0] for r in rows],float);self.q=np.array([r[1] for r in rows],float)
        self.windows=[];trans=[];active=None;start=None;prev=None
        for ts,q,_ in rows:
            if prev is not None and gap_overlap(gs,ge,prev,ts):active,start=None,None
            z=q>=MIN_QTY
            if active is None or z!=active:
                trans.append((float(ts),bool(z)))
                if z:start=float(ts)
                elif active is True and start is not None and ts>start and not gap_overlap(gs,ge,start,ts):
                    self.windows.append((start,float(ts),float(ts-start)))
            active=z;prev=ts
        self.wst=np.array([x[0] for x in self.windows],float)
        self.trans_t=np.array([x[0] for x in trans],float)
        self.trans_a=np.array([x[1] for x in trans],bool)
    def vals(self,t):
        t=np.asarray(t,float);idx=np.searchsorted(self.ts,t,'right')-1
        act=np.full(t.shape,np.nan);qty=np.full(t.shape,np.nan);age=np.full(t.shape,np.nan);ok=idx>=0
        if np.any(ok):
            ii=idx[ok];obs,tt=self.ts[ii],t[ok];inv=np.zeros(len(tt),bool)
            for n,(a,b) in enumerate(zip(obs,tt)):inv[n]=gap_overlap(self.gs,self.ge,a,b)
            q=self.q[ii].copy();a=(q>=MIN_QTY).astype(float);q[inv]=np.nan;a[inv]=np.nan;act[ok]=a;qty[ok]=q
            ti=np.searchsorted(self.trans_t,tt,'right')-1;ag=tt-self.trans_t[np.maximum(ti,0)];ag[(ti<0)|inv]=np.nan;age[ok]=ag
        return act,qty,age
    def success_many(self,t,grace=GRACE):
        t=np.asarray(t,float);out=np.zeros(t.shape,float)
        if len(self.wst)==0:return out
        idx=np.searchsorted(self.wst,t+grace,'right')-1;good=idx>=0
        if np.any(good):
            ii=idx[good];tt=t[good];ends=np.array([self.windows[j][1] for j in ii]);starts=self.wst[ii]
            out[good]=((starts-grace<=tt)&(tt<ends)).astype(float)
        return out
    def success(self,t,grace=GRACE):return bool(self.success_many(np.array([t]),grace)[0])

@dataclass
class ResearchContext:
    con: sqlite3.Connection
    gs: np.ndarray
    ge: np.ndarray
    timelines: Dict[Tuple[str,str],Timeline]
    grid: np.ndarray
    active: np.ndarray
    qty: np.ndarray
    age: np.ndarray
    g2: np.ndarray
    g6: np.ndarray
    g18: np.ndarray
    active_frac: np.ndarray
    @classmethod
    def build(cls,db,targets=PLUSHIES):
        con=connect(db);gs,ge=load_gaps(con);tls={k:Timeline(con,gs,ge,*k) for k in targets}
        g0=math.ceil(max(x.ts[0] for x in tls.values())/STEP)*STEP;g1=math.floor(min(x.ts[-1] for x in tls.values())/STEP)*STEP
        grid=np.arange(g0,g1+STEP,STEP,float);A=[];Q=[];AGE=[]
        for k in targets:
            a,q,ag=tls[k].vals(grid);A.append(a);Q.append(q);AGE.append(ag)
        A,Q,AGE=np.vstack(A),np.vstack(Q),np.vstack(AGE)
        events=[]
        for x in tls.values():
            for s,e,d in x.windows:events.append((e,d))
        events.sort();et=np.array([x[0] for x in events],float);ed=np.array([x[1] for x in events],float)
        def rolling(hours):
            out=np.full(len(grid),np.nan);w=hours*3600
            for j,t in enumerate(grid):
                lo=np.searchsorted(et,t-w,'left');hi=np.searchsorted(et,t,'left')
                if hi-lo>=5:out[j]=np.median(ed[lo:hi])
            return out
        with np.errstate(all='ignore'):af=np.nanmean(A,axis=0)
        return cls(con,gs,ge,tls,grid,A,Q,AGE,rolling(2),rolling(6),rolling(18),af)
    def idx(self,country,item):return list(self.timelines.keys()).index((country,item))

def valid_starts(ctx,country,item,warmup_days=8,stride=1800):
    tl=ctx.timelines[(country,item)];travel=TRAVEL_SECONDS[country];maxfuture=MAX_WAIT+travel+GRACE
    x=math.ceil((tl.ts[0]+warmup_days*DAY)/stride)*stride;last=tl.ts[-1]-maxfuture;starts=[]
    while x<=last:
        a,_,_=tl.vals(np.array([x]))
        if not np.isnan(a[0]) and not gap_overlap(ctx.gs,ctx.ge,x,x+maxfuture):starts.append(float(x))
        x+=stride
    return starts

def recent_target_series(ctx,country,item):
    tl=ctx.timelines[(country,item)];n=len(ctx.grid);te=np.array([x[1] for x in tl.windows],float);td=np.array([x[2] for x in tl.windows],float)
    tw=np.array([tl.windows[j+1][0]-tl.windows[j][1] for j in range(len(tl.windows)-1)],float);twe=te[:-1]
    def recent3(ev,val):
        out=np.full(n,np.nan)
        for j,t in enumerate(ctx.grid):
            hi=np.searchsorted(ev,t,'left');lo=max(0,hi-3)
            if hi-lo:out[j]=np.median(val[lo:hi])
        return out
    return recent3(te,td),recent3(twe,tw)

class AnalogPlanner:
    def __init__(self,ctx,country,item,k,global_weight,cutoff=None):
        self.ctx,self.country,self.item=ctx,country,item;self.tl=ctx.timelines[(country,item)];self.travel=TRAVEL_SECONDS[country]
        self.k,self.gw=int(k),float(global_weight);self.target_i=ctx.idx(country,item);self.maxfuture=MAX_WAIT+self.travel+GRACE;self.rL,self.rW=recent_target_series(ctx,country,item)
        hour=(ctx.grid%DAY)/DAY*2*np.pi
        def fill(arr):
            med=np.nanmedian(arr);return np.nan_to_num(arr,nan=(0.0 if not np.isfinite(med) else med))
        F=np.column_stack([ctx.active[self.target_i],np.log1p(fill(ctx.age[self.target_i])/300),np.log1p(fill(ctx.qty[self.target_i])/100),np.log1p(fill(ctx.g2)/600),np.log1p(fill(ctx.g6)/600),np.log1p(fill(ctx.g18)/600),ctx.active_frac,np.log1p(fill(self.rL)/600),np.log1p(fill(self.rW)/600),np.sin(hour),np.cos(hour)])
        if cutoff is None:cutoff=ctx.grid[-1]+STEP
        ids=np.where(ctx.grid<cutoff)[0];mu=np.nanmedian(F[ids],axis=0);sd=np.nanstd(F[ids],axis=0);sd[sd<1e-6]=1
        self.Z=(F-mu)/sd;self.weights=np.ones(self.Z.shape[1]);self.weights[3:7]=self.gw
        self.path_ok=np.array([not gap_overlap(ctx.gs,ctx.ge,t,t+self.maxfuture) for t in ctx.grid]);self.cache={};self.delays=np.arange(0,MAX_WAIT+1,STEP,float)
    def plan(self,q):
        key=int(q)
        if key in self.cache:return self.cache[key]
        qi=int(round((q-self.ctx.grid[0])/STEP))
        if qi<0 or qi>=len(self.ctx.grid):return None
        hi=np.searchsorted(self.ctx.grid,q-self.maxfuture,'right');ids=np.arange(0,hi,6);ids=ids[self.path_ok[ids]&~np.isnan(self.ctx.active[self.target_i,ids])]
        if len(ids)<self.k:self.cache[key]=None;return None
        same=self.ctx.active[self.target_i,ids]==self.ctx.active[self.target_i,qi]
        if same.sum()>=self.k:ids=ids[same]
        diff=(self.Z[ids]-self.Z[qi])*self.weights;dist=np.sqrt(np.nanmean(diff*diff,axis=1));kk=min(self.k,len(dist));pick=np.argpartition(dist,kk-1)[:kk];nid,dd=ids[pick],dist[pick]
        ww=np.exp(-dd);ww/=ww.sum() or 1
        base=self.ctx.grid[nid][:,None]+self.delays[None,:]+self.travel
        probs=(self.tl.success_many(base.ravel()).reshape(len(nid),len(self.delays))*ww[:,None]).sum(axis=0)
        robust=probs.copy()
        for j in range(len(self.delays)):
            loc=probs[max(0,j-2):min(len(self.delays),j+3)];robust[j]=.55*probs[j]+.3*loc.mean()+.15*loc.min()
        near=np.where((robust>=robust.max()-.025)&(probs>=probs.max()-.04))[0]
        if len(near):
            cls=np.split(near,np.where(np.diff(near)>1)[0]+1);cl=max(cls,key=lambda z:(robust[z].mean(),probs[z].mean(),len(z),-z[0]));j=int(cl[len(cl)//2])
        else:j=int(np.argmax(robust))
        self.cache[key]=(q+self.delays[j],float(probs[j]),float(robust[j]));return self.cache[key]

class TemplatePlanner:
    def __init__(self,ctx,country,item,lags=(1,),lookback=7200,shift_range=3600,minfit=.48):
        self.ctx,self.country,self.item=ctx,country,item;self.tl=ctx.timelines[(country,item)];self.travel=TRAVEL_SECONDS[country];self.lags=tuple(lags);self.lookback=int(lookback);self.shift_range=int(shift_range);self.minfit=float(minfit);self.cache={}
    def _state(self,t):
        a,_,_=self.tl.vals(np.array([t]));return None if np.isnan(a[0]) else bool(a[0])
    def _best_ref(self,q,lag_days):
        points=np.arange(q-self.lookback,q+1,STEP);cur=[self._state(x) for x in points];best=(-1.0,0,-1.0)
        for sh in range(-self.shift_range,self.shift_range+1,STEP):
            ref=[self._state(x-lag_days*DAY-sh) for x in points];pairs=[(a,b) for a,b in zip(cur,ref) if a is not None and b is not None]
            if len(pairs)<6:continue
            vv=[]
            for v in (False,True):
                z=[a==b for a,b in pairs if a==v]
                if z:vv.append(sum(z)/len(z))
            bal=sum(vv)/len(vv) if vv else -1;raw=sum(a==b for a,b in pairs)/len(pairs)
            if bal>best[0] or (bal==best[0] and raw>best[2]) or (bal==best[0] and raw==best[2] and abs(sh)<abs(best[1])):best=(bal,sh,raw)
        return best
    def plan(self,q):
        key=int(q)
        if key in self.cache:return self.cache[key]
        refs=[]
        for d in self.lags:
            fit,sh,raw=self._best_ref(q,d)
            if fit>=self.minfit:refs.append((d,sh,fit,raw))
        vals=[]
        for delay in range(0,MAX_WAIT+1,STEP):
            a=q+self.travel+delay;num=den=0.0
            for d,sh,fit,raw in refs:
                z=self._state(a-d*DAY-sh)
                if z is None:continue
                w=fit*fit/d;num+=w*int(z);den+=w
            if den:vals.append((delay,num/den))
        if vals:
            bestp=max(v for _,v in vals);cand=[x for x in vals if x[1]>=bestp-.04];groups=[]
            for x in cand:
                if not groups or x[0]-groups[-1][-1][0]>STEP:groups.append([x])
                else:groups[-1].append(x)
            g=max(groups,key=lambda z:(sum(v for _,v in z)/len(z),len(z),-z[0]));delay,prob=g[len(g)//2]
        else:delay,prob=0,.5
        feat={'fit':sum(x[2] for x in refs)/len(refs) if refs else 0.0,'maxfit':max((x[2] for x in refs),default=0.0),'raw':sum(x[3] for x in refs)/len(refs) if refs else 0.0,'refs':len(refs),'shift':sum(abs(x[1]) for x in refs)/len(refs)/max(self.shift_range,1) if refs else 0.0,'prob':prob,'delay':delay}
        self.cache[key]=(q+delay,float(prob),feat);return self.cache[key]

def dynamic_replay(tl,planner,starts,travel,refresh=STEP,max_wait=MAX_WAIT):
    hits=recs=0;details=[]
    for s in starts:
        q,deadline,sched=s,s+max_wait,None
        while q<=deadline:
            p=planner(q)
            if p is not None and p[0]<=deadline:sched=p
            if sched is not None and sched[0]<=q+refresh:
                dep=max(q,sched[0]);ok=tl.success(dep+travel,GRACE);hits+=int(ok);recs+=1;details.append((s,dep,dep+travel,int(ok)));break
            q+=refresh
        if sched is None:details.append((s,None,None,0))
    n=len(starts);return {'success':hits/n if n else 0.0,'coverage':recs/n if n else 0.0,'hits':hits,'n':n,'details':details}

def selector_feature_dict(ctx,country,item,s,pA,pB):
    ti=ctx.idx(country,item);gi=int(round((s-ctx.grid[0])/STEP));gi=max(0,min(gi,len(ctx.grid)-1));rL,rW=recent_target_series(ctx,country,item)
    def val(arr,default=0.0):
        x=arr[gi];return float(x) if np.isfinite(x) else default
    def ratio(a,b):
        aa,bb=val(a,np.nan),val(b,np.nan);return float(aa/bb) if np.isfinite(aa) and np.isfinite(bb) and bb else 1.0
    d={'g2_g18':ratio(ctx.g2,ctx.g18),'g6_g18':ratio(ctx.g6,ctx.g18),'active_frac':val(ctx.active_frac),'rL_g6':float(val(rL,0.0)/val(ctx.g6,1.0)) if val(ctx.g6,0.0) else 1.0,'rW':val(rW),'active':val(ctx.active[ti]),'age':val(ctx.age[ti]),'qty':val(ctx.qty[ti]),'hour':float((s%DAY)/DAY)}
    def unpack(p,prefix):
        if p:
            d[f'{prefix}_prob']=float(p[1]);robust=p[2] if len(p)>2 and isinstance(p[2],(int,float,np.floating)) else p[1];d[f'{prefix}_rob']=float(robust);d[f'{prefix}_delay']=float(p[0]-s)
        else:d[f'{prefix}_prob']=d[f'{prefix}_rob']=d[f'{prefix}_delay']=0.0
    unpack(pA,'A');unpack(pB,'B');d['dp']=d['B_prob']-d['A_prob'];d['dr']=d['B_rob']-d['A_rob'];d['ddelay']=d['B_delay']-d['A_delay']
    d.update({'g2':val(ctx.g2),'g6':val(ctx.g6),'g18':val(ctx.g18),'af':val(ctx.active_frac),'rL':val(rL),'rW2':val(rW)})
    return d

def fixed_expert_outcomes(tl,planner,starts,travel):
    out,first={},{}
    for s in starts:
        first[s]=planner(s);q,deadline,sched,res=s,s+MAX_WAIT,None,False
        while q<=deadline:
            p=planner(q)
            if p and p[0]<=deadline:sched=p
            if sched and sched[0]<=q+STEP:
                dep=max(q,sched[0]);res=tl.success(dep+travel,GRACE);break
            q+=STEP
        out[s]=int(bool(res))
    return out,first
