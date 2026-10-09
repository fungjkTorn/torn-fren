from __future__ import annotations
import argparse, json
from common import ResearchContext, TemplatePlanner, valid_starts, TRAVEL_SECONDS, MAX_WAIT, STEP, GRACE

COUNTRY='uae';ITEM='Camel Plushie'
EXPERTS=[(lags,look,shift) for lags in ((1,),(2,),(7,),(1,2),(1,7),(1,2,7)) for look in (7200,14400) for shift in (3600,7200)]
WINNING_CONFIG={'expert_bank':'24 template experts','selector':'highest current recommended-plan probability'}

def replay(db:str):
    ctx=ResearchContext.build(db);tl=ctx.timelines[(COUNTRY,ITEM)];travel=TRAVEL_SECONDS[COUNTRY];starts=valid_starts(ctx,COUNTRY,ITEM);hold=starts[int(.75*len(starts)):]
    planners={e:TemplatePlanner(ctx,COUNTRY,ITEM,lags=e[0],lookback=e[1],shift_range=e[2]).plan for e in EXPERTS}
    hits=recs=0
    for s in hold:
        q=s;deadline=s+MAX_WAIT;sched=None
        while q<=deadline:
            candidates=[]
            for e,p in planners.items():
                z=p(q)
                if z and z[0]<=deadline:candidates.append((z[1],z[2].get('maxfit',0),-z[0],z))
            if candidates:sched=max(candidates,key=lambda x:(x[0],x[1],x[2]))[3]
            if sched and sched[0]<=q+STEP:
                dep=max(q,sched[0]);hits+=int(tl.success(dep+travel,GRACE));recs+=1;break
            q+=STEP
    return {'item':f'{COUNTRY}:{ITEM}','config':WINNING_CONFIG,'holdout':{'success':hits/len(hold),'coverage':recs/len(hold),'hits':hits,'n':len(hold)}}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--db',required=True);a=ap.parse_args();print(json.dumps(replay(a.db),indent=2,default=str))
