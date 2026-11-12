"""Controlled feature ablation on mature, observed inventory trajectories.

Every family uses the same candidate paths, neighbor count, maturity rule,
training-only scaling and departure rules. Quantity and observed decline rate
are added in stages; no event clock or future batch quantity is invented.
"""
import bisect
import math
from statistics import median

import numpy as np

from research.causal_stock_paths import CausalStockPaths
from research.quantity_rate_cycles import QuantityRateCycles


class InventoryFeaturePaths:
    GROUPS={
        'phase':(1,3,4,5,6),
        'quantity':(1,2,3,4,5,6,7,8),
        'flow':(1,2,3,4,5,6,7,8,9,10,11,12,13),
    }
    MODES=tuple(group+gate for group in GROUPS for gate in ('70','_peak'))

    @staticmethod
    def features(tracker,issued):
        core=CausalStockPaths.features(tracker,issued)
        if core is None:return None
        q=tracker.last.quantity
        prior=median(tracker.restock_quantities[-16:]) if tracker.restock_quantities else 30
        batch=max(30,tracker.batch_quantity or prior)
        rates=list(tracker.rates)[-16:]
        completed=median(rates) if rates else 0
        current=median(tracker._current_rates(issued)) if rates else 0
        # _current_rates falls back unless the current segment has >=3 drops
        # spanning >=3min within10min, and no old last update (>180s).
        recent=[r for r in tracker.segment if issued-600<=r.epoch<=issued]
        observed=(q>0 and len(recent)>=4 and issued-recent[0].epoch>=180
            and issued-tracker.last.epoch<=180
            and sum(a.quantity>b.quantity for a,b in zip(recent,recent[1:]))>=3
            and recent[0].quantity>q and completed>0)
        ratio=current/completed if completed>0 else 1
        residual=q/current if q>0 and current>0 else 0
        buying=max(0,q-29)/current if q>0 and current>0 else 0
        return core+(math.log1p(q/batch),math.log(max(.25,min(4,batch/max(30,prior)))),
            math.log1p(completed*60/100),math.log(max(.25,min(4,ratio))),int(observed),
            math.log1p(min(28800,residual)/600),math.log1p(min(28800,buying)/600))

    def __init__(self,base,observations,crosses):
        self.base=base;matrix=[];tracker=QuantityRateCycles(crosses);cursor=0
        for issued in base.starts:
            issued=int(issued)
            while cursor<len(observations) and observations[cursor].epoch<=issued:
                tracker.add(observations[cursor]);cursor+=1
            feature=self.features(tracker,issued)
            if feature is None:raise ValueError('base path lacks inventory feature state')
            matrix.append(feature)
        self.matrix=np.asarray(matrix,dtype=float).reshape((-1,14))

    def plans(self,issued,tracker,*,poll_age):
        result={mode:dict(departure_epoch=None,status='INSUFFICIENT_INVENTORY_PATHS') for mode in self.MODES}
        if tracker.last is not None and tracker.last.epoch>issued:raise ValueError('future inventory-path observation')
        feature=self.features(tracker,issued)
        if feature is None or poll_age is None or not 0<=poll_age<=180:return result
        b=self.base
        end=bisect.bisect_right(b.starts,issued-b.MAX_WAIT-b.flight-190)
        candidates=np.arange(max(0,end-512),end)
        candidates=candidates[self.matrix[candidates,0]==feature[0]]
        if len(candidates)<24:return result
        current=np.asarray(feature)
        for family,columns in self.GROUPS.items():
            x=self.matrix[candidates][:,columns]
            # Neither later origins nor future labels set the feature scale.
            scale=np.maximum(np.quantile(x,.75,axis=0)-np.quantile(x,.25,axis=0),.25)
            delta=np.clip((x-current[list(columns)])/scale,-8,8)
            distance=np.mean(delta**2,axis=1)
            chosen=np.argsort(distance,kind='stable')[:32]
            ids=candidates[chosen];weights=np.exp(-np.sqrt(distance[chosen]));weights/=weights.sum()
            outcomes=b.outcomes[ids];known=outcomes>=0
            mass=np.sum(known*weights[:,None],axis=0)
            support=np.divide(np.sum((outcomes==1)*weights[:,None],axis=0),mass,
                out=np.zeros(len(b.delays)),where=mass>0)
            eligible=(np.sum(known,axis=0)>=16)&(mass>=.8)
            smooth=np.minimum(support,(support+np.r_[support[0],support[:-1]]+np.r_[support[1:],support[-1]])/3)
            peak=float(np.max(smooth[eligible])) if np.any(eligible) else 0
            for suffix in ('70','_peak'):
                threshold=.7 if suffix=='70' else max(.15,peak-.03)
                choices=np.flatnonzero(eligible&(smooth>=threshold));j=int(choices[0]) if len(choices) else None
                result[family+suffix]=dict(departure_epoch=issued+int(b.delays[j]) if j is not None else None,
                    status='INVENTORY_FEATURE_PATH_PROPOSAL' if j is not None else 'NO_SUPPORTED_INVENTORY_DEPARTURE',
                    model_name='causal_inventory_feature_ablation_v1',feature_family=family,
                    feature_indices=list(columns),selected_paths=len(ids),candidate_paths=len(candidates),
                    latest_training_path_end=int(b.starts[ids].max())+b.MAX_WAIT+b.flight+190,
                    scale_training_latest_origin=int(b.starts[candidates].max()),
                    observed_current_rate_supported=bool(feature[11]),
                    uncalibrated_path_support=float(smooth[j]) if j is not None else None,
                    maximum_path_support=peak,known_path_mass=float(mass[j]) if j is not None else None,
                    depletion_stock_quantity=0,arrival_stock_threshold=30,
                    calibrated_success_probability=None,event_timing_prediction_supported=False)
        return result
