"""Small deterministic Newton-boosted trees for causal arrival stock labels.

Pure NumPy, fixed capacity and recency schedules; no dependency installation,
item-specific tuning, event accuracy inheritance or automatic promotion.
"""
import bisect
import math

import numpy as np

from research.inventory_feature_paths import InventoryFeaturePaths
from research.quantity_rate_cycles import QuantityRateCycles
from research.true_zero_cycles import model


class HistogramLogitTrees:
    ROUNDS=24
    RATE=.15
    REG=.5
    MAX_DEPTH=2

    def fit(self,x,y,weights):
        self.edges=[np.unique(np.quantile(x[:,j],np.arange(1,8)/8)) for j in range(x.shape[1])]
        bins=self.bin(x);self.trees=[]
        mean=float(np.average(y,weights=weights));self.base=math.log(max(.001,mean)/max(.001,1-mean))
        f=np.full(len(y),self.base)
        for _ in range(self.ROUNDS):
            p=1/(1+np.exp(-np.clip(f,-20,20)))
            gradient=weights*(y-p);hessian=weights*np.maximum(p*(1-p),.0001)
            tree=self._node(bins,gradient,hessian,weights,np.arange(len(y)),0)
            self.trees.append(tree);f+=self.RATE*self._predict_tree(tree,bins)
        return self

    def bin(self,x):
        return np.column_stack([np.searchsorted(edge,x[:,j],side='right') for j,edge in enumerate(self.edges)]).astype(np.uint8)

    def _node(self,bins,g,h,w,ids,depth):
        G=float(g[ids].sum());H=float(h[ids].sum());value=float(np.clip(G/(H+self.REG),-2,2))
        if depth>=self.MAX_DEPTH or len(ids)<48 or w[ids].sum()<6:return value
        best=1e-9;split=None;parent=G*G/(H+self.REG)
        for j in range(bins.shape[1]):
            b=bins[ids,j]
            count=np.cumsum(np.bincount(b,minlength=8))[:-1]
            mass=np.cumsum(np.bincount(b,weights=w[ids],minlength=8))[:-1]
            gs=np.cumsum(np.bincount(b,weights=g[ids],minlength=8))[:-1]
            hs=np.cumsum(np.bincount(b,weights=h[ids],minlength=8))[:-1]
            valid=(count>=24)&(len(ids)-count>=24)&(mass>=3)&(w[ids].sum()-mass>=3)
            gain=gs*gs/(hs+self.REG)+(G-gs)**2/(H-hs+self.REG)-parent
            gain[~valid]=-np.inf
            k=int(np.argmax(gain))
            if gain[k]>best:best=float(gain[k]);split=(j,k)
        if split is None:return value
        j,k=split;left=bins[ids,j]<=k
        return (j,k,self._node(bins,g,h,w,ids[left],depth+1),self._node(bins,g,h,w,ids[~left],depth+1))

    @classmethod
    def _predict_tree(cls,tree,bins):
        if not isinstance(tree,tuple):return np.full(len(bins),tree)
        j,k,left,right=tree;mask=bins[:,j]<=k;out=np.empty(len(bins))
        if np.any(mask):out[mask]=cls._predict_tree(left,bins[mask])
        if np.any(~mask):out[~mask]=cls._predict_tree(right,bins[~mask])
        return out

    def predict(self,x):
        bins=self.bin(x);f=np.full(len(x),self.base)
        for tree in self.trees:f+=self.RATE*self._predict_tree(tree,bins)
        return 1/(1+np.exp(-np.clip(f,-20,20)))


