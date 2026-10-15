"""Arrival-only analogs of complete, already observed inventory trajectories.

Historical paths retain their actual sequence of physical zero waits, stock
lifetimes and buying windows. No marginal phase medians are chained. Outcome
matrices may be precomputed offline, but a path is never eligible until its
ENTIRE wait+flight horizon and evidence lag have elapsed before issuance.
"""
import bisect
import math

import numpy as np

from research.true_zero_cycles import ZeroCycles, model


class CausalStockPaths:
    MAX_WAIT=28800
    MODES=('recent70','analog70','analog80')

    @staticmethod
    def features(tracker,asof):
        state=tracker.physical.asof()
        onset=state['phase_onset'];last=tracker.last
        hi=state['stocked_durations'];lo=state['depleted_durations']
        if (onset is None or last is None or last.epoch>asof or asof-last.epoch>86400
            or min(len(hi),len(lo))<3):
            return None
        angle=2*math.pi*(asof%86400)/86400
        return (int(last.quantity>0),math.log1p((asof-onset)/300),
                math.log1p(last.quantity/100),
                math.log1p(model.quantile(hi[-8:],.5)/600),
                math.log1p(model.quantile(lo[-8:],.5)/600),
                math.sin(angle),math.cos(angle))

    def __init__(self,observations,polls,crosses,*,cutoff,flight_seconds,score):
        self.flight=flight_seconds
        self.delays=np.arange(0,self.MAX_WAIT+1,120,dtype=np.int64)
        self.starts=[];features=[];outcomes=[]
        score_cache={}
        tracker=ZeroCycles(crosses);cursor=0
        if observations:
            first=((observations[0].epoch//1800)+1)*1800
            last=cutoff-self.MAX_WAIT-flight_seconds-190
            if max(0,(last-first)//1800+1)>4096:
                raise ValueError('historical path grid cap exceeded')
            for start in range(first,last+1,1800):
                while cursor<len(observations) and observations[cursor].epoch<=start:
                    tracker.add(observations[cursor]);cursor+=1
                feature=self.features(tracker,start)
                pi=bisect.bisect_right(polls,start)-1
                if feature is None or pi<0 or start-polls[pi]>180 or crosses(start,start):
                    continue
                row=[]
                for delay in self.delays:
                    arrival=start+int(delay)+flight_seconds
                    if arrival not in score_cache:
                        outcome,_,_=score(arrival)
                        score_cache[arrival]=1 if outcome=='SUCCESS' else 0 if outcome=='FAILURE' else -1
                    row.append(score_cache[arrival])
                self.starts.append(start);features.append(feature);outcomes.append(row)
        self.starts=np.asarray(self.starts,dtype=np.int64)
        self.features_matrix=np.asarray(features,dtype=float).reshape((-1,7))
        self.outcomes=np.asarray(outcomes,dtype=np.int8).reshape((-1,len(self.delays)))

    def plans(self,issued,tracker,*,poll_age):
        empty={m:dict(departure_epoch=None,status='INSUFFICIENT_CAUSAL_PATH_SUPPORT') for m in self.MODES}
        if tracker.last is not None and tracker.last.epoch>issued:
            raise ValueError('future stock observation in path query')
        feature=self.features(tracker,issued)
        if feature is None or poll_age is None or not 0<=poll_age<=180:
            return empty
        # Critically this bound is per ISSUE, not the final replay cutoff.
        end=bisect.bisect_right(self.starts,issued-self.MAX_WAIT-self.flight-190)
        candidates=np.arange(max(0,end-512),end)
        candidates=candidates[self.features_matrix[candidates,0]==feature[0]]
        if len(candidates)<24:
            return empty
        current=np.asarray(feature)
        distance=np.mean((self.features_matrix[candidates,1:]-current[1:])**2,axis=1)
        order=np.argsort(distance,kind='stable')[:32]
        picks={'recent':candidates,'analog':candidates[order]}
        for name,ids in picks.items():
            weights=(np.ones(len(ids)) if name=='recent' else np.exp(-np.sqrt(distance[order])))
            weights=weights/weights.sum()
            values=self.outcomes[ids]
            known=values>=0
            mass=np.sum(known*weights[:,None],axis=0)
            support=np.divide(np.sum((values==1)*weights[:,None],axis=0),mass,
                              out=np.zeros(len(self.delays)),where=mass>0)
            eligible=(np.sum(known,axis=0)>=16)&(mass>=.8)
            # Demand support in adjacent departure bins too. This is empirical
            # scenario agreement, not a calibrated success probability.
            smooth=np.minimum(support,(support+np.r_[support[0],support[:-1]]+
                                       np.r_[support[1:],support[-1]])/3)
            for mode in self.MODES:
                if not mode.startswith(name):
                    continue
                threshold=.8 if mode.endswith('80') else .7
                selected=np.flatnonzero(eligible&(smooth>=threshold))
                j=int(selected[0]) if len(selected) else None
                empty[mode]=dict(departure_epoch=issued+int(self.delays[j]) if j is not None else None,
                    status='HISTORICAL_PATH_PROPOSAL' if j is not None else 'NO_SUPPORTED_PATH_DEPARTURE',
                    model_name='causal_complete_stock_paths_v1',mode=mode,
                    selected_paths=len(ids),latest_training_path_end=int(self.starts[ids].max())+self.MAX_WAIT+self.flight+190,
                    uncalibrated_path_support=float(smooth[j]) if j is not None else None,
                    known_path_mass=float(mass[j]) if j is not None else None,
                    depletion_stock_quantity=0,arrival_stock_threshold=30,
                    calibrated_success_probability=None,
                    event_timing_prediction_supported=False)
        return empty
