"""Past-only corrections to future-quarter arrival clocks; research only.

Training uses hourly fixed counterfactual departures, NOT player flights or
replanned execution. Actual policy evaluation remains five-minute replanning.
All31 offsets must mature before ANY label in a trial may enter training.
"""
from collections import Counter

import numpy as np

from services.travel_window_policy import project_policy


class ArrivalClockCorrection:
    MODES=('recent','stable')
    OFFSETS=np.arange(-900,901,60,dtype=np.int64)

    def __init__(self,family):
        self.family=family
        self.pending=[];self.history={0:[],1:[],2:[]}
        self.seen=set();self.seen_order=[]
        self.version=0;self.cache={};self.last_issue=None
        self.counts=Counter();self.chosen={m:Counter() for m in self.MODES}

    @staticmethod
    def bucket(lead):return min(2,max(0,lead//7200))

    def _resolve(self,issued,score):
        waiting=[];changed=False
        for trial in self.pending:
            if trial['ready']>issued:
                waiting.append(trial);continue
            values=[]
            for offset in self.OFFSETS:
                outcome,_,_=score(trial['arrival']+int(offset))
                if outcome=='PENDING':raise ValueError('mature clock trial returned pending truth')
                values.append(1 if outcome=='SUCCESS' else 0 if outcome=='FAILURE' else -1)
            row=dict(trial,values=values)
            bucket=self.history[trial['bucket']]
            bucket.append(row);bucket.sort(key=lambda r:r['issued'])
            del bucket[:-64]
            self.counts['matured_trials']+=1;self.version+=1
            changed=True
        self.pending=waiting
        if changed:self.cache.clear()

    def fit(self,bucket,mode):
        key=(bucket,mode,self.version)
        if key in self.cache:return self.cache[key]
        rows=self.history[bucket][-(32 if mode=='recent' else 64):]
        minimum=12 if mode=='recent' else 24
        best=dict(offset_seconds=0,training_trials=len(rows),matched_trials=0,
                  paired_gain=0.,latest_training_maturity=max((r['ready'] for r in rows),default=None),
                  calibrated_success_probability=None)
        best_key=(0.,0,0,0)
        if len(rows)>=minimum:
            values=np.asarray([r['values'] for r in rows])
            baseline=values[:,15]
            for j,offset in enumerate(self.OFFSETS):
                paired=(baseline>=0)&(values[:,j]>=0)
                n=int(paired.sum())
                if n<max(minimum,.8*len(rows)):continue
                delta=values[:,j]-baseline
                gain=float(delta[paired].mean())
                if gain<.05:continue
                if mode=='stable':
                    half=len(rows)//2
                    halves=(slice(None,half),slice(half,None))
                    if any(int(paired[s].sum())<max(12,.8*len(paired[s])) or
                           float(delta[s][paired[s]].mean())<.02 for s in halves):continue
                rank=(gain,n,-abs(int(offset)),-int(offset))
                if rank>best_key:
                    best_key=rank
                    best.update(offset_seconds=int(offset),matched_trials=n,paired_gain=round(gain,6))
        self.cache[key]=best
        return best

    def plans(self,issued,forecast,*,poll_age,score):
        if self.last_issue is not None and issued<=self.last_issue:
            raise ValueError('clock correction requires increasing issues')
        self.last_issue=issued
        self._resolve(issued,score)
        baseline=project_policy(forecast,now=issued,poll_age_seconds=poll_age,kind='current_quarter')
        flight=baseline['player_flight_seconds'];grace=baseline['arrival_grace_seconds']
        healthy=(poll_age is not None and 0<=poll_age<=180
                 and forecast['status']=='EVENT_TIMELINE_FORECAST_AVAILABLE')
        events=baseline['forecast_events']
        onset=forecast.get('physical_phase_onset_epoch')
        if healthy and onset is not None and issued%3600==0:
            for event in events:
                start=event['predicted_restock_epoch'];end=event['predicted_stock_below_30_epoch']
                arrival=start+(end-start)//4-grace
                departure=arrival-flight
                # All positive/negative counterfactual clocks must be feasible
                # at the original issue, within its original eight-hour wait.
                if not issued+900<=departure<=issued+28800-900:continue
                bucket=self.bucket(arrival-issued);identity=(onset,bucket)
                if identity not in self.seen:
                    self.seen.add(identity);self.seen_order.append(identity)
                    if len(self.seen_order)>512:self.seen.remove(self.seen_order.pop(0))
                    self.pending.append(dict(issued=issued,arrival=arrival,bucket=bucket,
                        ready=arrival+900+190))
                    self.counts['enrolled_trials']+=1
                break
        if len(self.pending)>32:raise ValueError('clock pending trial cap exceeded')
        result={}
        for mode in self.MODES:
            departure=baseline['estimated_departure_epoch'];fit=None;offset=0
            # Preserve exact baseline behavior with no supported correction,
            # and keep observed-current survival separate from future clocks.
            if healthy and baseline['status']!='MODELED_CURRENT_STOCK_REACHABLE':
                candidates=[]
                for event in events:
                    start=event['predicted_restock_epoch'];end=event['predicted_stock_below_30_epoch']
                    target=start+(end-start)//4
                    learned=self.fit(self.bucket(target-grace-issued),mode)
                    shift=learned['offset_seconds']
                    dep=max(issued,target-grace-flight+shift)
                    if start+shift<=dep+flight+grace<end+shift and dep<=issued+28800:
                        candidates.append((dep,event['index'],learned))
                if any(v[2]['offset_seconds'] for v in candidates):
                    departure,_,fit=min(candidates,key=lambda v:(v[0],v[1]))
                    offset=fit['offset_seconds']
            if departure is not None and departure>issued+28800:departure=None
            self.chosen[mode][offset]+=1
            result[mode]=dict(departure_epoch=departure,
                status='UNCALIBRATED_PAST_ERROR_CLOCK_CORRECTION' if departure is not None else baseline['status'],
                model_name='matured_arrival_clock_correction_v1',base_forecast_family=self.family,
                mode=mode,offset_seconds=offset,training=fit,
                calibrated_success_probability=None,event_timing_prediction_supported=False,
                depletion_stock_quantity=0,arrival_stock_threshold=30)
        return result

    def diagnostics(self):
        return dict(self.counts,pending_trials=len(self.pending),
            history_by_lead_bucket={k:len(v) for k,v in self.history.items()},
            current_fits={m:{b:self.fit(b,m) for b in self.history} for m in self.MODES},
            issue_offset_counts={m:dict(v) for m,v in self.chosen.items()},
            training_unit='Matured hourly counterfactual clocks, deduplicated by observed physical phase and lead bucket; correlated, not actual execution')