class TreeArrivalOccupancy:
    MODES=('stable70','stable_peak','recent70','recent_peak')
    REFIT=43200
    SCHEDULES={'stable':(14,7),'recent':(7,2)}

    @staticmethod
    def state(tracker,issued):
        feature=InventoryFeaturePaths.features(tracker,issued)
        if feature is None:return None
        s=tracker.physical.asof()
        cycle=max(60,model.quantile(s['stocked_durations'][-16:],.5)+model.quantile(s['depleted_durations'][-16:],.5))
        return feature,issued-s['phase_onset'],cycle

    @staticmethod
    def design(state,issued,leads):
        feature,age,cycle=state;leads=np.asarray(leads,dtype=float)
        columns=[np.full(len(leads),value) for value in feature]+[leads/3600,leads/cycle]
        for harmonic in (1,2):
            angle=2*np.pi*harmonic*(age+leads)/cycle
            columns.extend((np.sin(angle),np.cos(angle)))
        angle=2*np.pi*((issued+leads)%86400)/86400
        columns.extend((np.sin(angle),np.cos(angle)))
        return np.column_stack(columns)

    def __init__(self,observations,polls,crosses,*,cutoff,flight_seconds,score):
        self.flight=flight_seconds;self.delays=np.arange(0,28801,120)
        rows=[];labels=[];maturity=[];origins=[];tracker=QuantityRateCycles(crosses);cursor=0
        if observations:
            first=(observations[0].epoch//3600+1)*3600
            if (cutoff-first)//3600>1100:raise ValueError('tree origin cap exceeded')
            for start in range(first,cutoff-flight_seconds-190+1,3600):
                while cursor<len(observations) and observations[cursor].epoch<=start:
                    tracker.add(observations[cursor]);cursor+=1
                state=self.state(tracker,start);pi=bisect.bisect_right(polls,start)-1
                if state is None or pi<0 or start-polls[pi]>180 or crosses(start,start):continue
                leads=flight_seconds+np.arange(0,28801,900);x=self.design(state,start,leads)
                for j,lead in enumerate(leads):
                    arrival=start+int(lead)
                    if arrival+190>cutoff:continue
                    outcome=score(arrival)[0]
                    if outcome not in ('SUCCESS','FAILURE'):continue
                    rows.append(x[j]);labels.append(int(outcome=='SUCCESS'));origins.append(start);maturity.append(arrival+190)
        self.x=np.asarray(rows,dtype=float).reshape((-1,22));self.y=np.asarray(labels,dtype=float)
        self.origin=np.asarray(origins,dtype=np.int64);self.maturity=np.asarray(maturity,dtype=np.int64)
        self.fit_epoch=None;self.fits={};self.training={};self.fit_count=0

    def _refit(self,epoch):
        self.fit_epoch=epoch;self.fits={};self.fit_count+=1
        for family,(days,half) in self.SCHEDULES.items():
            eligible=(self.maturity<=epoch)&(self.origin>=epoch-days*86400)
            x=self.x[eligible];y=self.y[eligible];origin=self.origin[eligible]
            unique,counts=np.unique(origin,return_counts=True)
            self.training[family]=dict(refit_epoch=epoch,known_rows=len(y),distinct_hourly_origins=len(unique),
                latest_training_truth_maturity=int(self.maturity[eligible].max()) if len(y) else None,
                oldest_training_origin=int(unique[0]) if len(unique) else None,
                history_days=days,weight_half_life_days=half)
            if len(unique)<48 or min(np.sum(y==0),np.sum(y==1))<20:continue
            weights=np.exp2(-(epoch-origin)/(half*86400))/counts[np.searchsorted(unique,origin)]
            self.fits[family]=HistogramLogitTrees().fit(x,y,weights)

    def plans(self,issued,tracker,*,poll_age):
        result={mode:dict(departure_epoch=None,status='INSUFFICIENT_TREE_TRAINING') for mode in self.MODES}
        if tracker.last is not None and tracker.last.epoch>issued:raise ValueError('future tree query observation')
        state=self.state(tracker,issued)
        if state is None or poll_age is None or not 0<=poll_age<=180:return result
        epoch=issued//self.REFIT*self.REFIT
        if epoch!=self.fit_epoch:self._refit(epoch)
        x=self.design(state,issued,self.flight+self.delays)
        for family,fit in self.fits.items():
            score=fit.predict(x)
            smooth=np.minimum(score,(score+np.r_[score[0],score[:-1]]+np.r_[score[1:],score[-1]])/3)
            for suffix in ('70','_peak'):
                threshold=.7 if suffix=='70' else max(.15,float(smooth.max())-.02)
                choices=np.flatnonzero(smooth>=threshold);j=int(choices[0]) if len(choices) else None
                result[family+suffix]=dict(departure_epoch=issued+int(self.delays[j]) if j is not None else None,
                    status='TREE_ARRIVAL_PROPOSAL' if j is not None else 'NO_SUPPORTED_TREE_DEPARTURE',
                    model_name='fixed_histogram_logit_trees_v1',family=family,training=dict(self.training[family]),
                    uncalibrated_arrival_score=float(smooth[j]) if j is not None else None,
                    calibrated_success_probability=None,event_timing_prediction_supported=False,
                    depletion_stock_quantity=0,arrival_stock_threshold=30)
        return result
