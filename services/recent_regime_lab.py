import statistics

from services.arrival_model_tournament import _model_arrival_backtest
from services.arrival_success_lab import _incoming_lifetimes
from services.medium_model_lab import analyze_advanced_item
from services.prediction_v2_selector import select_prediction_v2_model


def _pct_hits(rows):
    usable = [r for r in rows if r.get('arrival_hit') is not None]
    if not usable:
        return None
    return sum(bool(r['arrival_hit']) for r in usable) / len(usable)


def _point_stats(rows):
    errs = [float(r['signed_error_seconds']) for r in rows if r.get('signed_error_seconds') is not None]
    if not errs:
        return None
    abs_errs = sorted(abs(x) for x in errs)
    p90_idx = max(0, min(len(abs_errs)-1, int(round(0.9*(len(abs_errs)-1)))))
    return {
        'n': len(errs),
        'median_signed_error_seconds': statistics.median(errs),
        'median_absolute_error_seconds': statistics.median(abs_errs),
        'p90_absolute_error_seconds': abs_errs[p90_idx],
        'min_error_seconds': min(errs),
        'max_error_seconds': max(errs),
    }


def analyze_recent_regime(country, item_name, model_name='baseline_all_median', policy='lifetime', min_train=15):
    selector = select_prediction_v2_model(country, item_name, min_train=min_train)
    analysis = analyze_advanced_item(country, item_name, min_train=min_train)
    records = list(analysis['records_by_model'].get(model_name, []))
    lifetimes = _incoming_lifetimes(country, item_name)
    median_lifetime = selector.get('median_stock_lifetime_seconds')

    recent_limit = None if policy == 'lifetime' else 20 if policy == 'recent20' else 10
    bt = _model_arrival_backtest(records, lifetimes, median_lifetime, recent_limit=recent_limit)
    if not bt:
        return {
            'country': country.upper(), 'item_name': item_name, 'model': model_name,
            'policy': policy, 'rows': [], 'windows': {}, 'regime_status': 'insufficient',
            'regime_reason': 'Not enough resolved walk-forward predictions.'
        }

    # Rebuild scored rows because _model_arrival_backtest currently returns summary only.
    # Replay its logic locally by pairing each record to a resolved lifetime, then use the
    # same offsets stored by a second pass through helper internals in arrival_model_tournament.
    from services.arrival_model_tournament import _adaptive_offset
    from services.arrival_success_lab import _success
    history = []
    scored = []
    for rec in records:
        ts = rec.get('actual_restock_timestamp')
        if ts is None:
            continue
        lifetime = lifetimes.get(int(ts))
        if lifetime is None:
            continue
        offset = _adaptive_offset(history, recent_limit=recent_limit, max_offset_seconds=median_lifetime)
        row = dict(rec)
        row['actual_lifetime_seconds'] = lifetime
        row['recommended_arrival_offset_seconds'] = offset
        row['arrival_hit'] = _success(rec['signed_error_seconds'], lifetime, offset) if offset is not None else None
        history.append(row)
        if row['arrival_hit'] is not None:
            scored.append(row)

    windows = {}
    for size in (5, 10, 15, 20):
        subset = scored[-size:]
        windows[size] = {
            'n': len(subset),
            'arrival_success_rate': _pct_hits(subset),
            'point': _point_stats(subset),
        }
    windows['all'] = {
        'n': len(scored),
        'arrival_success_rate': _pct_hits(scored),
        'point': _point_stats(scored),
    }

    r5 = windows[5]['arrival_success_rate']
    r10 = windows[10]['arrival_success_rate']
    r15 = windows[15]['arrival_success_rate']
    r20 = windows[20]['arrival_success_rate']
    rall = windows['all']['arrival_success_rate']

    status = 'no_recent_regime'
    reason = 'Recent results do not yet show a stable improvement over lifetime performance.'
    if len(scored) >= 15 and r10 is not None and r15 is not None:
        if r10 >= 0.90 and r15 >= 0.80 and (rall is None or r10 >= rall + 0.10):
            status = 'recent_regime_candidate'
            reason = 'Last 10 and last 15 are both strong and materially better than lifetime performance.'
            if r5 is not None and r5 >= 0.80 and (r20 is None or r20 >= 0.70):
                status = 'recent_regime_supported'
                reason = 'Last 5/10/15 are strong, last 20 is acceptable, and recent performance materially exceeds lifetime.'

    # Actual recent point-error tightening helps distinguish a real timing regime from
    # arrival-offset luck.
    p10 = windows[10]['point']
    pall = windows['all']['point']
    if status.startswith('recent_regime') and p10 and pall:
        if p10['median_absolute_error_seconds'] > pall['median_absolute_error_seconds'] * 1.20:
            status = 'recent_arrival_streak_only'
            reason = 'Arrival success improved, but recent point errors did not tighten; treat as a streak rather than a timing regime.'

    return {
        'country': country.upper(),
        'item_name': item_name,
        'model': model_name,
        'policy': policy,
        'behavior_class': selector['behavior_class'],
        'model_evidence_tier': selector['selection_tier'],
        'median_stock_lifetime_seconds': median_lifetime,
        'windows': windows,
        'regime_status': status,
        'regime_reason': reason,
        'rows': scored,
    }
