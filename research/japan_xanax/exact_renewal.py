"""Exact integer-second empirical renewal occupancy; research only.

Marginalizes all iid completed-cycle paths, rather than sampling 64 paths.
The observed current phase is still required. No cross-provider training,
phase invention, retained deadlines, calibrated probability or promotion.
"""
import bisect
import time
from functools import lru_cache
import numpy as np
from research.japan_xanax.renewal_shadow import History, KEY, FLIGHT, WAIT, STEP, GRACE, source_data
from research.japan_xanax.zero_handoff import ZeroAnchor
from research.japan_xanax.recent_regime import ISSUE_START, ISSUE_END, TRUTH_CUTOFF, unique_departures
from research.japan_xanax.cadence_replay import evaluate

HORIZON = FLIGHT + WAIT
MODES = ('sequence_original', 'handoff_original', 'paired_mc_peak', 'paired_mc_60',
         'renewal_exact_peak', 'renewal_exact_60', 'leave_now_control')


def weights_for(cycles):
    ends = np.array([c.end for c in cycles])
    weights = np.exp2((ends - ends.max()) / (3 * 86400))
    return weights / weights.sum()


@lru_cache(maxsize=24)
def renewal_occupancy(cycles, horizon=HORIZON):
    """Expected buying availability t seconds after a known physical zero.

    R[0]=1; R[t]=sum_d P(cycle duration=d)*R[t-d]. Occupancy is
    the convolution of R and the single-cycle availability reward. Joint
    low/high/availability duration tuples are preserved inside each cycle.
    Integer-second event times avoid accumulating time-grid rounding bias.
    """
    if not cycles or not 0 <= horizon <= HORIZON:
        raise ValueError('Bounded nonempty renewal history required')
    if any(not c.zero < c.restock < c.end or not 0 <= c.available <= c.end-c.restock for c in cycles):
        raise ValueError('Invalid true-zero cycle')
    weights = weights_for(cycles)
    duration = np.array([c.end-c.zero for c in cycles], dtype=int)
    kernel = np.bincount(duration, weights=weights)
    lags = np.flatnonzero(kernel)
    lags = lags[lags <= horizon]
    probabilities = kernel[lags]
    renewal = np.zeros(horizon+1); renewal[0] = 1.
    if len(lags):
        for t in range(int(lags[0]), horizon+1):
            n = bisect.bisect_right(lags, t)
            renewal[t] = np.dot(probabilities[:n], renewal[t-lags[:n]])
    diff = np.zeros(horizon+2)
    for c, weight in zip(cycles, weights):
        lo = c.restock-c.zero
        # Strict end: t+10 < restock+available, exactly as MC baseline.
        hi = lo+c.available-GRACE
        if lo < hi and lo <= horizon:
            diff[lo] += weight; diff[min(hi, horizon+1)] -= weight
    reward = np.cumsum(diff[:-1])
    size = 1 << (2*horizon+1).bit_length()
    occupancy = np.fft.irfft(np.fft.rfft(renewal, size)*np.fft.rfft(reward, size), size)[:horizon+1]
    if occupancy.min() < -1e-8 or occupancy.max() > 1+1e-8:
        raise ValueError('Invalid renewal occupancy mass')
    occupancy = np.clip(occupancy, 0, 1)
    occupancy.setflags(write=False)
    return occupancy


def curve(history, issued, poll_age):
    if history.last is not None and history.last[0] > issued:
        raise ValueError('Future observation')
    if poll_age is None or not 0 <= poll_age <= 180 or history.crosses(issued, issued):
        return None, 'STALE_OR_GAPPED_SOURCE'
    cycles = tuple(c for c in history.cycles if c.end <= issued)[-96:]
    if len(cycles) < 16:
        return None, 'INSUFFICIENT_COMPLETED_CYCLES'
    if history.phase_start is None:
        return None, 'UNKNOWN_CURRENT_PHASE'
    if issued-history.last[0] > 86400:
        return None, 'OLD_STOCK_STATE'
    high = history.last[1] > 0; age = issued-history.phase_start
    eligible = [i for i,c in enumerate(cycles) if (c.end-c.restock if high else c.restock-c.zero) > age]
    if len(eligible) < 4:
        return None, 'INSUFFICIENT_PHASE_SURVIVORS'
    weights = weights_for(cycles)[eligible]; weights /= weights.sum()
    delays = np.arange(0, WAIT+1, 60); land = FLIGHT+delays
    support = np.zeros(len(delays)); future = renewal_occupancy(cycles)
    for i, weight in zip(eligible, weights):
        c = cycles[i]
        if high:
            available = max(0, c.available-age) if history.last[1] >= 30 else 0
            zero = c.end-c.restock-age
            support += weight*((land >= 0) & (land+GRACE < available))
        else:
            restock = c.restock-c.zero-age
            zero = restock+c.end-c.restock
            support += weight*((land >= restock) & (land+GRACE < restock+c.available))
        offsets = land-zero; valid = offsets >= 0
        support[valid] += weight*future[offsets[valid]]
    if np.max(support) > 1+1e-8:
        raise ValueError('Overlapping occupancy mass')
    return dict(delays=delays.tolist(), support=np.clip(support, 0, 1).tolist(),
                completed_cycles=len(cycles), latest_training_cycle_end=cycles[-1].end), 'SHADOW_ESTIMATE'


