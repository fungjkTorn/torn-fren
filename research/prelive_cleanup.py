"""Approved next-six cleanup, fixed before comparative accuracy replay.

Only real earlier observations and successful poll evidence are used. No
selection on realized arrival outcomes. Native generations/configs stay pinned.
"""
import bisect
from contextlib import closing
from copy import deepcopy
import math
import os
from pathlib import Path
import sqlite3

from deploy.scripts.v163_readonly_event_first_preview import predict_events,phase_quantiles
from research.corrected_challengers import NEXT_SIX_MODELS,ALL_MODELS
from research.plushie_champions.common import TRAVEL_SECONDS
from services.first_release_schedule import forecast_first_release_item
from services.restock_signatures import learn,events

POLICY='NEXT_SIX_PRELIVE_CLEANUP_V1'
VARIANTS=('clean-full','clean-recent7')
HALF_LIFE=7*86400
BLOCK=600
STORES={}


def weighted_quantiles(values,weights,age=0):
    pairs=sorted((v-age,w) for v,w in zip(values,weights) if v>age and w>0)
    if not pairs:return None
    total=sum(w for _,w in pairs);out={}
    for name,p in [('early',.25),('middle',.5),('late',.75)]:
        cumulative=0.
        for value,weight in pairs:
            cumulative+=weight
            if cumulative>=p*total:out[name]=value;break
    return out


def event_forecaster(variant):
    def build(key,phases,**kwargs):
        asof=kwargs['asof'];high=phases['stocked_durations'];low=phases['depleted_durations']
        def estimate(values,age=0):
            if variant=='clean-full':return phase_quantiles(values,age=age)
            windows=phases['observed_bounded_stocked_windows'] if values is high else phases['observed_bounded_depleted_windows']
            if len(windows)!=len(values):raise ValueError('phase durations/closures differ')
            if any(end>asof for _,end in windows):raise ValueError('future phase label')
            return weighted_quantiles(values,[2**((end-asof)/HALF_LIFE) for _,end in windows],age)
        result=predict_events(key,phases,phase_estimator=estimate,**kwargs)
        hi=estimate(high) if high else None
        for e in result['restock_events']:
            e['early_stock_end_epoch']=e['restock_early_epoch']+hi['early']
        onset=phases.get('phase_onset')
        if phases['phase']=='HIGH' and type(onset) is int:
            active=estimate(high,age=asof-onset)
            if active:result['current_phase_early_end_epoch']=asof+active['early']
        result['adaptation_policy']={'variant':variant,'half_life_seconds':HALF_LIFE if variant=='clean-recent7' else None,
            'older_history_discarded':False,'window_uncertainty_quantiles':[.25,.75]}
        return result
    return build


