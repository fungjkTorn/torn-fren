"""Research ablation: one bounded agreeing-zero handoff inside a cycle.

Explicitly relaxed training provenance, unlike strict clean half phases.
Every depletion anchor remains an observed positive->exactly0 transition.
Cross-provider agreeing zeros are not provider-clock certification; hidden
transitions remain possible. This candidate must not automatically go live.
"""
import bisect
import time
from collections import Counter
from research.japan_xanax.renewal_shadow import History,KEY,FLIGHT,WAIT,STEP,source_data
from research.japan_xanax.zero_handoff import ZeroAnchor,poll_continuity
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END,TRUTH_CUTOFF,unique_departures
from research.japan_xanax.cadence_replay import evaluate


class SingleZeroHandoff(History):
    def __init__(self,crosses,healthy):
        super().__init__(crosses);self.healthy=healthy;self.used=False;self.crossed=False
        self.counts=Counter();self.bridged_cycle_ends=[]

    def add(self,row):
        previous=self.last;anchor=self.low;phase=self.phase_start
        n=len(self.cycles);t,q,provider=row
        agreeing=(previous is not None and provider!=previous[2] and previous[1]==q==0)
        preserve=(agreeing and not self.used and anchor is not None and phase==anchor
            and self.restock is None and 0<t-previous[0]<=60 and not self.crosses(previous[0],t)
            and self.healthy(previous[0],t))
        was_crossed=self.crossed
        super().add(row)
        if len(self.cycles)>n:
            self.counts['completed_cycles']+=1
            if was_crossed:
                self.bridged_cycle_ends.append(t);self.counts['completed_bridged_cycles']+=1
        if preserve:
            self.low=anchor;self.phase_start=phase;self.used=True;self.crossed=True
            self.counts['agreeing_zero_handoff_preserved']+=1
        elif previous is not None and (provider!=previous[2] or t<=previous[0] or self.crosses(previous[0],t) or q>previous[1]>0):
            if agreeing:self.counts['agreeing_zero_handoff_rejected']+=1
            self.used=False;self.crossed=False
        elif previous is not None and previous[1]>0 and q==0:
            # A fresh observed physical-zero anchor opens a new cycle budget.
            self.used=False;self.crossed=False


def run(source,*,model_sha,progress=None):
    began=time.monotonic()
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed truth cutoff unavailable')
    h=History(crosses);anchor=ZeroAnchor(crosses,180)
    trained=SingleZeroHandoff(crosses,poll_continuity(polls));cursor=0
    modes=('sequence_original','handoff_original','training_handoff60','leave_now_control')
    records={m:[] for m in modes};snapshots=[]
    for issued in range(ISSUE_START,ISSUE_END+WAIT+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];h.add(row);anchor.add(row);trained.add(row);cursor+=1
        i=bisect.bisect_right(polls,issued)-1;age=issued-polls[i] if i>=0 else None
        base=h.plans(issued,poll_age=age);view,borrowed=anchor.phase_view(h)
        handoff=view.plans(issued,poll_age=age) if borrowed else base
        # Match the current-phase handoff control. Only the accepted training
        # representation changes; rejected training joins may still borrow
        # the existing current-phase-only anchor without creating a tuple.
        trained_view,_=anchor.phase_view(trained)
        selected=trained_view.plans(issued,poll_age=age)
        chosen=dict(sequence_original=base['sequence_blocks_peak']['departure'],handoff_original=handoff['sequence_blocks_peak']['departure'],
            training_handoff60=selected['sequence_blocks_peak']['departure'],leave_now_control=base['leave_now_control']['departure'])
        if issued in (ISSUE_START,ISSUE_START+86400,ISSUE_START+2*86400,ISSUE_END):
            snapshots.append(dict(issued=issued,strict_completed=len(h.cycles),candidate_completed=len(trained.cycles),
                candidate_latest_end=trained.cycles[-1].end if trained.cycles else None,
                completed_bridged_cycles=sum(t<=issued for t in trained.bridged_cycle_ends)))
        if progress is not None and (issued-ISSUE_START)//STEP%96==0:
            progress(dict(issued=issued,elapsed_seconds=time.monotonic()-began))
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
        paired_vs_handoff={'training_handoff60':compare_cohorts(cohorts['handoff_original'],cohorts['training_handoff60'])},
        training_snapshots=snapshots,handoff_counts_including_warmup_and_followup=dict(trained.counts),
        bridged_cycle_ends_in_window=[t for t in trained.bridged_cycle_ends if ISSUE_START<=t<=ISSUE_END],build_seconds=time.monotonic()-began,
        development_window=True,independent_validation=False,automatic_promotion=False,calibrated_probability=False,
        arrival_target=30,depletion_stock_quantity=0,grace_seconds=10,
        limitation='RELAXED CROSS-PROVIDER TRAINING PROVENANCE: exactly one observed agreeing-zero switch <=60s per cycle, healthy global polls, no gap, no initial zero invention. Source-specific clocks and hidden restocks remain uncertain. Same inspected days; no production or running-recorder changes.')
