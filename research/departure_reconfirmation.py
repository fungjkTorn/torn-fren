"""Clock-selected replanning cohorts from immutable as-issued plans.

This simulates checking every five minutes, never actual player execution.
A changed/absent plan replaces the old plan, including when a deadline arrives.
"""
from collections import Counter


def evaluate(plans, *, cutoff, flight_seconds, score):
    counts = Counter()
    for start_index in range(0, len(plans), 12):
        start = plans[start_index][0]
        deadline = start + 28800
        counts['starts'] += 1
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
            counts['departed'] += 1
            counts['wait_seconds_sum'] += departure-start
            resolved = True
            break
        if not resolved:
            counts['ABSTAIN' if cutoff >= deadline+300 else 'PENDING'] += 1
    scored = counts['SUCCESS'] + counts['FAILURE']
    return dict(counts, scored=scored,
                success_fraction=round(counts['SUCCESS']/scored,4) if scored else None,
                departure_coverage=round(counts['departed']/counts['starts'],4) if counts['starts'] else None,
                actual_player_execution=False,
                protocol='Fixed hourly starts; replace plan each 300s issue; expire source at 180s; maximum wait 8h. Correlated historical cohorts.')
