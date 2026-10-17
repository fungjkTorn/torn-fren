"""Cycle-clock-conditioned complete trajectories; departure-only research.

Use prequential cycle errors to align old stock trajectories to a current
cycle forecast. Future stock paths must fully mature before each issue.
Ridge and median remain separate fixed policies, never hindsight selection.
"""
import bisect

import numpy as np

from research.restock_predictability_audit import cycles_from_rows,cycle_predictions


class CycleRegressionPaths:
    MODES=('ridge70','ridge_peak','median70','median_peak')
    MAX_WAIT=28800
    GRID=60

    def __init__(self,observations,crosses,*,cutoff,flight_seconds,interval_score):
        self.flight=flight_seconds;self.crosses=crosses
        self.trials,_=cycles_from_rows(observations,crosses,cutoff)
        self.starts=[t['start'] for t in self.trials]
        # Every fit is reconstructed at that cycle's birth using only already
        # observed completions. Future labels cannot alter an earlier fit.
        self.fits=[cycle_predictions(self.trials,t['start'],t['feature']) for t in self.trials]
        self.cases=[i for i,t in enumerate(self.trials) if t['outcome']=='CLOSED' and self.fits[i] is not None]
        self.times=np.asarray([r.epoch for r in observations],dtype=np.int64)
        self.quantities=np.asarray([r.quantity for r in observations],dtype=np.int64)
        self.delays=np.arange(0,self.MAX_WAIT+1,self.GRID,dtype=np.int64)
        self.grid_start=(observations[0].epoch//self.GRID)*self.GRID if observations else cutoff
        last=((cutoff-190-self.GRID)//self.GRID)*self.GRID
        n=max(0,(last-self.grid_start)//self.GRID+1)
        if n>150000:raise ValueError('cycle trajectory grid cap exceeded')
        self.values=np.asarray([interval_score(t,t+self.GRID)
            for t in range(self.grid_start,last+1,self.GRID)],dtype=np.int8)

    def plans(self,issued,tracker,*,poll_age):
        result={mode:dict(departure_epoch=None,status='INSUFFICIENT_CYCLE_TRAJECTORIES') for mode in self.MODES}
        last=tracker.last
        if last is not None and last.epoch>issued:raise ValueError('future cycle-path observation')
        if last is None or issued-last.epoch>86400 or poll_age is None or not 0<=poll_age<=180:
            return result
        i=bisect.bisect_right(self.starts,issued)-1
        if i<0:return result
        current=self.trials[i];fit=self.fits[i]
        if fit is None or current.get('invalidated_at',issued+1)<=issued:return result
        horizon=self.MAX_WAIT+self.flight+self.GRID+190
        # Entire shifted future trajectory, not just the fitted error, must
        # have completed before this issuance. Last64 is fixed before matching.
        ids=[j for j in self.cases if self.trials[j]['end']+horizon<=issued][-64:]
        if len(ids)<24:return result
        birth=np.asarray([self.trials[j]['start'] for j in ids],dtype=np.int64)
        end=np.asarray([self.trials[j]['end'] for j in ids],dtype=np.int64)
        for family in ('ridge','median'):
            residual=np.asarray([self.trials[j]['duration']-self.fits[j][family] for j in ids],dtype=np.int64)
            next_restock=current['start']+fit[family]+residual
            shadow=end+issued-next_restock
            indices=(shadow-self.grid_start)//self.GRID
            qi=np.searchsorted(self.times,shadow,side='right')-1
            inside=(indices>=0)&(indices<len(self.values))&(qi>=0)
            values=np.full(len(ids),-1,dtype=np.int8);values[inside]=self.values[indices[inside]]
            historical_quantity=np.zeros(len(ids),dtype=np.int64)
            historical_quantity[qi>=0]=self.quantities[qi[qi>=0]]
            allowed=(inside&(next_restock>issued)&(shadow>=birth)&(shadow<end)
                &((historical_quantity>0)==(last.quantity>0))
                &(values==int(last.quantity>=30)))
            selected=np.flatnonzero(allowed)
            if len(selected)<16:continue
            arrivals=end[selected,None]+issued+self.flight+self.delays[None,:]-next_restock[selected,None]
            positions=(arrivals-self.grid_start)//self.GRID
            in_bounds=(positions>=0)&(positions<len(self.values))
            outcomes=np.full(positions.shape,-1,dtype=np.int8)
            outcomes[in_bounds]=self.values[positions[in_bounds]]
            known=np.sum(outcomes>=0,axis=0)
            support=np.divide(np.sum(outcomes==1,axis=0),known,out=np.zeros(len(self.delays)),where=known>0)
            eligible=(known>=12)&(known/len(selected)>=.8)
            smooth=np.minimum(support,(support+np.r_[support[0],support[:-1]]+np.r_[support[1:],support[-1]])/3)
            peak=float(np.max(smooth[eligible])) if np.any(eligible) else 0
            for suffix in ('70','_peak'):
                mode=family+suffix;threshold=.7 if suffix=='70' else max(.15,peak-.03)
                choices=np.flatnonzero(eligible&(smooth>=threshold));j=int(choices[0]) if len(choices) else None
                result[mode]=dict(departure_epoch=issued+int(self.delays[j]) if j is not None else None,
                    status='CYCLE_CONDITIONED_PATH_PROPOSAL' if j is not None else 'NO_SUPPORTED_CYCLE_PATH_DEPARTURE',
                    model_name='prequential_cycle_conditioned_stock_paths_v1',family=family,
                    current_cycle_start_epoch=current['start'],point_cycle_duration_seconds=fit[family],
                    training_cycles=fit['training_cycles'],clock_fit_latest_training_end=fit['latest_training_end'],
                    selected_paths=len(selected),latest_training_path_end=int(end[selected].max())+horizon,
                    current_physical_and_buying_phase_matched=True,
                    uncalibrated_path_support=float(smooth[j]) if j is not None else None,
                    maximum_path_support=peak,known_path_mass=float(known[j]/len(selected)) if j is not None else None,
                    depletion_stock_quantity=0,arrival_stock_threshold=30,
                    calibrated_success_probability=None,event_timing_prediction_supported=False)
        return result
