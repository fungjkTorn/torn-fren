"""Research-only alternating renewal trained on clean separate half phases.

No provider-crossing intervals, invented zero events, sampled paths or time
rounding. Independence of successive zero/positive durations is a modeling
assumption, not an observed whole-cycle pairing or calibrated probability.
"""
import bisect
import time
from functools import lru_cache
import numpy as np
from research.japan_xanax.renewal_shadow import History,KEY,FLIGHT,WAIT,STEP,GRACE,source_data
from research.japan_xanax.training_audit import HalfPhases
from research.japan_xanax.zero_handoff import ZeroAnchor
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END,TRUTH_CUTOFF,unique_departures
from research.japan_xanax.cadence_replay import evaluate
from research.japan_xanax.exact_renewal import choose

HORIZON=FLIGHT+WAIT
HALF_LIVES={'half72h':3*86400,'half6h':21600}


def weights(phases,half_life):
    ends=np.array([p[0] for p in phases]);w=np.exp2((ends-ends.max())/half_life)
    return w/w.sum()


def convolve(a,b,horizon):
    n=1<<(len(a)+len(b)-1).bit_length()
    return np.fft.irfft(np.fft.rfft(a,n)*np.fft.rfft(b,n),n)[:horizon+1]


@lru_cache(maxsize=16)
def occupancy(low,high,half_life,horizon=HORIZON):
    """Two arrays: availability from physical zero / a new positive phase."""
    if not low or not high or half_life not in HALF_LIVES.values() or not 0<=horizon<=HORIZON:
        raise ValueError('Invalid bounded phase configuration')
    if any(p[1]<=0 for p in low+high) or any(not 0<=p[2]<=p[1] for p in high):
        raise ValueError('Invalid observed half-phase duration')
    wl=weights(low,half_life);wh=weights(high,half_life)
    kernel=np.zeros(horizon+1);ld=np.zeros(horizon+1);hd=np.zeros(horizon+1);diff=np.zeros(horizon+2)
    for l,w in zip(low,wl):
        if l[1]<=horizon:ld[l[1]]+=w
    for h,w in zip(high,wh):
        if h[1]<=horizon:hd[h[1]]+=w
        end=h[2]-GRACE
        if end>0:diff[0]+=w;diff[min(end,horizon+1)]-=w
    # Sparse exact integer-duration products avoid FFT noise creating false
    # positive transition lags. Mass beyond horizon is not renormalized.
    for l,lw in zip(low,wl):
        for h,hw in zip(high,wh):
            d=l[1]+h[1]
            if d<=horizon:kernel[d]+=lw*hw
    lags=np.flatnonzero(kernel);prob=kernel[lags];renewal=np.zeros(horizon+1);renewal[0]=1.
    if len(lags):
        for t in range(int(lags[0]),horizon+1):
            n=bisect.bisect_right(lags,t)
            renewal[t]=np.dot(prob[:n],renewal[t-lags[:n]])
    reward_high=np.cumsum(diff[:-1]);reward_zero=convolve(ld,reward_high,horizon)
    zero=convolve(renewal,reward_zero,horizon)
    positive=reward_high+convolve(hd,zero,horizon)
    for values in (zero,positive):
        if values.min() < -1e-8 or values.max()>1+1e-8:raise ValueError('Invalid occupancy mass')
        np.clip(values,0,1,out=values);values.setflags(write=False)
    return zero,positive


def curve(history,halves,issued,age,half_life):
    if history.last is not None and history.last[0]>issued:raise ValueError('Future stock observation')
    if age is None or not 0<=age<=180 or history.crosses(issued,issued):return None,'STALE_OR_GAPPED_SOURCE'
    low=tuple((p['end'],p['duration']) for p in halves.low if p['end']<=issued)[-96:]
    high=tuple((p['end'],p['duration'],p['available']) for p in halves.high if p['end']<=issued)[-96:]
    if len(low)<16 or len(high)<16:return None,'INSUFFICIENT_CLEAN_HALF_PHASES'
    if history.phase_start is None:return None,'UNKNOWN_CURRENT_PHASE'
    if issued-history.last[0]>86400:return None,'OLD_STOCK_STATE'
    is_high=history.last[1]>0;phase_age=issued-history.phase_start;phases=high if is_high else low
    eligible=[i for i,p in enumerate(phases) if p[1]>phase_age]
    if len(eligible)<4:return None,'INSUFFICIENT_PHASE_SURVIVORS'
    w=weights(phases,half_life)[eligible];w/=w.sum()
    zero,positive=occupancy(low,high,half_life)
    delays=np.arange(0,WAIT+1,60);land=FLIGHT+delays;support=np.zeros(len(delays))
    for i,weight in zip(eligible,w):
        phase=phases[i];remaining=phase[1]-phase_age;offset=land-remaining;valid=offset>=0
        if is_high:
            available=max(0,phase[2]-phase_age) if history.last[1]>=30 else 0
            support+=weight*(land+GRACE<available)
            support[valid]+=weight*zero[offset[valid]]
        else:support[valid]+=weight*positive[offset[valid]]
    return dict(delays=delays.tolist(),support=np.clip(support,0,1).tolist(),
        zero_phases=len(low),positive_phases=len(high),latest_training_end=max(low[-1][0],high[-1][0])), 'SHADOW_ESTIMATE'