class NetRates:
    """Incrementally evaluate actual ten-minute blocks; flat/rising blocks count."""
    def __init__(self,source,key,variant,asof,rows,gaps):
        self.source=source;self.key=key;self.variant=variant;self.anchor=int(os.environ.get("TORNFREN_REPLAY_CALIBRATION_START",asof))
        if self.anchor>asof:raise ValueError("calibration starts in the future")
        self.last=0;self.next_end=(rows[0][0]//BLOCK+2)*BLOCK
        self.polls=[];self.clocks=[];self.clock_times=[];self.rates=[];self.weights=[];self.ends=[]
        calibration_gaps=[(lo,hi if hi is not None and hi<=self.anchor else None) for lo,hi in gaps if lo<=self.anchor]
        self.profile=learn(rows,calibration_gaps,self.anchor)
    def update(self,rows,gaps,asof):
        if asof<self.last:raise ValueError('net-rate history must advance causally')
        previous=self.last
        with closing(sqlite3.connect(self.source.as_uri()+'?mode=ro',uri=True)) as db:
            self.polls.extend(r[0] for r in db.execute("SELECT timestamp FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp>? AND timestamp<=? ORDER BY timestamp",(previous,asof)))
            self.clocks.extend(db.execute("SELECT received_epoch,country_update_epoch,clock_status FROM country_stock_observations WHERE country=? AND received_epoch>? AND received_epoch<=? ORDER BY received_epoch,id",(self.key.split(':')[0],previous,asof)))
        self.clock_times=[r[0] for r in self.clocks]
        self.last=asof
        times=[r[0] for r in rows]
        bad=[b[0] for a,b in zip(rows,rows[1:]) if a[2]!=b[2] or b[0]<=a[0]]
        resets=[e['epoch'] for e in events(rows,gaps,self.profile)]
        for end in range(self.next_end,asof-180+1,BLOCK):
            self.next_end=end+BLOCK;start=end-BLOCK
            country_fresh=True
            for boundary in (start,end):
                c=bisect.bisect_right(self.clock_times,boundary)-1
                if c<0:country_fresh=False;break
                receipt,reported,status=self.clocks[c]
                if status!='REPORTED' or reported is None or not 0<=boundary-reported<=180 or not 0<=boundary-receipt<=180:
                    country_fresh=False;break
            if not country_fresh:continue
            a=bisect.bisect_right(times,start)-1;b=bisect.bisect_right(times,end)-1
            if a<0 or b<0 or rows[a][1]<=30:continue
            if bisect.bisect_right(bad,end)>bisect.bisect_right(bad,start):continue
            if bisect.bisect_right(resets,end)>bisect.bisect_right(resets,start):continue
            if any(lo<=end and (hi is None or hi>=start) for lo,hi in gaps):continue
            i=bisect.bisect_right(self.polls,start)-1;j=bisect.bisect_left(self.polls,end)
            if i<0 or j>=len(self.polls):continue
            stamps=self.polls[i:j+1]
            if start-stamps[0]>180 or stamps[-1]-end>180 or any(y-x>180 for x,y in zip(stamps,stamps[1:])):continue
            self.rates.append((rows[a][1]-rows[b][1])/BLOCK)
            self.weights.append(2**((end-self.anchor)/HALF_LIFE) if self.variant=='clean-recent7' else 1.)
            self.ends.append(end)
        if len(self.rates)<3:return None
        # Translate signed floating-point rates without discarding zeros/gains.
        pairs=sorted(zip(self.rates,self.weights));total=sum(w for _,w in pairs);out={}
        for name,p in [('median',.5),('upper',.75)]:
            acc=0.
            for rate,w in pairs:
                acc+=w
                if acc>=p*total:out[name]=rate;break
        out.update(samples=len(self.rates),flat_blocks=sum(r==0 for r in self.rates),
            rising_blocks=sum(r<0 for r in self.rates),last_label_epoch=self.ends[-1],
            signature_training_cutoff=self.profile['training_cutoff'])
        return out


def current_transform(source,key,variant):
    def transform(forecast,observations,gaps,asof):
        rows=[(r.epoch,r.quantity,r.source) for r in observations]
        identity=(str(Path(source).resolve()),key,variant)
        if identity not in STORES:STORES[identity]=NetRates(Path(source).resolve(),key,variant,asof,rows,gaps)
        rates=STORES[identity].update(rows,gaps,asof)
        out=deepcopy(forecast);quantity=out.get('observed_current_quantity')
        out['net_stock_rates']=rates
        if type(quantity) is not int or quantity<=30:return out
        # Preserve the observed onset, including explicitly unknown onsets.
        early_end=out.get('current_phase_early_end_epoch')
        unknown_phase=out['status'] in ('CURRENT_PHASE_UNKNOWN','CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS','INSUFFICIENT_BOUNDED_RESTOCK_HISTORY')
        if key=='uni:Xanax' or unknown_phase:
            out['current_stock_window']=None
            if rates:
                upper=max(0.,rates['upper']);flight=TRAVEL_SECONDS[key.split(':')[0]]
                lower=quantity-upper*flight
                out['current_stock_arrival_support']={'asof_epoch':asof,'arrival_epoch':asof+flight,
                    'quantity_at_issue':quantity,'loss_rate_upper':upper,
                    'expected_quantity_estimate':quantity-rates['median']*flight,
                    'lower_quantity_estimate':lower,'depletion_epoch':None,
                    'restock_onset_inferred':False,'calibration_state':'UNCALIBRATED'}
                if lower>=31:out['status']='EVENT_TIMELINE_FORECAST_AVAILABLE'
        elif out.get('current_stock_window') and type(early_end) is int:
            end=early_end
            if rates and rates['upper']>0:end=min(end,asof+math.ceil((quantity-30)/rates['upper']))
            out['current_stock_window']['uncorrected_expected_stock_end_epoch']=out['current_stock_window']['predicted_stock_below_30_epoch']
            out['current_stock_window']['predicted_stock_below_30_epoch']=end
            out['current_stock_window']['end_estimate_basis']='PHASE_Q25_AND_NET_LOSS_Q75'
        return out
    return transform


def forecast(source,key,issued,variant):
    if key not in NEXT_SIX_MODELS or variant not in VARIANTS:raise ValueError('unapproved cleanup variant')
    row=forecast_first_release_item(source,key,now=issued,flight_seconds=TRAVEL_SECONDS[key.split(':')[0]],
        model_roster=ALL_MODELS,timing_full_history=True,current_stock_leave_now=True,
        event_forecaster=event_forecaster(variant),forecast_transform=current_transform(source,key,variant))
    d=row.get('decision') or {};selected=d.get('selected_restock_event_index')
    if selected and type(d.get('estimated_arrival_epoch')) is int:
        event=next(e for e in d['forecast_events'] if e['index']==selected)
        lower=max(event['restock_late_epoch'],event['estimated_departure_start_epoch']+d['player_flight_seconds'])
        upper=min(event['estimated_latest_departure_epoch']+d['player_flight_seconds'],event['early_stock_end_epoch']-1)
        original=d['estimated_arrival_epoch']
        if lower<=upper:
            arrival=min(max(original,lower),upper);departure=arrival-d['player_flight_seconds']
            d.update(estimated_departure_epoch=departure,estimated_arrival_epoch=arrival,
                estimated_arrival_plus_grace_epoch=arrival,departure_countdown_seconds=departure-issued,
                status='ESTIMATED_DEPARTURE_WINDOW_OPEN' if departure==issued else 'WAIT_FOR_ESTIMATED_DEPARTURE')
        d['arrival_placement']={'rule':'CLAMP_NATIVE_TO_OVERLAPPING_Q25_Q75_CORE',
            'native_arrival_epoch':original,'core_start_epoch':lower,'core_end_epoch':upper,
            'core_overlaps':lower<=upper,'event_selection_changed':False}
    row.update(research_policy='CORRECTED_CHALLENGERS_FIRST_REACHABLE_V1',cleanup_policy=POLICY,
        cleanup_variant=variant,production_deployed=False,
        training_policy='ALL_AVAILABLE_CAUSAL_HISTORY_NO_ROLLING_LOOKBACK')
    return row
