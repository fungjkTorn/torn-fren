from __future__ import annotations
import argparse, json
from common import ResearchContext, TemplatePlanner, valid_starts, TRAVEL_SECONDS, MAX_WAIT, STEP, GRACE, DAY

EXPERTS=[(lags,look,shift) for lags in ((1,),(2,),(7,),(1,2),(1,7),(1,2,7)) for look in (7200,14400) for shift in (3600,7200)]
WINNING_WINDOWS={'Monkey Plushie':2,'Chamois Plushie':3}
TARGETS={'monkey':('arg','Monkey Plushie'),'chamois':('swi','Chamois Plushie')}

def replay_target(db:str,country:str,item:str):
    ctx=ResearchContext.build(db);tl=ctx.timelines[(country,item)];travel=TRAVEL_SECONDS[country];starts=valid_starts(ctx,country,item);hold=starts[int(.75*len(starts)):]
    planners={e:TemplatePlanner(ctx,country,item,lags=e[0],lookback=e[1],shift_range=e[2]).plan for e in EXPERTS}
    outcome={e:{} for e in EXPERTS}; resolved={e:{} for e in EXPERTS}
    for e,p in planners.items():
        for s in starts:
            q=s;deadline=s+MAX_WAIT;sched=None;ok=0;rt=None
            while q<=deadline:
                z=p(q)
                if z and z[0]<=deadline:sched=z
                if sched and sched[0]<=q+STEP:
                    dep=max(q,sched[0]);ok=int(tl.success(dep+travel,GRACE));rt=dep+travel+GRACE;break
                q+=STEP
            outcome[e][s]=ok;resolved[e][s]=rt
    days=WINNING_WINDOWS[item];hits=recs=0
    for s in hold:
        scores=[];cut=s-days*DAY
        for e in EXPERTS:
            ys=[outcome[e][h] for h in starts if cut<=h<s and resolved[e][h] is not None and resolved[e][h]<s]
            score=(sum(ys)+2)/(len(ys)+4) if ys else .5
            scores.append((score,len(ys),e))
        e=max(scores,key=lambda x:(x[0],x[1]))[2];hits+=outcome[e][s];recs+=1
    return {'item':f'{country}:{item}','config':{'resolved_performance_window_days':days,'expert_bank':EXPERTS},'holdout':{'success':hits/len(hold),'coverage':recs/len(hold),'hits':hits,'n':len(hold)}}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--db',required=True);ap.add_argument('--target',choices=TARGETS,required=True);a=ap.parse_args();c,i=TARGETS[a.target];print(json.dumps(replay_target(a.db,c,i),indent=2,default=str))
