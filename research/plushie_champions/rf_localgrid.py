from __future__ import annotations
import argparse, json
from common import ResearchContext, AnalogPlanner, dynamic_replay, valid_starts, TRAVEL_SECONDS

COUNTRY='uni'; ITEM='Red Fox Plushie'; WINNING_CONFIG={'k':18,'global_regime_weight':0.5}

def replay(db:str):
    ctx=ResearchContext.build(db);tl=ctx.timelines[(COUNTRY,ITEM)];starts=valid_starts(ctx,COUNTRY,ITEM)
    sp=int(.75*len(starts)); train,hold=starts[:sp],starts[sp:]; vi=int(len(train)*.70); val=train[vi:]
    planner=AnalogPlanner(ctx,COUNTRY,ITEM,WINNING_CONFIG['k'],WINNING_CONFIG['global_regime_weight'],cutoff=hold[0])
    vr=dynamic_replay(tl,planner.plan,val,TRAVEL_SECONDS[COUNTRY]);hr=dynamic_replay(tl,planner.plan,hold,TRAVEL_SECONDS[COUNTRY])
    return {'item':f'{COUNTRY}:{ITEM}','config':WINNING_CONFIG,'validation':vr,'holdout':hr}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--db',required=True);a=ap.parse_args();print(json.dumps(replay(a.db),indent=2,default=str))
