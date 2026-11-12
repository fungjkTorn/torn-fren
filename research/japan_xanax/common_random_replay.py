"""Common random scenario draws; unchanged models, gates and five-minute cadence."""
import bisect
from research.japan_xanax.renewal_shadow import History,KEY,FLIGHT,WAIT,STEP,source_data
from research.japan_xanax.zero_handoff import ZeroAnchor
from research.japan_xanax.recent_regime import ISSUE_START,ISSUE_END,TRUTH_CUTOFF,unique_departures
from research.japan_xanax.target_trace import trace
from research.japan_xanax.cadence_replay import evaluate


def run(source,*,model_sha):
    from research.departure_reconfirmation import evaluate_all_starts,compare_cohorts
    rows,polls,crosses,evidence,cutoff=source_data(source,now=TRUTH_CUTOFF,item_key=KEY)
    if cutoff!=TRUTH_CUTOFF:raise ValueError('Fixed truth cutoff unavailable')
    h=History(crosses);anchor=ZeroAnchor(crosses,180);cursor=0
    modes=('sequence_original','handoff_original','sequence_common_random','handoff_common_random');records={m:[] for m in modes}
    for issued in range(ISSUE_START,ISSUE_END+WAIT+STEP,STEP):
        while cursor<len(rows) and rows[cursor][0]<=issued:
            row=rows[cursor];h.add(row);anchor.add(row);cursor+=1
        i=bisect.bisect_right(polls,issued)-1;age=issued-polls[i] if i>=0 else None
        view,borrowed=anchor.phase_view(h)
        for stable in (False,True):
            base=h.plans(issued,poll_age=age,stable_scenarios=stable)['sequence_blocks_peak']
            alt=view.plans(issued,poll_age=age,stable_scenarios=stable)['sequence_blocks_peak'] if borrowed else base
            for stem,p in [('sequence',base),('handoff',alt)]:
                mode=stem+('_common_random' if stable else '_original');dep=p['departure']
                records[mode].append(dict(item_key=KEY,mode=mode,issued=issued,published=issued+15,
                    source_cutoff=issued-age if age is not None else issued-181,
                    departure=max(dep,issued+15) if dep is not None else None,status=p['status']))
    starts=list(range(ISSUE_START,ISSUE_END+STEP,STEP));policies={};cohorts={};traces={};distinct={};legacy={}
    for mode,values in records.items():
        c=[];policies[mode]=evaluate(values,starts,cutoff=cutoff,score=evidence.score,cohorts=c)
        cohorts[mode]=c;distinct[mode]=unique_departures(c)
        traces[mode]=trace(values,asof=ISSUE_END+WAIT+299,issue_end=ISSUE_END)
        if mode.endswith('_original'):
            legacy[mode]=evaluate_all_starts([(r['issued'],r['departure'],r['issued']-r['source_cutoff']) for r in values],cutoff=cutoff,flight_seconds=FLIGHT,score=evidence.score,start_before=ISSUE_END)
    expected={'sequence_original':(391,76,467),'handoff_original':(518,141,659)}
    return dict(item_key=KEY,model_sha=model_sha,issue_start=ISSUE_START,issue_end=ISSUE_END,truth_cutoff=cutoff,
        policies=policies,legacy_controls=legacy,
        legacy_controls_reproduced={m:tuple(legacy[m].get(k,0) for k in ('SUCCESS','FAILURE','departed'))==v for m,v in expected.items()},
        paired_vs_original={m:compare_cohorts(cohorts[m.replace('_common_random','_original')],cohorts[m]) for m in modes if m.endswith('_common_random')},
        departure_concentration=distinct,target_traces=traces,development_window=True,independent_validation=False,automatic_promotion=False,
        limitation='Same inspected three-day window. Phase-anchor/scenario-index seeds remove gratuitous resampling changes, not evidence-driven revisions. Original models,64 scenarios, confidence gates, publication15s and source/forecast expiry unchanged. Needs fresh validation.')
