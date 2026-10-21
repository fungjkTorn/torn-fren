"""Research-only zero-agreement provider handoffs; unchanged training history."""
import bisect
import copy
from collections import Counter
from research.japan_xanax.renewal_shadow import History,KEY,FLIGHT,WAIT,STEP,source_data,rate_plan
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END,TRUTH_CUTOFF,unique_departures

CAPS={'zero_handoff60':60,'zero_handoff180':180,'zero_handoff600':600,'zero_handoff_continuous_poll':86400}


def poll_continuity(polls):
    bad_ends=[b for a,b in zip(polls,polls[1:]) if b-a>180]
    def healthy(start,end):
        a=bisect.bisect_right(polls,start)-1;b=bisect.bisect_right(polls,end)-1
        if a<0 or b<0 or start-polls[a]>180 or end-polls[b]>180:return False
        # Only polls known at the handoff may establish continuity.
        return bisect.bisect_right(bad_ends,polls[b])==bisect.bisect_right(bad_ends,polls[a])
    return healthy


class ZeroAnchor:
    def __init__(self,crosses,cap,continuous=None):
        self.crosses=crosses;self.cap=cap;self.last=None;self.anchor=None;self.counts=Counter()
        self.continuous=continuous

    def add(self,row):
        previous=self.last;t,q,source=row
        if previous is None or t<=previous[0] or self.crosses(previous[0],t):self.anchor=None
        elif source!=previous[2]:
            if (previous[1]==q==0 and t-previous[0]<=self.cap and self.anchor is not None
                    and (self.continuous is None or self.continuous(previous[0],t))):
                self.counts['zero_agreement_handoff_preserved']+=1
            else:
                self.anchor=None;self.counts['handoff_rejected']+=1
        elif previous[1]>0 and q==0:self.anchor=t
        elif q>0:self.anchor=None
        self.last=row

    def phase_view(self,history):
        # Borrow only the current zero phase. Completed training tuples stay
        # exactly those accepted by the strict baseline, never cross providers.
        if history.phase_start is not None or self.anchor is None or history.last[1]!=0:return history,False
        view=copy.copy(history);view.phase_start=self.anchor
        return view,True


def run(source,*,model_sha):
    from research.quantity_rate_cycles import QuantityRateCycles
    from deploy.scripts.v163_readonly_event_first_preview import OBS
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed truth cutoff unavailable')
    h=History(crosses);rate=QuantityRateCycles(crosses);cursor=0
    trackers={m:ZeroAnchor(crosses,c,poll_continuity(polls) if m=='zero_handoff_continuous_poll' else None) for m,c in CAPS.items()}
    modes=('sequence_blocks_peak','rate_current_quarter','leave_now_control')+tuple(CAPS)
    plans={m:[] for m in modes};rescued=Counter();switches=Counter();switch_delays=Counter()
    for issued in range(ISSUE_START,ISSUE_END+WAIT+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];prev=h.last
            if prev is not None and prev[2]!=row[2] and ISSUE_START<=row[0]<=ISSUE_END:
                tag=('zero' if prev[1]==0 else 'positive')+'_to_'+('zero' if row[1]==0 else 'positive')
                switches[tag]+=1
                dt=row[0]-prev[0];bucket='le60' if dt<=60 else 'le180' if dt<=180 else 'le600' if dt<=600 else 'gt600'
                switch_delays[tag+':'+bucket]+=1
            for tracker in trackers.values():tracker.add(row)
            h.add(row);rate.add(OBS(*row));cursor+=1
        i=bisect.bisect_right(polls,issued)-1;age=issued-polls[i] if i>=0 else None
        selected=h.plans(issued,poll_age=age);base=selected['sequence_blocks_peak']['departure']
        chosen=dict(sequence_blocks_peak=base,rate_current_quarter=rate_plan(rate,KEY,issued,age)['departure'],
            leave_now_control=selected['leave_now_control']['departure'])
        for m,tracker in trackers.items():
            view,borrowed=tracker.phase_view(h)
            chosen[m]=view.plans(issued,poll_age=age)['sequence_blocks_peak']['departure'] if borrowed else base
            if issued<=ISSUE_END and borrowed:
                rescued[m+':borrowed_phase_issues']+=1
                if chosen[m] is not None:rescued[m+':restored_forecast_issues']+=1
        for m,dep in chosen.items():plans[m].append((issued,max(dep,issued+15) if dep is not None else None,age))
    policies={};cohorts={};distinct={}
    for m,values in plans.items():
        c=[];policies[m]=evaluate_all_starts(values,cutoff=cutoff,flight_seconds=FLIGHT,score=evidence.score,start_before=ISSUE_END,cohorts=c)
        cohorts[m]=c;distinct[m]=unique_departures(c)
    base=policies['sequence_blocks_peak']
    return dict(item_key=KEY,model_sha=model_sha,issue_start=ISSUE_START,issue_end=ISSUE_END,truth_cutoff=cutoff,
        policies=policies,departure_concentration=distinct,rescued_issues=dict(rescued),
        provider_switch_types=dict(switches),provider_switch_delay_buckets=dict(switch_delays),
        handoff_diagnostics={m:dict(t.counts) for m,t in trackers.items()},
        paired_vs_sequence={m:compare_cohorts(cohorts['sequence_blocks_peak'],cohorts[m]) for m in CAPS},
        baseline_reproduced=all(base.get(k,0)==v for k,v in {'starts':864,'SUCCESS':391,'FAILURE':76,'UNKNOWN':0,'departed':467}.items()),
        exact_zero_anchor=True,cross_provider_training=False,development_window=True,
        independent_validation=False,automatic_promotion=False,
        limitation='Current zero-phase continuity borrowed only across agreeing zero provider handoffs within capped observed time and no collection gap. Global poll health is not provider-specific clock certification; fresh validation required. No website changes.')
