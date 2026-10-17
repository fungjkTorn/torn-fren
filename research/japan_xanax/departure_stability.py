"""Recheck retained Japan departure targets; same recent development window."""
import bisect
from collections import Counter
from research.japan_xanax.renewal_shadow import History,KEY,FLIGHT,WAIT,STEP,source_data,rate_plan
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END,TRUTH_CUTOFF,unique_departures
from research.japan_xanax.coverage_challengers import support_at

GATES={'retained20':.2,'retained30':.3,'retained40':.4}


class RecheckedTarget:
    def __init__(self,gate):
        self.gate=gate;self.target=None;self.counts=Counter()

    def choose(self,issued,primary,curve,age):
        if age is None or not 0<=age+15<=180 or not curve:
            self.target=None;self.counts['unavailable']+=1;return None
        # An already expired deadline is never republished as a fresh target.
        if self.target is not None and issued+15<=self.target<=issued+WAIT:
            if support_at(curve,self.target-issued)>=self.gate:
                self.counts['retained_after_current_support_recheck']+=1
                return self.target
            self.counts['rejected_by_current_support']+=1
        elif self.target is not None:self.counts['expired_or_outside_horizon']+=1
        self.target=primary if type(primary) is int and issued<=primary<=issued+WAIT else None
        self.counts['new_model_target' if self.target is not None else 'model_abstention']+=1
        return self.target


def run(source,*,model_sha):
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed truth cutoff unavailable')
    trackers={m:RecheckedTarget(g) for m,g in GATES.items()}
    modes=('sequence_blocks_peak','rate_current_quarter','leave_now_control')+tuple(GATES)
    plans={m:[] for m in modes};raw=Counter();previous=None
    history=History(crosses);rate=QuantityRateCycles(crosses);cursor=0
    for issued in range(ISSUE_START,ISSUE_END+WAIT+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];history.add(row);rate.add(OBS(*row));cursor+=1
        pi=bisect.bisect_right(polls,issued)-1;age=issued-polls[pi] if pi>=0 else None
        curves={};selected=history.plans(issued,poll_age=age,diagnostics=curves)
        primary=selected['sequence_blocks_peak']['departure']
        chosen=dict(sequence_blocks_peak=primary,rate_current_quarter=rate_plan(rate,KEY,issued,age)['departure'],
            leave_now_control=selected['leave_now_control']['departure'])
        for m,tracker in trackers.items():chosen[m]=tracker.choose(issued,primary,curves.get('sequence_blocks'),age)
        if issued<=ISSUE_END:
            raw['issues']+=1;raw['no_primary_forecast' if primary is None else 'primary_forecast']+=1
            if primary is not None:
                raw['primary_within_next_five_minutes' if primary<issued+300 else 'primary_more_than_five_minutes_away']+=1
            if primary is not None and previous is not None:
                raw['target_later_than_previous' if primary>previous else 'target_earlier_than_previous' if primary<previous else 'same_target']+=1
        previous=primary
        for m,dep in chosen.items():plans[m].append((issued,max(dep,issued+15) if dep is not None else None,age))
    policies={};cohorts={};concentration={}
    for m,values in plans.items():
        c=[];policies[m]=evaluate_all_starts(values,cutoff=cutoff,flight_seconds=FLIGHT,score=evidence.score,start_before=ISSUE_END,cohorts=c)
        cohorts[m]=c;concentration[m]=unique_departures(c)
    base=policies['sequence_blocks_peak']
    return dict(item_key=KEY,model_sha=model_sha,issue_start=ISSUE_START,issue_end=ISSUE_END,truth_cutoff=cutoff,
        policies=policies,departure_concentration=concentration,primary_issue_diagnostics=dict(raw),
        retention_diagnostics={m:dict(t.counts) for m,t in trackers.items()},
        paired_vs_sequence={m:compare_cohorts(cohorts['sequence_blocks_peak'],cohorts[m]) for m in GATES},
        baseline_reproduced=all(base.get(k,0)==v for k,v in {'starts':864,'SUCCESS':391,'FAILURE':76,'UNKNOWN':0,'departed':467}.items()),
        development_window=True,independent_validation=False,automatic_promotion=False,
        arrival_target=30,depletion_stock_quantity=0,grace_seconds=10,publication_floor_seconds=15,
        limitation='Retained targets are rechecked against CURRENT uncalibrated scenario support and freshness, never blindly committed. Same inspected three-day development window; needs fresh validation before release.')