def choose(values, issued, gate):
    if values is None:
        return None
    threshold = max(.15, max(values['support'])-.03) if gate == 'peak' else .6
    # Numerical FFT noise must not choose an earlier mathematically zero bin.
    return next((issued+d for d,s in zip(values['delays'], values['support']) if s+1e-12 >= threshold), None)


def run(source, *, model_sha, progress=None):
    began = time.monotonic()
    from research.departure_reconfirmation import evaluate_all_starts, compare_cohorts
    rows, polls, crosses, evidence, cutoff = source_data(source, now=TRUTH_CUTOFF, item_key=KEY)
    if cutoff != TRUTH_CUTOFF:
        raise ValueError('Fixed truth cutoff unavailable')
    h = History(crosses); anchor = ZeroAnchor(crosses, 180); cursor = 0
    records = {m: [] for m in MODES}; statuses = {}; renewal_occupancy.cache_clear()
    for issued in range(ISSUE_START, ISSUE_END+WAIT+STEP, STEP):
        while cursor < len(rows) and rows[cursor][0] <= issued:
            row = rows[cursor]; h.add(row); anchor.add(row); cursor += 1
        i = bisect.bisect_right(polls, issued)-1
        age = issued-polls[i] if i >= 0 else None
        base = h.plans(issued, poll_age=age)
        view, borrowed = anchor.phase_view(h)
        alt = view.plans(issued, poll_age=age) if borrowed else base
        values, status = curve(view, issued, age)
        if issued <= ISSUE_END:
            statuses[status] = statuses.get(status, 0)+1
        chosen = dict(sequence_original=base['sequence_blocks_peak']['departure'],
            handoff_original=alt['sequence_blocks_peak']['departure'],
            paired_mc_peak=alt['paired_recent_peak']['departure'], paired_mc_60=alt['paired_recent_60']['departure'],
            renewal_exact_peak=choose(values, issued, 'peak'), renewal_exact_60=choose(values, issued, '60'),
            leave_now_control=base['leave_now_control']['departure'])
        if progress is not None and (issued-ISSUE_START)//STEP % 96 == 0:
            progress(dict(issued=issued, elapsed_seconds=time.monotonic()-began, kernel_cache=renewal_occupancy.cache_info()._asdict()))
        for mode, dep in chosen.items():
            records[mode].append(dict(item_key=KEY, mode=mode, issued=issued, published=issued+15,
                source_cutoff=issued-age if age is not None else issued-181,
                departure=max(dep, issued+15) if dep is not None else None))
    starts = list(range(ISSUE_START, ISSUE_END+STEP, STEP)); policies = {}; cohorts = {}; distinct = {}; legacy = {}
    for mode, values in records.items():
        c = []; policies[mode] = evaluate(values, starts, cutoff=cutoff, score=evidence.score, cohorts=c)
        cohorts[mode] = c; distinct[mode] = unique_departures(c)
        if mode in ('sequence_original', 'handoff_original'):
            legacy[mode] = evaluate_all_starts([(r['issued'], r['departure'], r['issued']-r['source_cutoff']) for r in values],
                cutoff=cutoff, flight_seconds=FLIGHT, score=evidence.score, start_before=ISSUE_END)
    fingerprints = {'sequence_original': (391,76,467), 'handoff_original': (518,141,659)}
    return dict(item_key=KEY, model_sha=model_sha, issue_start=ISSUE_START, issue_end=ISSUE_END, truth_cutoff=cutoff,
        policies=policies, departure_concentration=distinct, legacy_controls=legacy,
        legacy_controls_reproduced={m:tuple(legacy[m].get(k,0) for k in ('SUCCESS','FAILURE','departed')) == v for m,v in fingerprints.items()},
        paired_vs_handoff={m:compare_cohorts(cohorts['handoff_original'], cohorts[m]) for m in ('renewal_exact_peak','renewal_exact_60')},
        phase_statuses=statuses, build_seconds=time.monotonic()-began, kernel_cache=renewal_occupancy.cache_info()._asdict(),
        development_window=True, independent_validation=False, automatic_promotion=False, calibrated_probability=False,
        arrival_target=30, depletion_stock_quantity=0, grace_seconds=10,
        limitation='Exact under empirical iid completed-cycle model, not exact real-world probability. Same inspected three days; no synthetic current phase or cross-provider training. Integer-second renewal recurrence and FFT convolution; no seeded-path selection. Needs fresh validation.')
