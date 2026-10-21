"""Publication-aware Japan cadence experiment, fixed inspected development days."""
import bisect
import time
from collections import Counter
from research.japan_xanax.renewal_shadow import History,KEY,FLIGHT,WAIT,source_data
from research.japan_xanax.zero_handoff import ZeroAnchor
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END,TRUTH_CUTOFF,unique_departures
from research.japan_xanax.target_trace import trace


def evaluate(records,starts,*,cutoff,score,cohorts=None):
    """Only advice actually published and still current at departure may execute."""
    publications=[r['published'] for r in records];counts=Counter();daily={}
    for start in starts:
        day=daily.setdefault((start-starts[0])//86400,Counter());day['starts']+=1;counts['starts']+=1
        deadline=start+WAIT;chosen=None
        first=max(0,bisect.bisect_right(publications,start)-1)
        for i in range(first,len(records)):
            r=records[i];dep=r['departure'];published=r['published']
            if published>deadline:break
            stop=publications[i+1] if i+1<len(records) else min(cutoff+1,r['issued']+300)
            if dep is None or dep<max(start,published) or dep>deadline:continue
            if dep>=min(stop,r['issued']+300):continue
            if dep>cutoff:break
            if dep-r['source_cutoff']>180:
                counts['expired_source_candidates']+=1;continue
            chosen=dep;break
        if chosen is None:
            followup=min(cutoff,records[-1]['issued']+299) if records else -1
            outcome='ABSTAIN' if followup>=deadline else 'PENDING';wait=None
        else:
            outcome,_,_=score(chosen+FLIGHT);wait=chosen-start
            counts['departed']+=1;day['departed']+=1
            counts['wait_seconds_sum']+=wait;day['wait_seconds_sum']+=wait
        counts[outcome]+=1;day[outcome]+=1
        if cohorts is not None:cohorts.append(dict(start=start,outcome=outcome,wait=wait))
    def summary(c):
        known=c['SUCCESS']+c['FAILURE']
        return dict(c,scored=known,success_fraction=c['SUCCESS']/known if known else None,
            departure_coverage=c['departed']/c['starts'] if c['starts'] else None)
    return dict(summary(counts),chronological_start_day_slices=[summary(v) for _,v in sorted(daily.items())],
        actual_player_execution=False,protocol='Same 300sec visitor starts; latest actually published advice at departure; 300sec forecast TTL,180sec source TTL; max8h wait.')


def run(source,*,model_sha):
    began=time.monotonic()
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed truth cutoff unavailable')
    h=History(crosses);anchor=ZeroAnchor(crosses,180);cursor=0;calls=0
    modes=('sequence_300','handoff180_300','sequence_60','handoff180_60');records={m:[] for m in modes}
    for issued in range(ISSUE_START,ISSUE_END+WAIT+60,60):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];h.add(row);anchor.add(row);cursor+=1
        i=bisect.bisect_right(polls,issued)-1;age=issued-polls[i] if i>=0 else None
        base=h.plans(issued,poll_age=age)['sequence_blocks_peak'];calls+=1
        view,borrowed=anchor.phase_view(h)
        alt=view.plans(issued,poll_age=age)['sequence_blocks_peak'] if borrowed else base
        calls+=int(borrowed)
        for cadence in (60,300):
            if (issued-ISSUE_START)%cadence:continue
            for stem,plan in [('sequence',base),('handoff180',alt)]:
                dep=plan['departure'];dep=max(dep,issued+15) if dep is not None else None
                mode=stem+'_'+str(cadence)
                records[mode].append(dict(item_key=KEY,mode=mode,issued=issued,published=issued+15,
                    source_cutoff=issued-age if age is not None else issued-181,departure=dep,status=plan['status']))
    starts=list(range(ISSUE_START,ISSUE_END+300,300));policies={};cohorts={};traces={};distinct={}
    for mode,values in records.items():
        c=[];policies[mode]=evaluate(values,starts,cutoff=cutoff,score=evidence.score,cohorts=c)
        cohorts[mode]=c;distinct[mode]=unique_departures(c)
        traces[mode]=trace(values,asof=ISSUE_END+WAIT+299,issue_end=ISSUE_END)
    legacy={}
    for mode in ('sequence_300','handoff180_300'):
        values=[(r['issued'],r['departure'],r['issued']-r['source_cutoff']) for r in records[mode]]
        legacy[mode]=evaluate_all_starts(values,cutoff=cutoff,flight_seconds=FLIGHT,score=evidence.score,start_before=ISSUE_END)
    fingerprints={'sequence_300':(391,76,467),'handoff180_300':(518,141,659)}
    reproduced={m:tuple(legacy[m].get(k,0) for k in ('SUCCESS','FAILURE','departed'))==expected for m,expected in fingerprints.items()}
    return dict(item_key=KEY,model_sha=model_sha,issue_start=ISSUE_START,issue_end=ISSUE_END,truth_cutoff=cutoff,
        starts=len(starts),policies=policies,legacy_controls=legacy,legacy_controls_reproduced=reproduced,
        paired_vs_five_minute={m:compare_cohorts(cohorts[m.replace('_60','_300')],cohorts[m]) for m in ('sequence_60','handoff180_60')},
        departure_concentration=distinct,target_traces=traces,simulation_calls=calls,build_seconds=time.monotonic()-began,
        development_window=True,independent_validation=False,automatic_promotion=False,
        limitation='Reconstructed inspected three-day research, not a trace of the owner live journal. Forecast model/thresholds unchanged. One-minute cadence has higher compute cost. Provider clock certification and fresh validation remain required.')
