"""Pure journal diagnostics; no inference, truth labels, routing or promotion."""
from collections import Counter, defaultdict


def review(records, attempts, *, roster, modes):
    expected={(key,mode) for key in roster for mode in modes}
    if len(roster)!=24 or len(modes)!=9 or len(expected)!=216:
        raise ValueError('Exact24 by nine capture footprint required')
    batches=[]
    for offset in range(0,len(records),216):
        chunk=records[offset:offset+216]
        identities=Counter((r['item_key'],r['mode']) for r in chunk)
        batches.append(dict(batch=offset//216,rows=len(chunk),
            complete=len(chunk)==216 and set(identities)==expected and max(identities.values())==1,
            missing_item_models=len(expected-set(identities)),
            unexpected_item_models=len(set(identities)-expected),
            duplicate_item_models=sum(n-1 for n in identities.values())))
    grouped=defaultdict(list)
    for r in records:grouped[(r['item_key'],r['mode'])].append(r)
    if set(grouped)-expected:raise ValueError('Unrecognized item/model in capture')
    first_success=min((t for t,status in attempts if status=='ALL24_SPECIALIST_SHADOW_RECORDED'),default=None)
    active_hours=set()
    if first_success is not None:
        last=max([t for t,_ in attempts]+[r['published'] for r in records])
        active_hours=set(range(first_success//3600,last//3600+1))
    captured_hours={r['issued']//3600 for r in records}
    models={}
    for key,mode in sorted(expected):
        rows=grouped[(key,mode)]
        eligible=[r for r in rows if r['executable_before_next_recheck']]
        hours={r['issued']//3600 for r in eligible}
        models[key+'|'+mode]=dict(observed_rows=len(rows),
            observed_hours=len({r['issued']//3600 for r in rows}),
            eligible_rows=len(eligible),eligible_hours=len(hours),
            observed_active_window_hours=len(active_hours),
            eligible_hour_fraction_in_observed_active_window=(len(hours & active_hours)/len(active_hours) if active_hours else None),
            distinct_eligible_departures=len({r['departure'] for r in eligible}),
            statuses=dict(sorted(Counter(r['status'] for r in rows).items())))
    return dict(recorded_items=len({r['item_key'] for r in records}),
        missing_items=sorted(set(roster)-{r['item_key'] for r in records}),
        complete24_row_batches=sum(b['complete'] for b in batches),
        incomplete_row_batches=[b for b in batches if not b['complete']],
        complete_footprints=bool(batches) and all(b['complete'] for b in batches),
        active_window_observed_hours=len(active_hours),
        active_hours_without_any_capture=sorted(active_hours-captured_hours),
        capture_attempt_statuses=dict(sorted(Counter(status for _,status in attempts).items())),
        models=models,automatic_promotion=False,
        interpretation='Eligible hours are capture coverage in observed UTC-hour buckets, including partial hours; not visitor execution coverage. Entire skipped hours remain in that denominator. Repeated targets are not independent flights. Complete footprints verify saved item/model rows, not successful inference or release readiness.')
