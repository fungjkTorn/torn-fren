"""Clock-selected replanning cohorts from immutable as-issued plans.

This simulates checking every five minutes, never actual player execution.
A changed/absent plan replaces the old plan, including when a deadline arrives.
"""
from collections import Counter
from itertools import islice


def evaluate(plans, *, cutoff, flight_seconds, score, cohorts=None, start_before=None, cohort_offset=0):
    if type(cohort_offset) is not int or cohort_offset<0:
        raise ValueError('invalid cohort offset')
    counts = Counter(starts=0,departed=0)
    days={}
    for start_index in range(cohort_offset, len(plans), 12):
        start = plans[start_index][0]
        if start_before is not None and start>start_before:
            break
        deadline = start + 28800
        counts['starts'] += 1
        day=days.setdefault((start-plans[0][0])//86400,Counter())
        day['starts']+=1
        resolved = False
        for issued, departure, source_age in islice(plans,start_index,None):
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
                cohort_grid='SOURCE_RELATIVE_HOURLY',
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
    return compare_cohorts(left,right)


def compare_cohorts(left,right):
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


def evaluate_utc(plans,**kwargs):
    offset=next((i for i,p in enumerate(plans[:12]) if p[0]%3600==0),len(plans))
    result=evaluate(plans,cohort_offset=offset,**kwargs)
    result.update(cohort_grid='UTC_HOURLY',protocol='UTC top-of-hour starts; five-minute replanning; 180s source expiry; 8h wait. Correlated historical cohorts.')
    return result


def evaluate_all_starts(plans,*,cohorts=None,**kwargs):
    """Pool all12 hourly offsets without treating them as independent trials."""
    fields=('starts','departed','SUCCESS','FAILURE','UNKNOWN','PENDING','ABSTAIN',
            'wait_seconds_sum','expired_before_departure_rechecks')
    counts=Counter();days={};offsets=[]
    for offset in range(min(12,len(plans))):
        r=evaluate(plans,cohort_offset=offset,cohorts=cohorts,**kwargs)
        counts.update({k:r.get(k,0) for k in fields})
        for day,c in enumerate(r['chronological_start_day_slices']):
            days.setdefault(day,Counter()).update({k:c.get(k,0) for k in fields})
        offsets.append([(plans[offset][0]%3600)//60,r.get('SUCCESS',0),r['scored'],
                        r.get('departed',0),r.get('starts',0),r.get('wait_seconds_sum',0)])
    if cohorts is not None:cohorts.sort(key=lambda c:c['start'])
    def summary(c):
        n=c['SUCCESS']+c['FAILURE']
        return dict(c,scored=n,success_fraction=round(c['SUCCESS']/n,4) if n else None,
                    departure_coverage=round(c['departed']/c['starts'],4) if c['starts'] else None)
    return dict(summary(counts),cohort_grid='ALL_FIVE_MINUTE_STARTS',actual_player_execution=False,
                offsets=sorted(offsets),chronological_start_day_slices=[summary(c) for _,c in sorted(days.items())],
                protocol='All twelve UTC-minute hourly offsets pooled; highly correlated, NOT independent flights or confidence certification.')
