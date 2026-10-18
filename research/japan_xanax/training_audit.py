"""Audit strict completed-cycle training versus clean observed half phases.

Read-only diagnostics. Half phases are not fabricated completed cycles and
are not used to change a forecast or any production assignment here.
"""
import bisect
from collections import Counter
import numpy as np
from research.japan_xanax.renewal_shadow import History, KEY, STEP, source_data
from research.japan_xanax.recent_regime import ISSUE_START, ISSUE_END, TRUTH_CUTOFF
from research.japan_xanax.forecast_gap_audit import prerequisite


class HalfPhases:
    """Only uninterrupted, same-provider, observed transitions qualify.

    A zero spell starts at an observed positive->exactly0 transition.
    A positive spell starts at an observed0->positive transition, even if
    the preceding depletion was left censored. Positive topups disqualify
    that open positive spell. Availability >=30 is separate from depletion0.
    """
    def __init__(self, crosses):
        self.crosses=crosses;self.last=None;self.start=None;self.buy_end=None
        self.initial_quantity=None;self.low=[];self.high=[];self.resets=Counter()

    def add(self,row):
        t,q,provider=row;prev=self.last
        reason=None
        if prev is None:reason='INITIAL'
        elif t<=prev[0]:reason='NONINCREASING_TIME'
        elif provider!=prev[2]:reason='PROVIDER_SWITCH'
        elif self.crosses(prev[0],t):reason='COLLECTION_GAP'
        elif q>prev[1]>0:reason='POSITIVE_TOP_UP'
        if reason:
            if self.start is not None:self.resets[reason]+=1
            self.start=self.buy_end=self.initial_quantity=None
        else:
            if prev[1]>=30>q and self.start is not None and prev[1]>0 and self.buy_end is None:
                self.buy_end=t
            if prev[1]>0 and q==0:
                if self.start is not None:
                    available=max(0,(self.buy_end or t)-self.start) if self.initial_quantity>=30 else 0
                    self.high.append(dict(start=self.start,end=t,duration=t-self.start,available=available,
                        batch=self.initial_quantity,provider=provider))
                self.start=t;self.buy_end=None;self.initial_quantity=0
            elif prev[1]==0 and q>0:
                if self.start is not None:
                    self.low.append(dict(start=self.start,end=t,duration=t-self.start,provider=provider))
                self.start=t;self.buy_end=None;self.initial_quantity=q
        self.last=row


def summarize(intervals,issued):
    completed=[r for r in intervals if r['end']<=issued]
    selected=completed[-96:]
    recent={str(hours):sum(r['end']>=issued-hours*3600 for r in completed) for hours in (6,24,72)}
    if not selected:return dict(total_completed=len(completed),last96_count=0,recent_completed=recent)
    ages=np.array([issued-r['end'] for r in selected]);w=np.exp2(-ages/(3*86400));w/=w.sum()
    return dict(total_completed=len(completed),last96_count=len(selected),recent_completed=recent,
        newest_end=selected[-1]['end'],newest_age_hours=float(ages[-1]/3600),
        oldest_age_hours=float(ages[0]/3600),weighted_mean_age_hours=float(np.dot(ages,w)/3600),
        duration_p10_p50_p90_seconds=np.quantile([r['duration'] for r in selected],[.1,.5,.9]).tolist())


def describe(history,halves,issued):
    whole=[dict(end=c.end,duration=c.end-c.zero) for c in history.cycles]
    return dict(issued=issued,whole_cycles=summarize(whole,issued),
        zero_phases=summarize(halves.low,issued),positive_phases=summarize(halves.high,issued))


def run(source,*,model_sha):
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed truth cutoff unavailable')
    h=History(crosses);halves=HalfPhases(crosses);cursor=0;issues=Counter();daily={};snapshots=[]
    reset_losses=Counter();resets=Counter();previous_cycle_ends=None;cycle_set_changes=0
    for issued in range(ISSUE_START,ISSUE_END+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];prev=h.last;reason=None
            if prev is not None:
                if row[0]<=prev[0]:reason='NONINCREASING_TIME'
                elif row[2]!=prev[2]:reason='PROVIDER_SWITCH'
                elif crosses(prev[0],row[0]):reason='COLLECTION_GAP'
                elif row[1]>prev[1]>0:reason='POSITIVE_TOP_UP'
            if reason and ISSUE_START<=row[0]<=ISSUE_END:
                resets[reason]+=1
                if h.low is not None:reset_losses[reason+':open_zero_cycle']+=1
                if h.restock is not None:reset_losses[reason+':open_positive_cycle']+=1
            h.add(row);halves.add(row);cursor+=1
        pi=bisect.bisect_right(polls,issued)-1;age=issued-polls[pi] if pi>=0 else None
        reason,info=prerequisite(h,issued,age);issues[reason]+=1
        day=(issued-ISSUE_START)//86400;daily.setdefault(str(day),Counter())[reason]+=1
        ends=tuple(c.end for c in h.cycles[-96:])
        if previous_cycle_ends is not None and ends!=previous_cycle_ends:cycle_set_changes+=1
        previous_cycle_ends=ends
        if issued in (ISSUE_START,ISSUE_START+86400,ISSUE_START+2*86400,ISSUE_END):
            snapshots.append(describe(h,halves,issued))
    return dict(item_key=KEY,model_sha=model_sha,issue_start=ISSUE_START,issue_end=ISSUE_END,truth_cutoff=cutoff,
        prerequisite_counts=dict(issues),daily_prerequisites={k:dict(v) for k,v in daily.items()},
        whole_cycle_training_set_changes=cycle_set_changes,phase_resets=dict(resets),
        reset_losses=dict(reset_losses),snapshots=snapshots,
        whole_cycle_ends_in_window=[c.end for c in h.cycles if ISSUE_START<=c.end<=ISSUE_END],
        clean_zero_half_ends_in_window=[r['end'] for r in halves.low if ISSUE_START<=r['end']<=ISSUE_END],
        clean_positive_half_ends_in_window=[r['end'] for r in halves.high if ISSUE_START<=r['end']<=ISSUE_END],
        new_forecast_model=False,accuracy_results=False,automatic_promotion=False,
        limitation='Training representation audit on reused development days. A clean half phase does not prove an entire zero/restock/zero cycle. More intervals do not prove accuracy or independence. No cross-provider joins, inferred zero events or model changes.')
