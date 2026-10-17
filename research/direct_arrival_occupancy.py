"""Regularized direct arrival-stock classifier, isolated historical research.

Unlike event clocks, this fits poll-backed stock>=30 labels at flight+wait
horizons. Individual labels mature before each canonical six-hour refit;
training starts before the evaluation window, so replay does not cold-start
the learner. Scores remain uncalibrated and are never event-time predictions.
"""
import bisect
import math

import numpy as np

from research.true_zero_cycles import ZeroCycles, model


class DirectArrivalOccupancy:
    MODES=('direct70','direct_peak')
    MAX_WAIT=28800
    REFIT=21600
    HISTORY=21*86400

    @staticmethod
    def state(tracker,issued):
        if tracker.last is not None and tracker.last.epoch>issued:
            raise ValueError('future observation in occupancy query')
        s=tracker.physical.asof();last=tracker.last
        hi=s['stocked_durations'];lo=s['depleted_durations'];onset=s['phase_onset']
        if (last is None or onset is None or issued-last.epoch>86400
                or min(len(hi),len(lo))<3):
            return None
        high=model.quantile(hi[-16:],.5);low=model.quantile(lo[-16:],.5)
        cycle=max(60,high+low);positive=int(last.quantity>0)
        age=max(0,issued-onset)
        prior_batch=(model.quantile(tracker.restock_quantities[-16:],.5)
                     if tracker.restock_quantities else 30)
        batch=max(30,tracker.batch_quantity or prior_batch)
        return (positive,age,cycle,high/cycle,min(4,last.quantity/batch),
                math.log1p(last.quantity/100),
                math.log(max(60,hi[-1]+lo[-1])/cycle),math.log1p(cycle/600))

    @staticmethod
    def design(state,issued,leads):
        positive,age,cycle,duty,quantity,logq,recent,logcycle=state
        leads=np.asarray(leads,dtype=float);h=leads/14400
        a=min(8,age/cycle);z=np.ones(len(leads))
        columns=[z,z*positive,z*a,z*min(64,a*a),z*quantity,z*logq,
                 z*duty,z*recent,z*logcycle,h,h*h,h*positive,h*a,h*quantity]
        phase=(age+leads)/cycle
        for harmonic in (1,2,3):
            angle=2*np.pi*harmonic*phase
            for wave in (np.sin(angle),np.cos(angle)):
                columns.extend((wave,wave*positive))
        angle=2*np.pi*((issued+leads)%86400)/86400
        columns.extend((np.sin(angle),np.cos(angle)))
        return np.column_stack(columns)

    def __init__(self,observations,polls,crosses,*,cutoff,flight_seconds,score):
        self.flight=flight_seconds;self.delays=np.arange(0,28801,300)
        rows=[];labels=[];maturity=[];origins=[]
        tracker=ZeroCycles(crosses);cursor=0
        # Hourly origins avoid counting every poll as independent training.
        if observations:
            first=(observations[0].epoch//3600+1)*3600
            if (cutoff-first)//3600>1100:
                raise ValueError('occupancy history origin cap exceeded')
            for start in range(first,cutoff-flight_seconds-190+1,3600):
                while cursor<len(observations) and observations[cursor].epoch<=start:
                    tracker.add(observations[cursor]);cursor+=1
                state=self.state(tracker,start)
                pi=bisect.bisect_right(polls,start)-1
                if state is None or pi<0 or start-polls[pi]>180 or crosses(start,start):
                    continue
                delays=np.arange(0,28801,900)
                leads=delays+flight_seconds
                x=self.design(state,start,leads)
                for j,lead in enumerate(leads):
                    arrival=start+int(lead)
                    if arrival+190>cutoff:continue
                    result=score(arrival)[0]
                    if result not in ('SUCCESS','FAILURE'):continue
                    rows.append(x[j]);labels.append(int(result=='SUCCESS'))
                    maturity.append(arrival+190);origins.append(start)
        self.x=np.asarray(rows,dtype=float).reshape((-1,28))
        self.y=np.asarray(labels,dtype=float)
        self.maturity=np.asarray(maturity,dtype=np.int64)
        self.origin=np.asarray(origins,dtype=np.int64)
        self.fit_epoch=None;self.fit=None;self.fit_count=0;self.training={}

    def _refit(self,epoch):
        self.fit_epoch=epoch;self.fit=None;self.fit_count+=1
        eligible=(self.maturity<=epoch)&(self.origin>=epoch-self.HISTORY)
        x=self.x[eligible];y=self.y[eligible];origin=self.origin[eligible]
        unique,counts=np.unique(origin,return_counts=True)
        self.training=dict(refit_epoch=epoch,known_rows=len(y),distinct_hourly_origins=len(unique),
            latest_training_truth_maturity=int(self.maturity[eligible].max()) if len(y) else None,
            oldest_training_origin=int(unique[0]) if len(unique) else None)
        if len(unique)<48 or min(np.sum(y==0),np.sum(y==1))<20:return
        # Each origin contributes at most one unit despite many lead labels.
        weights=np.exp2(-(epoch-origin)/(7*86400))/counts[np.searchsorted(unique,origin)]
        mean=np.average(x,axis=0,weights=weights)
        scale=np.sqrt(np.average((x-mean)**2,axis=0,weights=weights))
        scale=np.maximum(scale,.1);mean[0]=0;scale[0]=1
        x=(x-mean)/scale
        beta=np.zeros(x.shape[1]);base=float(np.average(y,weights=weights))
        beta[0]=math.log(max(.001,base)/max(.001,1-base))
        penalty=np.eye(x.shape[1])*3;penalty[0,0]=.01
        for _ in range(10):
            p=1/(1+np.exp(-np.clip(x@beta,-25,25)))
            variance=weights*np.maximum(.0001,p*(1-p))
            gradient=x.T@(weights*(y-p))-penalty@beta
            hessian=x.T@(x*variance[:,None])+penalty
            step=np.linalg.solve(hessian,gradient)
            step*=min(1,2/max(2,float(np.max(np.abs(step)))))
            beta+=step
            if np.max(np.abs(step))<.0001:break
        self.fit=(mean,scale,beta)

    def plans(self,issued,tracker,*,poll_age):
        empty={mode:dict(departure_epoch=None,status='INSUFFICIENT_DIRECT_TRAINING') for mode in self.MODES}
        state=self.state(tracker,issued)
        if state is None or poll_age is None or not 0<=poll_age<=180:return empty
        epoch=issued//self.REFIT*self.REFIT
        if self.fit_epoch!=epoch:self._refit(epoch)
        if self.fit is None:return empty
        mean,scale,beta=self.fit
        x=self.design(state,issued,self.flight+self.delays)
        support=1/(1+np.exp(-np.clip(((x-mean)/scale)@beta,-25,25)))
        # No fitted probability is described as calibrated. Peak is a
        # diagnostic best-score policy with an explicit low .15 floor.
        for mode in self.MODES:
            threshold=.7 if mode=='direct70' else max(.15,float(support.max())-.02)
            ids=np.flatnonzero(support>=threshold);j=int(ids[0]) if len(ids) else None
            empty[mode]=dict(departure_epoch=issued+int(self.delays[j]) if j is not None else None,
                status='DIRECT_ARRIVAL_PROPOSAL' if j is not None else 'NO_SUPPORTED_DIRECT_ARRIVAL',
                model_name='regularized_direct_arrival_occupancy_v1',mode=mode,
                uncalibrated_arrival_score=float(support[j]) if j is not None else None,
                calibrated_success_probability=None,event_timing_prediction_supported=False,
                depletion_stock_quantity=0,arrival_stock_threshold=30,training=dict(self.training))
        return empty

    def diagnostics(self):
        return dict(self.training,refit_count=self.fit_count,history_days=21,
            training_origin_weight='one per hourly origin, seven-day half-life',
            training_precedes_replay_window=True,model_family='direct ridge logistic arrival occupancy')
