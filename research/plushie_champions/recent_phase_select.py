from __future__ import annotations
import argparse, json
from common import ResearchContext, TemplatePlanner, dynamic_replay, valid_starts, TRAVEL_SECONDS

COUNTRY='uni'; ITEM='Nessie Plushie'
WINNING_CONFIG={'lookback_h':2,'lags':(1,),'shift_h':1,'minfit':0.5,'recency_pow':1.0,'selection_recent_train_fraction':0.15}

def replay(db:str):
    ctx=ResearchContext.build(db)
    tl=ctx.timelines[(COUNTRY,ITEM)]
    starts=valid_starts(ctx,COUNTRY,ITEM)
    cut=int(.75*len(starts)); train,hold=starts[:cut],starts[cut:]
    n=max(40,int(len(train)*WINNING_CONFIG['selection_recent_train_fraction']))
    val=train[-n:]
    planner=TemplatePlanner(ctx,COUNTRY,ITEM,lags=WINNING_CONFIG['lags'],lookback=WINNING_CONFIG['lookback_h']*3600,shift_range=WINNING_CONFIG['shift_h']*3600,minfit=WINNING_CONFIG['minfit'])
    vr=dynamic_replay(tl,planner.plan,val,TRAVEL_SECONDS[COUNTRY])
    hr=dynamic_replay(tl,planner.plan,hold,TRAVEL_SECONDS[COUNTRY])
    return {'item':f'{COUNTRY}:{ITEM}','config':WINNING_CONFIG,'validation':vr,'holdout':hr}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--db',required=True);a=ap.parse_args();print(json.dumps(replay(a.db),indent=2,default=str))
