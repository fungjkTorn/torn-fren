"""Independent physical-zero labels for archived forecasts; no model fitting.

Forecast Pn is compared to the nth observed 0->positive transition after
issuance. Small refills remain events. Ambiguous coverage never causes a
later event to be substituted. This is a NEW physical-event benchmark, not
certification of the old auditor's normal-cycle ordinal semantics.
"""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict


def match(rows, polls, gaps, *, issued, ordinal, cutoff, estimate=None,
          window_start=None, window_end=None):
    """Rows are (timestamp, quantity, provider); polls are successful epochs.

    Actual event time lies in (last confirmed zero poll, first positive row].
    A model cannot earn a hit by choosing a nearby event retrospectively.
    """
    if type(ordinal) is not int or ordinal < 1:
        raise ValueError('A positive, explicit physical-event ordinal is required')
    if issued > cutoff:
        raise ValueError('Issue is beyond evidence cutoff')
    rows = [r for r in rows if r[0] <= cutoff]
    if any(a[0] >= b[0] for a,b in zip(rows,rows[1:])):
        return dict(status='UNKNOWN',reason='NON_UNIQUE_OBSERVATION_TIMES')
    times = [r[0] for r in rows]
    i = bisect_right(times,issued)-1
    if i < 0:
        return dict(status='UNKNOWN',reason='NO_ISSUE_STATE')
    if issued-rows[i][0]>86400:
        return dict(status='UNKNOWN',reason='ISSUE_STATE_OLDER_THAN_24H')
    events = []
    for a,b in zip(rows[i:],rows[i+1:]):
        if a[1] == 0 < b[1]:
            events.append((a,b))
    # Assess continuity even when no target exists; otherwise an outage
    # containing an unobserved cycle would look like an ordinary pending label.
    end = events[ordinal-1][1][0] if len(events)>=ordinal else cutoff
    if any(start <= end and (stop is None or stop >= issued) for start,stop in gaps):
        return dict(status='UNKNOWN',reason='COLLECTION_GAP')
    segment = rows[i:bisect_right(times,end)]
    if len({r[2] for r in segment}) != 1 or segment[0][2] is None:
        return dict(status='UNKNOWN',reason='PROVIDER_SWITCH_OR_MISSING')
    poll_times = [t for t in polls if t <= cutoff]
    pi = bisect_right(poll_times,issued)-1
    pj = bisect_left(poll_times,end)
    if pi < 0 or pj >= len(poll_times):
        return dict(status='UNKNOWN',reason='NO_POLL_BRACKET')
    coverage = poll_times[pi:pj+1]
    if any(b-a > 180 for a,b in zip(coverage,coverage[1:])):
        return dict(status='UNKNOWN',reason='SPARSE_POLL_COVERAGE')
    if len(events)<ordinal:
        return dict(status='PENDING',reason='PHYSICAL_EVENT_NOT_OBSERVED')
    zero,positive = events[ordinal-1]
    # Carry-forward delta state is confirmed at successful polls. Do not
    # mistake the timestamp of an old quantity change for the event lower bound.
    zi = bisect_left(poll_times,positive[0])-1
    if zi < 0 or poll_times[zi] < zero[0]:
        return dict(status='UNKNOWN',reason='NO_ZERO_POLL_BEFORE_RESTOCK')
    lower,upper = poll_times[zi],positive[0]
    if lower < issued:
        return dict(status='UNKNOWN',reason='RESTOCK_BRACKET_STRADDLES_ISSUE')
    result = dict(status='RESOLVED',event_ordinal=ordinal,
                  restock_after_epoch=lower,restock_by_epoch=upper,
                  observed_restock_quantity=positive[1],physical_depletion_quantity=0)
    if estimate is not None:
        result['minimum_absolute_error_seconds'] = max(lower-estimate,estimate-upper,0)
        result['maximum_absolute_error_seconds'] = max(abs(lower-estimate),abs(upper-estimate))
    if window_start is not None and window_end is not None:
        if window_start > window_end:
            result['window_result']='INVALID_WINDOW'
        elif window_start <= lower and upper <= window_end:
            result['window_result']='HIT'
        elif window_end <= lower or window_start > upper:
            result['window_result']='MISS'
        else:
            result['window_result']='UNKNOWN_EVENT_TIME_WITHIN_POLL_BRACKET'
    return result


