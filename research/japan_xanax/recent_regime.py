"""Recent-regime Japan development replay on the fixed inspected three days."""
import bisect
from collections import Counter
from research.japan_xanax.renewal_shadow import History,KEY,FLIGHT,WAIT,STEP,source_data,rate_plan

ISSUE_START=1791956700
ISSUE_END=1792215600
TRUTH_CUTOFF=1792254014
CONFIGS={'recent16_6h':(16,21600),'recent32_12h':(32,43200),'recent64_24h':(64,86400)}
BASES=('sequence_blocks_peak','rate_current_quarter','leave_now_control')
MODES=BASES+tuple(CONFIGS)+tuple('fallback_'+k for k in CONFIGS)+('recent_mean_peak','recent_mean_30','recent_mean_45')


def select_curve(curve,issued,threshold=None):
    if not curve:return None
    gate=max(.15,max(curve['support'])-.03) if threshold is None else threshold
    return next((issued+d for d,s in zip(curve['delays'],curve['support']) if s>=gate),None)


def combine(primary,variants,curves,issued):
    result=dict(variants)
    for key,value in variants.items():result['fallback_'+key]=primary if primary is not None else value
    # Missing short-memory history contributes no scenario support. Do not
    # silently raise confidence by averaging only the surviving configurations.
    template=next(iter(curves.values()),None)
    mean=None
    if template:
        delays=template['delays']
        if any(c['delays']!=delays for c in curves.values()):raise ValueError('Mixed scenario grids')
        mean=dict(delays=delays,support=[sum(c['support'][i] for c in curves.values())/len(CONFIGS) for i in range(len(delays))])
    for key,threshold in [('recent_mean_peak',None),('recent_mean_30',.3),('recent_mean_45',.45)]:
        result[key]=select_curve(mean,issued,threshold)
    return result


def unique_departures(cohorts):
    departures={}
    for c in cohorts:
        if c['wait'] is None:continue
        dep=c['start']+c['wait']
        if dep in departures and departures[dep]!=c['outcome']:raise ValueError('Conflicting same-arrival outcomes')
        departures[dep]=c['outcome']
    counts=Counter(departures.values())
    return dict(distinct_departure_epochs=len(departures),distinct_outcomes=dict(counts),
        independent_samples=False,actual_flights=False)


def run(source,*,model_sha):
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed three-day truth cutoff unavailable')
    history=History(crosses);rate=QuantityRateCycles(crosses);cursor=0
    plans={m:[] for m in MODES}
    for issued in range(ISSUE_START,ISSUE_END+WAIT+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            r=rows[cursor];history.add(r);rate.add(OBS(*r));cursor+=1
        pi=bisect.bisect_right(polls,issued)-1;age=issued-polls[pi] if pi>=0 else None
        baseline=history.plans(issued,poll_age=age)
        rate_dep=rate_plan(rate,KEY,issued,age)['departure']
        variants={};curves={}
        for name,(memory,decay) in CONFIGS.items():
            diagnostics={}
            selected=history.plans(issued,poll_age=age,cycle_limit=memory,half_life_seconds=decay,diagnostics=diagnostics)
            variants[name]=selected['sequence_blocks_peak']['departure']
            if 'sequence_blocks' in diagnostics:curves[name]=diagnostics['sequence_blocks']
        chosen=combine(baseline['sequence_blocks_peak']['departure'],variants,curves,issued)
        chosen.update(sequence_blocks_peak=baseline['sequence_blocks_peak']['departure'],
            rate_current_quarter=rate_dep,leave_now_control=baseline['leave_now_control']['departure'])
        for mode,dep in chosen.items():
            plans[mode].append((issued,max(dep,issued+15) if dep is not None else None,age))
    policies={};cohorts={};distinct={}
    for mode,values in plans.items():
        c=[];policies[mode]=evaluate_all_starts(values,cutoff=cutoff,flight_seconds=FLIGHT,
            score=evidence.score,start_before=ISSUE_END,cohorts=c)
        cohorts[mode]=c;distinct[mode]=unique_departures(c)
    base=policies['sequence_blocks_peak']
    reproduced=all(base.get(k,0)==v for k,v in {'starts':864,'SUCCESS':391,'FAILURE':76,'UNKNOWN':0,'departed':467}.items())
    return dict(item_key=KEY,model_sha=model_sha,issue_start=ISSUE_START,issue_end=ISSUE_END,
        truth_cutoff=cutoff,configs=CONFIGS,policies=policies,departure_concentration=distinct,
        baseline_reproduced=reproduced,
        paired_vs_sequence={m:compare_cohorts(cohorts['sequence_blocks_peak'],c) for m,c in cohorts.items() if m not in BASES},
        arrival_target=30,depletion_stock_quantity=0,grace_seconds=10,publication_floor_seconds=15,
        development_window=True,independent_validation=False,automatic_promotion=False,
        limitation='User-directed improvement on the same inspected three days. Recency uses only completed cycles before each issue. New candidates need fresh validation. Distinct departure epochs are still not independent flights.')
