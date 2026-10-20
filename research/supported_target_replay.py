"""Fixed four-item historical experiment for current-supported retention.

Serial native inference is shared across policies and visitor cohorts. Future
arrival truth is scored only AFTER every scheduling decision has been made.
This does not start a VM canary, change routing, or select a winning model.
"""
import argparse
import bisect
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time

from research.supported_target_retention import Band, Policy, KEYS, MODES, WAIT, STEP


def schedule(ticks, starts):
    """Replay frozen as-issued curves without access to outcome labels."""
    starts = tuple(starts)
    if not starts or len(set(starts)) != len(starts) or any(s % STEP for s in starts):
        raise ValueError('Unique grid-aligned visitor starts required')
    active = []
    records = []
    previous = None
    for tick in ticks:
        band = Band(tick['issued'], tick['native'], tuple(tuple(p) for p in tick['points']))
        q = band.issued
        if previous is not None and q != previous + STEP:
            raise ValueError('Missing or nonincreasing issue; do not bridge unknown advice')
        previous = q
        if q in starts:
            active.extend(Policy(q, mode) for mode in MODES)
        remain = []
        for p in active:
            if q > p.deadline:
                records.append(dict(issued=p.start, mode=p.mode, departure=None,
                                    status='EIGHT_HOUR_ABSTENTION'))
                continue
            dep = p.update(band, tick['age'])
            # Retained future targets must be reconfirmed on every issue.
            if dep is not None and q <= dep < q + STEP and dep <= p.deadline and \
                    tick['age'] is not None and 0 <= tick['age'] + dep - q <= 180:
                records.append(dict(issued=p.start, mode=p.mode, departure=dep,
                                    status='HISTORICAL_REPLANNED'))
            else:
                remain.append(p)
        active = remain
    if active or len(records) != len(starts)*len(MODES):
        raise ValueError('Incomplete cohort horizon; never relabel missing ticks as abstentions')
    return sorted(records, key=lambda r: (r['mode'], r['issued']))


def score_records(records, evidence, flight):
    output = []
    for r in records:
        outcome = evidence.score(r['departure'] + flight)[0] if r['departure'] is not None else 'ABSTAIN'
        if outcome == 'PENDING':
            raise ValueError('Immature arrival evidence')
        output.append(dict(r, outcome=outcome))
    return output


CHILD = '''import json,sys,types
from dataclasses import asdict
provider=types.ModuleType('services.yata_api')
def forbidden(*a,**k):raise RuntimeError('HTTP forbidden in causal retention inference')
provider.get_country_stock=forbidden
sys.modules['services.yata_api']=provider
from research.supported_target_retention import native_band
print(json.dumps(asdict(native_band(sys.argv[1],sys.argv[2],int(sys.argv[3]),all_supported=len(sys.argv)>4 and sys.argv[4]=='1')))))
'''