def audit(db, points, cutoff):
    """Use an existing read-only snapshot connection, bounded by item.

    points contain item_key, created_at, prediction_number, estimate_timestamp
    and window endpoints. No archive labels are updated or reused as truth.
    """
    required={'stock_history','poll_heartbeats','collection_gaps'}
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required <= tables:
        return dict(status='MISSING_PHYSICAL_EVIDENCE_TABLES',missing_tables=sorted(required-tables))
    groups=defaultdict(list)
    for p in points:groups[p['item_key']].append(p)
    overall=Counter();per_item={}
    for key,group in sorted(groups.items()):
        start=min(p['created_at'] for p in group)
        country,item=key.split(':',1)
        predecessor=db.execute('''SELECT timestamp,quantity,source FROM stock_history
            WHERE country=? AND item_name=? AND timestamp<=?
            ORDER BY timestamp DESC,id DESC LIMIT 1''',(country,item,start)).fetchone()
        rows=db.execute('''SELECT timestamp,quantity,source FROM stock_history
            WHERE country=? AND item_name=? AND timestamp>? AND timestamp<=?
            ORDER BY timestamp,id LIMIT 100001''',(country,item,start,cutoff)).fetchall()
        if len(rows)>100000:raise ValueError('Physical evidence cap exceeded; narrow days')
        if predecessor is not None:rows.insert(0,predecessor)
        polls=db.execute('''SELECT timestamp,source FROM poll_heartbeats
            WHERE mode='poll-cycle' AND success=1 AND timestamp>=? AND timestamp<=?
            ORDER BY timestamp,id LIMIT 400001''',(start-180,cutoff)).fetchall()
        if len(polls)>400000:raise ValueError('Physical poll cap exceeded; narrow days')
        gaps=db.execute('''SELECT start_timestamp,end_timestamp FROM collection_gaps
            WHERE start_timestamp<=? AND COALESCE(end_timestamp,9223372036854775807)>=?''',
            (cutoff,start)).fetchall()
        counts=Counter()
        # A switch and return in poll providers must also invalidate identity.
        for p in group:
            r=match(rows,sorted({r[0] for r in polls}),gaps,issued=p['created_at'],
                ordinal=p['prediction_number'],cutoff=cutoff,estimate=p.get('estimate_timestamp'),
                window_start=p.get('window_start_timestamp'),window_end=p.get('window_end_timestamp'))
            end=r.get('restock_by_epoch',cutoff)
            sources={src for t,src in polls if p['created_at']-180<=t<=end}
            if len(sources)>1 or None in sources:
                r=dict(status='UNKNOWN',reason='POLL_PROVIDER_SWITCH_OR_MISSING')
            elif r['status']=='RESOLVED' and sources != {rows[bisect_right([row[0] for row in rows],p['created_at'])-1][2]}:
                r=dict(status='UNKNOWN',reason='POLL_ITEM_PROVIDER_MISMATCH')
            counts[r['status']]+=1
            if 'reason' in r:counts[r['reason']]+=1
            if 'window_result' in r:counts[r['window_result']]+=1
        per_item[key]=dict(counts);overall.update(counts)
    return dict(status='INDEPENDENT_PHYSICAL_ORDINAL_DIAGNOSTIC',overall=dict(overall),
                per_item=per_item,legacy_normal_cycle_identity_certified=False,
                matching_uses_predicted_time=False,tiny_restocks_skipped=False,
                exact_game_event_times_verified=False)


def archived_audit(db, *, cutoff, days=30):
    """Freeze first active forecast per item/hour before reading outcomes."""
    if type(days) is not int or not 1<=days<=90:
        raise ValueError('days must be 1..90')
    from research.v128_full24_earliest_shadow import exact_roster
    allowed=set(exact_roster())
    rows=db.execute('''SELECT r.country,r.item_name,r.created_at,p.prediction_number,
        p.estimate_timestamp,p.window_start_timestamp,p.window_end_timestamp
        FROM forecast_audit_runs r JOIN forecast_audit_points p ON p.run_id=r.id
        WHERE r.created_at BETWEEN ? AND ? AND p.prediction_number=r.active_prediction_number
        ORDER BY r.created_at,p.id LIMIT 60001''',(cutoff-days*86400,cutoff)).fetchall()
    if len(rows)>60000:raise ValueError('Archived identity cap exceeded; narrow days')
    first={}
    for country,item,issued,ordinal,estimate,start,end in rows:
        key=country.lower()+':'+item
        if key not in allowed:continue
        first.setdefault((key,issued//3600),dict(item_key=key,created_at=issued,
            prediction_number=ordinal,estimate_timestamp=estimate,
            window_start_timestamp=start,window_end_timestamp=end))
    return audit(db,list(first.values()),cutoff)
