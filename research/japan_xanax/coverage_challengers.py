"""Predeclared Japan-only coverage challengers; causal historical research only."""
import bisect
from research.japan_xanax.renewal_shadow import (History,KEY,FLIGHT,WAIT,STEP,source_data,rate_plan,MODES)

NEW_MODES=('fallback_quantity_peak','fallback_rate_seq25','fallback_rate_agreement25',
           'fallback_rate_agreement40','sequence_slack10','sequence_gate30','sequence_gate45')


def support_at(curve,delay):
    """Conservative adjacent-grid support, never extrapolate a missing horizon."""
    if not curve or not 0<=delay<=WAIT:return 0.
    delays=curve['delays'];values=curve['support']
    i=bisect.bisect_left(delays,delay)
    if i>=len(delays):return 0.
    if delays[i]==delay:return values[i]
    return min(values[i-1],values[i]) if i else 0.


def combine(plans,curves,issued):
    """All routing decisions use issued forecasts, never arrival outcomes."""
    primary=plans['sequence_blocks_peak']['departure'];rate=plans['rate_current_quarter']['departure']
    quantity=plans['quantity_blocks_peak']['departure']
    valid=lambda dep: type(dep) is int and issued<=dep<=issued+WAIT
    primary=primary if valid(primary) else None
    rate=rate if valid(rate) else None
    quantity=quantity if valid(quantity) else None
    seq=support_at(curves.get('sequence_blocks'),rate-issued) if rate is not None else 0.
    pair=support_at(curves.get('paired_recent'),rate-issued) if rate is not None else 0.
    result={'fallback_quantity_peak':primary if primary is not None else quantity}
    for name,accepted in [('fallback_rate_seq25',seq>=.25),
            ('fallback_rate_agreement25',min(seq,pair)>=.25),
            ('fallback_rate_agreement40',min(seq,pair)>=.4)]:
        result[name]=primary if primary is not None else rate if accepted else None
    curve=curves.get('sequence_blocks')
    for name,threshold in [('sequence_slack10',None),('sequence_gate30',.3),('sequence_gate45',.45)]:
        dep=None
        if curve:
            gate=max(.15,max(curve['support'])-.10) if threshold is None else threshold
            for delay,support in zip(curve['delays'],curve['support']):
                if support>=gate:dep=issued+delay;break
        result[name]=dep
    return result


def run(source,*,model_sha,issue_end,days=6):
    if days!=6 or type(issue_end) is not int or issue_end%300:raise ValueError('Fixed aligned six-day comparison required')
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,item_key=KEY)
    if issue_end+WAIT+FLIGHT+490>cutoff:raise ValueError('Incomplete arrival truth')
    start=issue_end-days*86400+STEP;split=start+3*86400
    history=History(crosses);rate=QuantityRateCycles(crosses);cursor=0
    modes=MODES+NEW_MODES;plans={m:[] for m in modes}
    for issued in range(start,issue_end+WAIT+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];history.add(row);rate.add(OBS(*row));cursor+=1
        i=bisect.bisect_right(polls,issued)-1;age=issued-polls[i] if i>=0 else None
        curves={};selected=history.plans(issued,poll_age=age,diagnostics=curves)
        selected['rate_current_quarter']=rate_plan(rate,KEY,issued,age)
        derived=combine(selected,curves,issued)
        for mode in modes:
            dep=derived[mode] if mode in derived else selected[mode]['departure']
            dep=max(dep,issued+15) if dep is not None else None
            plans[mode].append((issued,dep,age))
    reports={}
    for label,lo,hi in [('earlier_three_days',start,split-STEP),('reserved_later_three_days',split,issue_end),('all_six_days',start,issue_end)]:
        results={};cohorts={}
        for mode,values in plans.items():
            c=[]
            results[mode]=evaluate_all_starts([v for v in values if v[0]>=lo],cutoff=cutoff,
                flight_seconds=FLIGHT,score=evidence.score,start_before=hi,cohorts=c)
            cohorts[mode]=c
        reports[label]=dict(issue_start=lo,issue_end=hi,policies=results,
            paired_vs_sequence={m:compare_cohorts(cohorts['sequence_blocks_peak'],cohorts[m]) for m in NEW_MODES},
            paired_vs_rate={m:compare_cohorts(cohorts['rate_current_quarter'],cohorts[m]) for m in NEW_MODES})
    return dict(item_key=KEY,model_sha=model_sha,truth_cutoff=cutoff,issue_start=start,issue_end=issue_end,
        split_epoch=split,days=days,arrival_target=30,grace_seconds=10,depletion_stock_quantity=0,
        publication_floor_seconds=15,reports=reports,automatic_promotion=False,
        historical_only=True,calibrated_probability=False,
        limitation='Fixed challengers on an older six-day window preceding the inspected renewal comparison. Later three days reserved before this run, not a pristine project-wide holdout. Correlated starts, causal replanning, no live deployment.')
