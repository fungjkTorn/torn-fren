"""Research-only, current-band-supported departure retention.

An old target is not a commitment: each issue must still place it in the
original model's CURRENT winning cluster. No truth, predicted quantity,
depletion estimate, or outcome label enters this policy. Scores are uncalibrated.
"""
from dataclasses import dataclass
import math

WAIT = 28800
STEP = 300
MODES = ('native', 'front_original_band', 'retain_original_band',
         'retain_original_band55', 'leave_now_control')


@dataclass(frozen=True)
class Band:
    issued: int
    native: int | None
    points: tuple  # (absolute departure, current raw model score)

    def __post_init__(self):
        if type(self.issued) is not int:
            raise ValueError('Integer issue required')
        if self.native is not None and (type(self.native) is not int or
                not self.issued <= self.native <= self.issued + WAIT):
            raise ValueError('Native target out of bounds')
        times = []
        for dep, score in self.points:
            if type(dep) is not int or not self.issued <= dep <= self.issued + WAIT:
                raise ValueError('Band target out of bounds')
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Invalid model score')
            times.append(dep)
        if times != sorted(set(times)):
            raise ValueError('Band must be sorted and unique')
        if times and self.native not in times:
            raise ValueError('Native target absent from winning band')


class Policy:
    """One instance per visitor AND mode; deadline never advances on replan."""
    def __init__(self, start, mode):
        if mode not in MODES:
            raise ValueError('Unknown fixed policy')
        self.mode = mode
        self.start = start
        self.deadline = start + WAIT
        self.target = None
        self.last_issue = None

    def update(self, band, age):
        q = band.issued
        if q < self.start or (self.last_issue is not None and q <= self.last_issue):
            raise ValueError('Nonincreasing visitor issue')
        self.last_issue = q
        if q + 15 > self.deadline or age is None or not 0 <= age + 15 <= 180:
            self.target = None
            return None
        points = {d: s for d, s in band.points if d <= self.deadline}
        if self.mode == 'native':
            target = band.native
        elif self.mode == 'leave_now_control':
            target = q
        elif self.mode == 'front_original_band':
            target = min(points, default=None)
        else:
            if self.mode == 'retain_original_band55':
                points = {d: s for d, s in points.items() if s >= .55}
            # Both retained and new targets need current support. In particular,
            # a native no-reference .5 fallback never supplies a retained band.
            candidates = [d for d in (self.target, band.native) if d in points]
            target = min(candidates, default=None)
        self.target = target if target is not None and q <= target <= self.deadline else None
        # Preserve the existing 15-second publication floor for grid-zero only.
        # A passed target is discarded above, never moved to a new issue.
        return max(q + 15, self.target) if self.target is not None else None


