"""Research-only whole trajectories aligned to physical phase onsets.

Unlike fixed-clock neighbors, each historical path is queried at the SAME
elapsed positive/zero phase age as the issue. Future cycles stay together.
Peak selection is an explicit low-support diagnostic, not a safe-trip claim.
"""
import bisect
import math

import numpy as np

from research.true_zero_cycles import ZeroCycles, model


class PhaseAlignedStockPaths:
    MODES=('analog_peak','recent_peak','analog50','analog70')
    MAX_WAIT=28800
    GRID=60

    @staticmethod
    def features(tracker,issued):
        state=tracker.physical.asof()
        hi=state['stocked_durations'];lo=state['depleted_durations']
        onset=state['phase_onset']
        last=tracker.last
        if (onset is None or onset>issued or last is None or last.epoch>issued
            or issued-last.epoch>86400 or min(len(hi),len(lo))<3
            or not tracker.restock_quantities):
            return None
        angle=2*math.pi*(onset%86400)/86400
        # Same phase implies the same meaning of the most recently closed
        # positive/zero phases. Age is aligned exactly, never a distance term.
        return (int(last.quantity>0),onset,
                math.log1p(tracker.restock_quantities[-1]/100),
                math.log1p(hi[-1]/600),math.log1p(lo[-1]/600),
                math.log1p(model.quantile(hi[-8:],.5)/600),
                math.log1p(model.quantile(lo[-8:],.5)/600),
                math.sin(angle),math.cos(angle))

    def __init__(self,observations,crosses,*,cutoff,flight_seconds,interval_score):
        self.flight=flight_seconds
        self.crosses=crosses
        self.delays=np.arange(0,self.MAX_WAIT+1,self.GRID,dtype=np.int64)
        self.anchors=[];features=[];ends=[]
        tracker=ZeroCycles(crosses)
        previous=None;active=None
        for row in observations:
            if row.epoch>cutoff:break
            tracker.add(row)
            f=self.features(tracker,row.epoch)
            if active is not None and (f is None or (f[0],f[1])!=active):
                ends[-1]=row.epoch
                active=None
            transition=(previous is not None and (previous.quantity>0)!=(row.quantity>0)
                        and previous.source==row.source and not crosses(previous.epoch,row.epoch))
            if f is not None and transition and f[1]==row.epoch:
                self.anchors.append(row.epoch);features.append((f[0],)+f[2:])
                ends.append(cutoff+1);active=(f[0],f[1])
            previous=row
        self.anchors=np.asarray(self.anchors,dtype=np.int64)
        self.features_matrix=np.asarray(features,dtype=float).reshape((-1,8))
        self.phase_ends=np.asarray(ends,dtype=np.int64)
        self.grid_start=(observations[0].epoch//self.GRID)*self.GRID if observations else cutoff
        last=((cutoff-190-self.GRID)//self.GRID)*self.GRID
        n=max(0,(last-self.grid_start)//self.GRID+1)
        if n>150000:raise ValueError('aligned trajectory grid cap exceeded')
        # Each cell certifies the entire minute, not just two endpoints.
        self.values=np.asarray([interval_score(t,t+self.GRID)
            for t in range(self.grid_start,last+1,self.GRID)],dtype=np.int8)

    def plans(self,issued,tracker,*,poll_age):
        result={m:dict(departure_epoch=None,status='INSUFFICIENT_ALIGNED_PATH_SUPPORT') for m in self.MODES}
        if tracker.last is not None and tracker.last.epoch>issued:
            raise ValueError('future physical observation in aligned query')
        f=self.features(tracker,issued)
        if f is None or poll_age is None or not 0<=poll_age<=180:return result
        phase,onset=f[:2];age=issued-onset
        # Historical phases must still be active at the matched age. Reject
        # the entire historical path until ALL wait/flight bins mature.
        horizon=age+self.MAX_WAIT+self.flight+self.GRID+190
        end=bisect.bisect_right(self.anchors,issued-horizon)
        ids=np.arange(max(0,end-512),end)
        ids=ids[(self.features_matrix[ids,0]==phase)&(self.phase_ends[ids]>self.anchors[ids]+age)]
        ids=ids[[not self.crosses(int(t),int(t)+age) for t in self.anchors[ids]]]
        if len(ids)<24:return result
        distance=np.mean((self.features_matrix[ids,1:]-np.asarray(f[2:]))**2,axis=1)
        order=np.argsort(distance,kind='stable')[:32]
        picks={'analog':(ids[order],np.exp(-np.sqrt(distance[order]))),
               'recent':(ids[-64:],np.ones(min(64,len(ids))))}
        for name,(paths,weights) in picks.items():
            arrival=self.anchors[paths,None]+age+self.flight+self.delays[None,:]
            indices=(arrival-self.grid_start)//self.GRID
            inside=(indices>=0)&(indices<len(self.values))
            values=np.full(indices.shape,-1,dtype=np.int8)
            values[inside]=self.values[indices[inside]]
            weights=weights/weights.sum()
            known=values>=0
            mass=np.sum(known*weights[:,None],axis=0)
            support=np.divide(np.sum((values==1)*weights[:,None],axis=0),mass,
                              out=np.zeros(len(self.delays)),where=mass>0)
            eligible=(np.sum(known,axis=0)>=16)&(mass>=.8)
            smooth=np.minimum(support,(support+np.r_[support[0],support[:-1]]+
                                       np.r_[support[1:],support[-1]])/3)
            peak=float(np.max(smooth[eligible])) if np.any(eligible) else 0.
            for mode in self.MODES:
                if not mode.startswith(name):continue
                diagnostic=mode.endswith('peak')
                threshold=max(.15,peak-.03) if diagnostic else .7 if mode.endswith('70') else .5
                candidates=np.flatnonzero(eligible&(smooth>=threshold))
                j=int(candidates[0]) if len(candidates) else None
                result[mode]=dict(departure_epoch=issued+int(self.delays[j]) if j is not None else None,
                    status='UNCALIBRATED_ALIGNED_PATH_DIAGNOSTIC' if j is not None else 'NO_SUPPORTED_ALIGNED_DEPARTURE',
                    model_name='physical_phase_aligned_trajectories_v1',mode=mode,
                    selected_paths=len(paths),physical_phase_age_seconds=age,
                    physical_phase_onset_epoch=onset,
                    latest_training_path_end=int(self.anchors[paths].max())+horizon,
                    uncalibrated_path_support=float(smooth[j]) if j is not None else None,
                    maximum_path_support=peak,known_path_mass=float(mass[j]) if j is not None else None,
                    low_support_peak_diagnostic=diagnostic,
                    calibrated_success_probability=None,event_timing_prediction_supported=False,
                    depletion_stock_quantity=0,arrival_stock_threshold=30)
        return result