def run(source,*,model_sha,progress=None):
    began=time.monotonic()
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed truth cutoff unavailable')
    h=History(crosses);halves=HalfPhases(crosses);anchor=ZeroAnchor(crosses,180);cursor=0
    modes=('sequence_original','handoff_original','leave_now_control')+tuple(k+'_'+g for k in HALF_LIVES for g in ('peak','60'))
    records={m:[] for m in modes};statuses={k:{} for k in HALF_LIVES};occupancy.cache_clear()
    for issued in range(ISSUE_START,ISSUE_END+WAIT+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];h.add(row);halves.add(row);anchor.add(row);cursor+=1
        i=bisect.bisect_right(polls,issued)-1;age=issued-polls[i] if i>=0 else None
        baseline=h.plans(issued,poll_age=age);view,borrowed=anchor.phase_view(h)
        alt=view.plans(issued,poll_age=age) if borrowed else baseline
        chosen=dict(sequence_original=baseline['sequence_blocks_peak']['departure'],
            handoff_original=alt['sequence_blocks_peak']['departure'],leave_now_control=baseline['leave_now_control']['departure'])
        for mode,decay in HALF_LIVES.items():
            values,status=curve(view,halves,issued,age,decay)
            if issued<=ISSUE_END:statuses[mode][status]=statuses[mode].get(status,0)+1
            for gate in ('peak','60'):chosen[mode+'_'+gate]=choose(values,issued,gate)
        if progress is not None and (issued-ISSUE_START)//STEP%96==0:
            progress(dict(issued=issued,elapsed_seconds=time.monotonic()-began,cache=occupancy.cache_info()._asdict()))
        for mode,dep in chosen.items():
            records[mode].append(dict(item_key=KEY,mode=mode,issued=issued,published=issued+15,
                source_cutoff=issued-age if age is not None else issued-181,departure=max(dep,issued+15) if dep is not None else None))
    starts=list(range(ISSUE_START,ISSUE_END+STEP,STEP));policies={};cohorts={};distinct={};legacy={}
    for mode,values in records.items():
        c=[];policies[mode]=evaluate(values,starts,cutoff=cutoff,score=evidence.score,cohorts=c)
        cohorts[mode]=c;distinct[mode]=unique_departures(c)
        if mode in ('sequence_original','handoff_original'):
            legacy[mode]=evaluate_all_starts([(r['issued'],r['departure'],r['issued']-r['source_cutoff']) for r in values],cutoff=cutoff,
                flight_seconds=FLIGHT,score=evidence.score,start_before=ISSUE_END)
    expected={'sequence_original':(391,76,467),'handoff_original':(518,141,659)}
    return dict(item_key=KEY,model_sha=model_sha,issue_start=ISSUE_START,issue_end=ISSUE_END,truth_cutoff=cutoff,
        policies=policies,departure_concentration=distinct,legacy_controls=legacy,
        legacy_controls_reproduced={m:tuple(legacy[m].get(k,0) for k in ('SUCCESS','FAILURE','departed'))==v for m,v in expected.items()},
        paired_vs_handoff={m:compare_cohorts(cohorts['handoff_original'],cohorts[m]) for m in modes if m.startswith('half')},
        phase_statuses=statuses,build_seconds=time.monotonic()-began,kernel_cache=occupancy.cache_info()._asdict(),
        development_window=True,independent_validation=False,automatic_promotion=False,calibrated_probability=False,
        arrival_target=30,depletion_stock_quantity=0,grace_seconds=10,
        limitation='Clean same-provider half phases only; successive low/high durations are modeled independently. Exact integer-second marginalization of that empirical model is not calibrated real-world probability. Same inspected three days; fresh validation required. No website or running-recorder changes.')