def template_band(planner, issued):
    from research.template_window_study import curve
    import numpy as np
    native = int(planner.plan(issued)[0])
    values = curve(planner, issued)
    delays, scores = values['delays'], values['scores']
    if not len(delays):
        return Band(issued, native, ())
    ids = np.flatnonzero(scores >= scores.max() - .04)
    groups = np.split(ids, np.where(np.diff(delays[ids]) > STEP)[0] + 1)
    group = max(groups, key=lambda g: (sum(float(scores[i]) for i in g) / len(g),
                                      len(g), -int(delays[g[0]])))
    if issued + int(delays[group[len(group)//2]]) != native:
        raise ValueError('Original template center parity failed')
    return Band(issued, native, tuple((issued + int(delays[i]), float(scores[i])) for i in group))


def analog_band(planner, issued):
    import numpy as np
    from research.v103_champion_score_curves import analog_scores, analog_champion_from_curve
    values = analog_scores(planner, issued)
    native = planner.plan(issued)
    rebuilt = analog_champion_from_curve(issued, values)
    if (native is None) != (rebuilt is None) or (native is not None and int(native[0]) != rebuilt[0]):
        raise ValueError('Original analog center parity failed')
    if native is None:
        return Band(issued, None, ())
    prob, robust = values['availability_score'], values['robust_score']
    ids = np.flatnonzero((robust >= robust.max() - .025) & (prob >= prob.max() - .04))
    if len(ids):
        groups = np.split(ids, np.where(np.diff(ids) > 1)[0] + 1)
        group = max(groups, key=lambda g: (float(robust[g].mean()), float(prob[g].mean()), len(g), -int(g[0])))
    else:
        group = [int(np.argmax(robust))]
    return Band(issued, int(native[0]), tuple((issued + int(values['delay_seconds'][i]), float(prob[i])) for i in group))


def observe_v20_plan(call):
    """Observe locals on return from the UNMODIFIED V20 plan in one child.

    Captures its actual winning cluster rather than reimplementing V20 math.
    Never installed in a server; the caller is an isolated research subprocess.
    """
    import sys
    from services import plushie_flower_dynamic_planner_v20 as engine
    captured = []
    previous = sys.getprofile()
    if previous is not None:
        raise ValueError('Refuse to replace an existing profiler')

    def observe(frame, event, result):
        if frame.f_code is engine.plan.__code__ and event == 'return':
            if result is None:
                captured.append(None)
            else:
                local = frame.f_locals
                cluster = local.get('cluster', [local['chosen_point']])
                captured.append(Band(int(local['qtime']), int(result['departure_time']),
                    tuple((int(local['qtime'] + p['delay']), float(p['prob'])) for p in cluster)))
    sys.setprofile(observe)
    try:
        result = call()
    finally:
        sys.setprofile(previous)
    if len(captured) > 1:
        raise ValueError('Unexpected multiple V20 plan calls')
    return result, captured[0] if captured else None


KEYS = ('uae:Camel Plushie', 'uni:Nessie Plushie', 'uni:Red Fox Plushie', 'chi:Peony')


def native_band(db, key, issued):
    """Requires an issue-truncated causal DB, never the outcome database."""
    import sqlite3
    from contextlib import closing
    from pathlib import Path
    from types import SimpleNamespace
    if key not in KEYS:
        raise ValueError('Unsupported native route')
    if type(issued) is not int or issued % STEP:
        raise ValueError('Native experiment requires grid-aligned issue')
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + '?mode=ro', uri=True)) as c:
        for table, clock in (('stock_history', 'timestamp'), ('poll_heartbeats', 'timestamp'),
                             ('collection_gaps', 'start_timestamp'), ('collection_gaps', 'end_timestamp')):
            if c.execute(f'SELECT 1 FROM {table} WHERE {clock}>? LIMIT 1', (issued,)).fetchone():
                raise ValueError('Future evidence supplied to native band')
    country, item = key.split(':', 1)
    if key == 'chi:Peony':
        from research.v38_peony_single_tick import predict
        result, band = observe_v20_plan(lambda: predict(db, country, item, issued))
        dep = result.get('recommended_departure_timestamp')
        if (band is None and dep is not None) or (band is not None and dep != band.native):
            raise ValueError('V20 native adapter parity failed')
        return band or Band(issued, None, ())
    if key == 'uni:Red Fox Plushie':
        from research.plushie_champions.common import ResearchContext, AnalogPlanner
        ctx = ResearchContext.build(db, asof=issued, readonly=True)
        try:
            return analog_band(AnalogPlanner(ctx, country, item, k=18, global_weight=.5, cutoff=issued), issued)
        finally:
            ctx.con.close()
    from research.plushie_champions.common import connect, load_gaps, Timeline
    from research.v46_fast_template import FastTemplatePlanner
    from research.v38_camel_single_tick import EXPERTS
    c = connect(db, readonly=True)
    try:
        gs, ge = load_gaps(c)
        ctx = SimpleNamespace(timelines={(country, item): Timeline(c, gs, ge, country, item)})
        if key == 'uni:Nessie Plushie':
            return template_band(FastTemplatePlanner(ctx, country, item, lags=(1,),
                lookback=7200, shift_range=3600, minfit=.5), issued)
        bank = []
        for lags, look, shift in EXPERTS:
            p = FastTemplatePlanner(ctx, country, item, lags=lags, lookback=look, shift_range=shift)
            choice = p.plan(issued)
            bank.append((choice[1], choice[2]['maxfit'], -choice[0], p))
        winner = max(bank, key=lambda b: b[:3])
        return template_band(winner[-1], issued)
    finally:
        c.close()