def collect_item(source, out, key, starts, timeout, *, all_supported=False):
    from research.causal_replay_slice import CausalReplaySlice
    from research.japan_xanax.renewal_shadow import source_data
    from research.plushie_champions.common import TRAVEL_SECONDS
    from research.matched_champion_audit import summarize
    from research.execution_offset_study import concentration
    rows, polls, crosses, evidence, cutoff = source_data(source, item_key=key)
    flight = TRAVEL_SECONDS[key.split(':', 1)[0]]
    stop = max(starts) + WAIT + STEP
    if cutoff < stop + flight + 190:
        raise ValueError('Truth horizon not mature')
    counts = Counter()
    ticks = []
    work = Path(out)/key.replace(':', '-').replace(' ', '_')
    work.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    with CausalReplaySlice(source, work/'causal.sqlite') as mirror, \
            (work/'as-issued-bands.jsonl').open('x') as journal:
        for q in range(min(starts), stop + 1, STEP):
            pi = bisect.bisect_right(polls, q)-1
            age = q-polls[pi] if pi >= 0 else None
            fresh = age is not None and 0 <= age+15 <= 180 and not crosses(q, q)
            band = Band(q, None, ())
            status = 'STALE_SOURCE'
            if fresh:
                mirror.advance(q)
                try:
                    child_args=[sys.executable, '-B', '-c', CHILD,str(work/'causal.sqlite'),key,str(q)]
                    if all_supported:child_args.append('1')
                    child = subprocess.run(child_args, check=True,
                        capture_output=True, text=True, timeout=timeout)
                    data = json.loads(child.stdout.strip().splitlines()[-1])
                    band = Band(data['issued'], data['native'], tuple(tuple(p) for p in data['points']))
                    if band.issued != q:
                        raise ValueError('Child issue mismatch')
                    status = 'OK' if band.native is not None else 'NO_NATIVE_RECOMMENDATION'
                except subprocess.TimeoutExpired:
                    status = 'NATIVE_TIMEOUT'
                except (subprocess.CalledProcessError, ValueError, KeyError, IndexError):
                    status = 'NATIVE_ERROR'
            counts[status] += 1
            tick = dict(asdict(band), age=age if fresh else None, status=status)
            ticks.append(tick)
            journal.write(json.dumps(tick, sort_keys=True)+'\n')
            journal.flush()
    # No labels are passed into schedule, including for choosing retained targets.
    records = score_records(schedule(ticks, starts), evidence, flight)
    # Export sampled evaluation labels only AFTER inference and scheduling.
    # These let hosted research reuse frozen curves without rerunning native
    # inference or exporting stock rows / the restricted SQLite source.
    with (work/'arrival-evaluation.jsonl').open('x') as labels:
        for tick in ticks:
            dep=tick['issued']+15
            outcome,reason,_=evidence.score(dep+flight)
            labels.write(json.dumps(dict(departure=dep,arrival=dep+flight,
                outcome=outcome,reason=reason,training_input=False),sort_keys=True)+'\n')
    report = dict(item_key=key, starts=starts, truth_cutoff=cutoff, records=records,
        policies=summarize(records), distinct=concentration(records),
        inference_status_counts=dict(counts), seconds=time.monotonic()-began,
        worker_errors=counts['NATIVE_TIMEOUT']+counts['NATIVE_ERROR'],
        original_curve_parity_checked_each_issue=True,
        candidate_scope='ALL_ORIGINAL_NEAR_MAX_CLUSTERS' if all_supported else 'ORIGINAL_WINNING_CLUSTER',
        physical_depletion_quantity=0, arrival_quantity=30, grace_seconds=10,
        raw_scores_calibrated=False, automatic_promotion=False, release_approved=False,
        limitation='Historical development comparison; correlated cohorts and shared arrivals. Compute failures are explicit and disqualify clean model comparisons.')
    (work/'report.json').write_text(json.dumps(report, sort_keys=True, indent=2)+'\n')
    print(json.dumps(dict(status='ITEM_COMPLETE', item_key=key,
                         policies=report['policies'], worker_errors=report['worker_errors'])), flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--start', type=int, required=True, help='First hourly visitor start, UTC epoch')
    p.add_argument('--end', type=int, required=True, help='Last hourly visitor start, UTC epoch')
    p.add_argument('--model-sha', required=True)
    p.add_argument('--tick-timeout', type=int, default=25)
    a = p.parse_args()
    if a.start % 3600 or a.end % 3600 or a.end < a.start or a.tick_timeout <= 0:
        p.error('Ordered hourly cohort boundaries and positive timeout required')
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    starts = tuple(range(a.start, a.end+1, 3600))
    request = dict(model_sha=a.model_sha, items=KEYS, modes=MODES, starts=starts,
                   parallel_native_workers=1, automatic_promotion=False,
                   source_expiry_seconds=180, replan_seconds=STEP, max_wait_seconds=WAIT)
    (out/'request.json').write_text(json.dumps(request, sort_keys=True, indent=2)+'\n')
    results = [collect_item(a.source, out, key, starts, a.tick_timeout) for key in KEYS]
    (out/'summary.json').write_text(json.dumps(dict(request=request,
        items={r['item_key']:r['policies'] for r in results}), sort_keys=True, indent=2)+'\n')


if __name__ == '__main__': main()
