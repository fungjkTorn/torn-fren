"""Clock-selected replanning cohorts from immutable as-issued plans.

This simulates checking every five minutes, never actual player execution.
A changed/absent plan replaces the old plan, including when a deadline arrives.
"""
from collections import Counter


def evaluate(plans, *, cutoff, flight_seconds, score, cohorts=None):
    counts = Counter()
    days={}
    for start_index in range(0, len(plans), 12):
        start = plans[start_index][0]
        deadline = start + 28800
        counts['starts'] += 1
        day=days.setdefault((start-plans[0][0])//86400,Counter())
        day['starts']+=1
        resolved = False
        for issued, departure, source_age in plans[start_index:]:
            if issued > deadline:
                break
            # Departure exactly at next issue must use that newer issue.
            if departure is None or not issued <= departure < issued + 300 or departure > deadline:
                continue
            if departure > cutoff:
                break
            if source_age is None or not 0 <= source_age + departure-issued <= 180:
                counts['expired_before_departure_rechecks'] += 1
                continue
            outcome, _, _ = score(departure+flight_seconds)
            counts[outcome] += 1
            day[outcome]+=1
            day['departed']+=1
            day['wait_seconds_sum']+=departure-start
            counts['departed'] += 1
            counts['wait_seconds_sum'] += departure-start
            if cohorts is not None:
                cohorts.append(dict(start=start,outcome=outcome,wait=departure-start))
            resolved = True
            break
        if not resolved:
            outcome='ABSTAIN' if cutoff >= deadline+300 else 'PENDING'
            counts[outcome] += 1
            day[outcome]+=1
            if cohorts is not None:
                cohorts.append(dict(start=start,outcome=outcome,wait=None))
    scored = counts['SUCCESS'] + counts['FAILURE']
    return dict(counts, scored=scored,
                success_fraction=round(counts['SUCCESS']/scored,4) if scored else None,
                departure_coverage=round(counts['departed']/counts['starts'],4) if counts['starts'] else None,
                actual_player_execution=False,
                chronological_start_day_slices=[dict(c,
                    scored=c['SUCCESS']+c['FAILURE'],
                    success_fraction=round(c['SUCCESS']/(c['SUCCESS']+c['FAILURE']),4)
                        if c['SUCCESS']+c['FAILURE'] else None,
                    departure_coverage=round(c['departed']/c['starts'],4))
                    for _,c in sorted(days.items())],
                protocol='Fixed hourly starts; replace plan each 300s issue; expire source at 180s; maximum wait 8h. Correlated historical cohorts.')


def compare(base,challenger,**kwargs):
    """Same fixed starts; keep unmatched outcomes visible, never drop abstentions."""
    left=[];right=[]
    evaluate(base,cohorts=left,**kwargs)
    evaluate(challenger,cohorts=right,**kwargs)
    if [c['start'] for c in left]!=[c['start'] for c in right]:
        raise ValueError('replanning comparisons require identical starts')
    counts=Counter()
    for a,b in zip(left,right):
        counts['starts']+=1
        counts[a['outcome']+'__'+b['outcome']]+=1
        if a['outcome'] in ('SUCCESS','FAILURE') and b['outcome'] in ('SUCCESS','FAILURE'):
            counts['matched_resolved']+=1
            counts['challenger_only_success']+=a['outcome']=='FAILURE' and b['outcome']=='SUCCESS'
            counts['baseline_only_success']+=a['outcome']=='SUCCESS' and b['outcome']=='FAILURE'
            counts['challenger_minus_baseline_wait_seconds_sum']+=b['wait']-a['wait']
    return dict(counts)
