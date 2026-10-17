from __future__ import annotations
import argparse, json
import numpy as np
from sklearn.linear_model import LogisticRegression
from common import ResearchContext, AnalogPlanner, valid_starts, TRAVEL_SECONDS, fixed_expert_outcomes, selector_feature_dict

COUNTRY='sou'; ITEM='Lion Plushie'
EXPERT_A={'k':14,'global_regime_weight':0.35}; EXPERT_B={'k':18,'global_regime_weight':0.50}
WINNING_CONFIG={'expert_a':EXPERT_A,'expert_b':EXPERT_B,'selector':'logistic class_weight=balanced max_iter=2000'}

def replay(db:str):
    ctx=ResearchContext.build(db);tl=ctx.timelines[(COUNTRY,ITEM)];travel=TRAVEL_SECONDS[COUNTRY];starts=valid_starts(ctx,COUNTRY,ITEM)
    sp=int(len(starts)*.75);train,hold=starts[:sp],starts[sp:];vi=int(len(train)*.70);early,val=train[:vi],train[vi:]
    pa=AnalogPlanner(ctx,COUNTRY,ITEM,EXPERT_A['k'],EXPERT_A['global_regime_weight'],cutoff=val[0]);pb=AnalogPlanner(ctx,COUNTRY,ITEM,EXPERT_B['k'],EXPERT_B['global_regime_weight'],cutoff=val[0])
    oAe,pAe=fixed_expert_outcomes(tl,pa.plan,early,travel);oBe,pBe=fixed_expert_outcomes(tl,pb.plan,early,travel)
    oAv,pAv=fixed_expert_outcomes(tl,pa.plan,val,travel);oBv,pBv=fixed_expert_outcomes(tl,pb.plan,val,travel)
    ha=AnalogPlanner(ctx,COUNTRY,ITEM,EXPERT_A['k'],EXPERT_A['global_regime_weight'],cutoff=hold[0]);hb=AnalogPlanner(ctx,COUNTRY,ITEM,EXPERT_B['k'],EXPERT_B['global_regime_weight'],cutoff=hold[0])
    oAh,pAh=fixed_expert_outcomes(tl,ha.plan,hold,travel);oBh,pBh=fixed_expert_outcomes(tl,hb.plan,hold,travel)
    names=None
    def vec(s,a,b):
        nonlocal names
        d=selector_feature_dict(ctx,COUNTRY,ITEM,s,a,b)
        if names is None:names=list(d)
        return np.array([d[k] for k in names],float)
    X=[];y=[]
    for s in early:
        if oAe[s]==oBe[s]:continue
        X.append(vec(s,pAe[s],pBe[s]));y.append(1 if (oBe[s] and not oAe[s]) else 0)
    X=np.vstack(X);y=np.array(y);med=np.nanmedian(X,axis=0);X=np.where(np.isfinite(X),X,med)
    clf=LogisticRegression(max_iter=2000,class_weight='balanced').fit(X,y)
    def score(sub,oA,oB,pA,pB):
        xx=np.vstack([vec(s,pA[s],pB[s]) for s in sub]);xx=np.where(np.isfinite(xx),xx,med);pred=clf.predict(xx)
        h=sum(oB[s] if int(z) else oA[s] for s,z in zip(sub,pred))
        return {'success':h/len(sub),'coverage':1.0,'hits':int(h),'n':len(sub),'use_b':int(pred.sum()),'a':sum(oA.values())/len(sub),'b':sum(oB.values())/len(sub),'oracle':sum(oA[s] or oB[s] for s in sub)/len(sub)}
    return {'item':f'{COUNTRY}:{ITEM}','config':WINNING_CONFIG,'validation':score(val,oAv,oBv,pAv,pBv),'holdout':score(hold,oAh,oBh,pAh,pBh),'features':names}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--db',required=True);a=ap.parse_args();print(json.dumps(replay(a.db),indent=2,default=str))
