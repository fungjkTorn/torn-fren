from __future__ import annotations
import argparse, json, math, statistics, time
from pathlib import Path

import services.history_service as hs
from services.japan_xanax_window_regime_longform import build_windows, build_samples, hit


def wilson(k, n, z=1.96):
    if not n:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    r = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return [c-r, c+r]


def quantile(values, q):
    vals = sorted(values)
    if not vals:
        return 0.0
    pos = (len(vals)-1) * q
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    f = pos-lo
    return vals[lo]*(1-f)+vals[hi]*f


def strict_samples(windows, rows, cooldown_lo=90*60, cooldown_hi=150*60):
    """Keep only continuously observed P2 paths with plausible Xanax cooldowns."""
    return [r for r in rows if cooldown_lo <= r['g1'] <= cooldown_hi and cooldown_lo <= r['g2'] <= cooldown_hi]


def observed_cooldowns(windows, upto_index, lo=90*60, hi=150*60):
    vals = []
    for j in range(1, upto_index+1):
        c = windows[j]['start'] - windows[j-1]['end']
        if lo <= c <= hi:
            vals.append(c)
    return vals


def base_prediction(windows, cur, cooldown_lookback=20, current_width_weight=.5):
    i = cur['window_index']
    c = observed_cooldowns(windows, i)
    c = c[-cooldown_lookback:]
    cooldown_center = statistics.mean(c)
    hist_width = statistics.median(w['width'] for w in windows[:i+1])
    future_lifetime = current_width_weight * windows[i]['width'] + (1-current_width_weight) * hist_width
    return 2*cooldown_center + future_lifetime


def resolved_training(rows, cur):
    return [r for r in rows if r['anchor'] < cur['anchor'] and r['target_end'] <= cur['anchor']]


def predict(windows, rows, cur, bias_lookback=10, bias_shrink=.5):
    base = base_prediction(windows, cur)
    train = resolved_training(rows, cur)
    if not train:
        return base
    train = train[-bias_lookback:]
    residuals = []
    for old in train:
        old_base = base_prediction(windows, old)
        actual_start_offset = old['target_start'] - old['anchor']
        residuals.append(actual_start_offset - old_base)
    return base + bias_shrink * statistics.median(residuals)


def recommend(windows, cur, width_quantile=.20):
    i = cur['window_index']
    history = [w['width'] for w in windows[:i]]
    return cur['prev_width'] >= quantile(history, width_quantile) if history else True


def evaluate(windows, rows, start=60, width_quantile=.20):
    rec = []
    for k in range(start, len(rows)):
        cur = rows[k]
        if not recommend(windows, cur, width_quantile):
            continue
        arrival_offset = predict(windows, rows[:k], cur)
        arrival = cur['anchor'] + arrival_offset
        rec.append({
            'sample': k,
            'anchor': cur['anchor'],
            'arrival_offset_s': arrival_offset,
            'actual': {g: int(hit(cur, arrival, g)) for g in [0,5,15,60,180]},
        })
    n = len(rec)
    rates = {g: (sum(r['actual'][g] for r in rec)/n if n else 0.0) for g in [0,5,15,60,180]}
    return {
        'n': n,
        'coverage': n/max(1, len(rows)-start),
        'rates': rates,
        'wilson': {g: wilson(sum(r['actual'][g] for r in rec), n) for g in [0,180]},
        'records': rec,
    }


def main():
    p = argparse.ArgumentParser(description='Strictly causal Japan Xanax regime/bias arrival model')
    p.add_argument('--db', default='data/stock_history.db')
    p.add_argument('--country', default='jap')
    p.add_argument('--item', default='Xanax')
    p.add_argument('--min-quantity', type=int, default=30)
    p.add_argument('--min-train-cycles', type=int, default=60)
    p.add_argument('--width-quantile', type=float, default=.20)
    p.add_argument('--output', default='reports/japan_xanax_causal_regime_v5')
    a = p.parse_args()
    hs.DB_PATH = Path(a.db)
    windows = build_windows(a.country, a.item, a.min_quantity)
    rows = strict_samples(windows, build_samples(windows))
    if len(rows) <= a.min_train_cycles:
        raise SystemExit(f'Only {len(rows)} strict causal samples')
    result = evaluate(windows, rows, a.min_train_cycles, a.width_quantile)
    first = rows[a.min_train_cycles]['anchor']
    last = rows[-1]['anchor']
    days = max((last-first)/86400, 1e-9)
    summary = {
        'schema': 'japan-xanax-causal-regime-v5',
        'created_at': int(time.time()),
        'development_only': True,
        'strict_rules': {
            'collector_gaps_excluded': True,
            'provider_bounces_suppressed': True,
            'cooldown_range_minutes': [90,150],
            'training_labels_must_resolve_before_current_anchor': True,
        },
        'model': {
            'cooldown_lookback': 20,
            'future_lifetime': '0.5 * current width + 0.5 * historical median width',
            'bias': '0.5 * median start residual from last 10 resolved P2 samples',
            'recommend_when': f'current width >= historical {a.width_quantile:.0%} quantile',
        },
        'windows': len(windows),
        'strict_samples': len(rows),
        'evaluation_samples': len(rows)-a.min_train_cycles,
        'recommended': result['n'],
        'coverage': result['coverage'],
        'rates': result['rates'],
        'wilson': result['wilson'],
        'evaluation_days': days,
        'recommendations_per_day': result['n']/days,
    }
    out = Path(a.output).with_suffix('.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    print(f'Saved {out}')


if __name__ == '__main__':
    main()
