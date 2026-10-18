"""Execution-trained timing correction; research only, no model promotion.

Train offsets ONLY on past, matured, actually eligible near-term proposals.
Never learn from a floating target that the execution policy would not reach.
Separate >=30 availability labels from the unchanged physical-zero tracker.
"""
import bisect
import heapq
import math
from collections import Counter,defaultdict,deque

from research.japan_xanax.renewal_shadow import History,source_data,rate_plan,STEP,WAIT
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END
from research.matched_champion_audit import ISSUES,summarize

OFFSETS=(-1200,-900,-600,-300,0,300,600)
MIN_KNOWN=8


def bounded_departure(issued,departure,offset=0):
    if departure is None:return None
    if type(departure) is not int:raise ValueError('Integer departure required')
    dep=max(issued+15,departure+offset)
    return dep if dep<=issued+WAIT else None


class ExecutionCalibration:
    def __init__(self,flight):
        self.flight=flight;self.pending=[];self.serial=0;self.seen=set();self.last=None
        self.history=defaultdict(lambda:deque(maxlen=64));self.counts=Counter()

    def advance(self,issued,score):
        if self.last is not None and issued<=self.last:raise ValueError('Nonincreasing calibration clock')
        self.last=issued
        while self.pending and self.pending[0][0]<=issued:
            maturity,_,phase,offset,dep=self.pending[0]
            heapq.heappop(self.pending)
            if dep+self.flight+190>issued:raise ValueError('Unmatured outcome requested')
            outcome,_,evidence=score(dep+self.flight)
            if outcome=='PENDING':raise ValueError('Mature arrival still pending')
            if evidence is not None and evidence.get('post_poll',0)>issued:raise ValueError('Future poll leaked into training')
            self.counts['matured_'+outcome]+=1
            if outcome in ('SUCCESS','FAILURE'):
                self.history[(phase,offset)].append((maturity,int(outcome=='SUCCESS')))

    def observe(self,issued,choices,phase,poll_age):
        if self.last!=issued:raise ValueError('Advance before enqueueing current plans')
        for offset,dep in choices.items():
            if dep is None or not issued<=dep<issued+STEP:continue
            if poll_age is None or not 0<=poll_age+dep-issued<=180:continue
            # One decision per five-minute arrival bucket per expert; repeated
            # overlapping cohorts must not inflate selector training evidence.
            key=(phase,offset,dep//STEP)
            if key in self.seen:continue
            self.seen.add(key);self.serial+=1
            if len(self.seen)>60000:raise ValueError('Calibration evidence cap exceeded')
            heapq.heappush(self.pending,(dep+self.flight+190,self.serial,phase,offset,dep))

    def estimates(self,issued,phase):
        result={}
        for offset in OFFSETS:
            rows=[(t,y) for t,y in self.history[(phase,offset)] if issued-t<=7*86400]
            if len(rows)<MIN_KNOWN:continue
            weights=[math.exp2(-(issued-t)/21600) for t,y in rows]
            value=(sum(w*y for w,(_,y) in zip(weights,rows))+2)/(sum(weights)+4)
            result[offset]=dict(raw_score=value,known=len(rows),latest_maturity=max(t for t,y in rows))
        return result

    def choose(self,issued,choices,phase,*,gated):
        estimates=self.estimates(issued,phase)
        eligible=[o for o,d in choices.items() if d is not None and issued<=d<issued+STEP
                  and o in estimates and estimates[o]['raw_score']>=.65]
        if eligible:
            winner=max(eligible,key=lambda o:(estimates[o]['raw_score'],-choices[o],-abs(o)))
            return choices[winner],winner
        return (None,None) if gated else (choices[0],0)


def fixed_records(plans,starts,cutoff,flight,score):
    from research.departure_reconfirmation import evaluate
    result=[]
    for mode,values in plans.items():
        index={v[0]:i for i,v in enumerate(values)}
        for start in starts:
            c=[];evaluate(values[index[start]:],cutoff=cutoff,flight_seconds=flight,score=score,
                          start_before=start,cohorts=c)
            if len(c)!=1:raise ValueError('Matched cohort identity changed')
            r=c[0];result.append(dict(issued=start,mode=mode,
                departure=start+r['wait'] if r['wait'] is not None else None,
                outcome=r['outcome'],status='HISTORICAL_REPLANNED'))
    return result


def concentration(records):
    result={}
    for mode in sorted({r['mode'] for r in records}):
        unique={}
        for r in records:
            if r['mode']!=mode or r['departure'] is None:continue
            dep=r['departure']
            if dep in unique and unique[dep]!=r['outcome']:raise ValueError('Conflicting identical arrival outcomes')
            unique[dep]=r['outcome']
        result[mode]=dict(distinct_departures=len(unique),outcomes=dict(Counter(unique.values())))
    return result


def run(source,*,model_sha):
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    from research.plushie_champions.common import TRAVEL_SECONDS
    from research.departure_reconfirmation import evaluate_all_starts
    result={}
    for key in ('can:Xanax','jap:Xanax'):
        rows,polls,crosses,evidence,cutoff=source_data(source,item_key=key)
        flight=TRAVEL_SECONDS[key.split(':',1)[0]]
        if cutoff<ISSUES[-1]+WAIT+flight+190:raise ValueError('Immature fixed study')
        rate=QuantityRateCycles(crosses);history=History(crosses);cursor=0
        calibration=ExecutionCalibration(flight);plans={};selected=Counter();forecast_diagnostics=[]
        warmup=ISSUE_START-7*86400
        for issued in range(warmup,ISSUES[-1]+WAIT+STEP,STEP):
            while cursor<len(rows) and rows[cursor][0]<=issued:
                row=rows[cursor];rate.add(OBS(*row));history.add(row);cursor+=1
            calibration.advance(issued,evidence.score)
            pi=bisect.bisect_right(polls,issued)-1;age=issued-polls[pi] if pi>=0 else None
            base=rate_plan(rate,key,issued,age)['departure']
            choices={offset:bounded_departure(issued,base,offset) for offset in OFFSETS}
            phase='ZERO' if rate.last is not None and rate.last.quantity==0 else 'POSITIVE'
            calibration.observe(issued,choices,phase,age)
            fallback,fo=calibration.choose(issued,choices,phase,gated=False)
            gated,go=calibration.choose(issued,choices,phase,gated=True)
            if issued<ISSUE_START:continue
            current={('rate_control' if o==0 else 'offset_%+d'%o):d for o,d in choices.items()}
            current.update(adaptive_fallback=fallback,adaptive_gated=gated,
                           leave_now_control=issued+15 if age is not None and age+15<=180 else None)
            sequence=history.plans(issued,poll_age=age,flight_seconds=flight)
            current['sequence_control']=bounded_departure(issued,sequence['sequence_blocks_peak']['departure'])
            for mode,dep in current.items():plans.setdefault(mode,[]).append((issued,dep,age))
            selected['fallback_'+str(fo)]+=1;selected['gated_'+str(go)]+=1
            if issued in ISSUES:
                forecast=rate.forecast(key,asof=issued)
                forecast_diagnostics.append(dict(issued=issued,phase=phase,
                    observed_quantity=rate.last.quantity if rate.last is not None else None,
                    estimated_departure=base,
                    forecast_events=forecast.get('restock_events'),
                    calibration=calibration.estimates(issued,phase)))
        prior={};prior_records=[]
        for mode,values in plans.items():
            c=[];prior[mode]=evaluate_all_starts(values,cutoff=cutoff,flight_seconds=flight,
                score=evidence.score,start_before=ISSUE_END,cohorts=c)
            prior_records.extend(dict(issued=r['start'],mode=mode,outcome=r['outcome'],
                departure=r['start']+r['wait'] if r['wait'] is not None else None) for r in c)
        failed=fixed_records(plans,ISSUES,cutoff,flight,evidence.score)
        result[key]=dict(truth_cutoff=cutoff,earlier_three_day=prior,
            earlier_distinct=concentration(prior_records),failed_nine=summarize(failed),
            failed_nine_distinct=concentration(failed),failed_nine_records=failed,
            calibration_counts=dict(calibration.counts),selection_counts=dict(selected),
            forecast_diagnostics=forecast_diagnostics)
    return dict(model_sha=model_sha,items=result,offsets_seconds=OFFSETS,
        minimum_known_training=MIN_KNOWN,training_half_life_seconds=21600,
        issue_start=ISSUE_START,issue_end=ISSUE_END,failed_issues=ISSUES,
        training='ONLY_MATURED_EXECUTABLE_PROPOSALS_BUCKET_DEDUPLICATED',
        physical_depletion_quantity=0,arrival_target=30,grace_seconds=10,
        automatic_promotion=False,independent_validation=False,
        limitation='Inspected development windows. Distinct epochs still not independent flights. Raw smoothed calibration scores are not verified probabilities. Fixed offset arms are all reported, never posthoc assigned to live items.')
