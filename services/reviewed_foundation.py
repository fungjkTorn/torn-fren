"""Reviewed item foundation. Pure causal inference; no provider calls or writes."""
from bisect import bisect_left,bisect_right
from statistics import median,mean
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from deploy.scripts.v163_readonly_event_first_preview import OBS,_ReplayPhases,_gap_index,phase_quantiles,predict_events
POLICY='REVIEWED_FOUNDATION_20261111_V1'
REVIEWED={'can:Wolverine Plushie','cay:Stingray Plushie','mex:Jaguar Plushie','arg:Monkey Plushie','sou:Xanax'}
START=1793599200
TZ=ZoneInfo('America/New_York')
KEY='sou:Xanax'

from deploy.scripts.v163_readonly_event_first_preview import *
from deploy.scripts.v163_readonly_event_first_preview import _window
def add_threshold(tracker, obs, spans):
    high_count, low_count = (len(tracker.high), len(tracker.low))
    tracker.add(OBS(obs.epoch, 200 if obs.quantity >= 31 else 0, obs.source))
    if len(tracker.high) > high_count:
        duration = tracker.high[-1]
        start = obs.epoch - duration
        spans['stocked'][start] = {'start': start, 'end': obs.epoch, 'duration': duration}
    if len(tracker.low) > low_count:
        duration = tracker.low[-1]
        start = obs.epoch - duration
        spans['empty'][start] = {'start': start, 'end': obs.epoch, 'duration': duration}
review=SimpleNamespace(add_threshold=add_threshold)
class Bulk:

    def __init__(self, crosses, minimum):
        self.crosses = crosses
        self.minimum = minimum
        self.tracker = _ReplayPhases(crosses)
        self.stocked = {}
        self.spans = {'stocked': self.stocked, 'buying': self.stocked, 'empty': {}}
        self.last = None
        self.active = False
        self.openings = []
        self.points = []
        self.pairs = []
        self.duration_at_close = {}
        self.incoming = None

    def add(self, o):
        prior = self.last
        was_active = self.active
        if o.quantity <= 30:
            self.active = False
        elif o.quantity >= self.minimum:
            self.active = True
        if self.active and (not was_active) and prior and (prior.source == o.source) and (prior.epoch < o.epoch) and (not self.crosses(prior.epoch, o.epoch)):
            self.openings.append(o.epoch)
        self.last = o
        old_onset = self.tracker.onset
        old_low_count = len(self.tracker.low)
        review.add_threshold(self.tracker, OBS(o.epoch, o.quantity if self.active else 0, o.source), self.spans)
        new_onset = self.tracker.onset
        if old_onset != new_onset:
            closed = self.stocked.get(old_onset)
            if self.points and closed and (closed['end'] == o.epoch):
                self.duration_at_close[o.epoch] = closed['duration']
                if self.incoming is not None:
                    prior_duration, wait = self.incoming
                    self.pairs.append((o.epoch, prior_duration, wait, closed['duration']))
            self.points = []
            self.incoming = None
            if len(self.tracker.low) > old_low_count and old_onset in self.duration_at_close:
                self.incoming = (self.duration_at_close[old_onset], self.tracker.low[-1])
        if new_onset is not None and self.tracker.current and (o.quantity > 30):
            self.points.append((o.epoch, o.quantity))

    def state(self):
        return dict(self.tracker.asof(), last_observation=self.last)

def active_rate(now, curve):
    if not curve or now - curve[-1][0] > 180:
        return None
    end, quantity = curve[-1]
    points = [p for p in curve if p[0] >= end - 720]
    if len(points) < 5 or end - points[0][0] < 300:
        return None
    if points[0][1] - quantity < max(100, points[0][1] * 0.12):
        return None
    rates = [(a[1] - b[1]) / (b[0] - a[0]) for i, a in enumerate(points) for b in points[i + 1:] if b[0] - a[0] >= 120]
    rate = median(rates) if rates else 0
    return max(60, round((quantity - 30) / rate - (now - end))) if rate > 0 else None

def forecast(state, history, curve, now):
    recent = history[-8:]
    phase = dict(state, stocked_durations=recent, future_stocked_durations=recent)
    rate = active_rate(now, curve) if state['phase'] == 'HIGH' else None

    def estimate(samples, *, age=0):
        result = phase_quantiles(samples, age=age)
        if rate is None or samples is not recent or (not age):
            return result
        if result is None:
            return {'early': max(60, rate // 2), 'middle': rate, 'late': rate * 2}
        center = max(60, round((result['middle'] + 2 * rate) / 3))
        return dict(early=min(result['early'], center), middle=center, late=max(result['late'], center))
    f = sa_predict_events(KEY, phase, asof=now, min_qty=31, phase_estimator=estimate)
    return dict(f, physical_phase_onset_epoch=state['phase_onset'])
class BoundedPhaseRecovery:

    def __init__(self, tracker, minimum=200, maximum_bracket=180, verified_through=None):
        self.tracker = tracker
        self.minimum = minimum
        self.maximum_bracket = maximum_bracket
        self.pending = None
        self.verified_through = verified_through
        self.recovered_bounds = None
        self.recoveries = []

    def __getattr__(self, name):
        return getattr(self.tracker, name)

    def add(self, observation):
        t = self.tracker
        prior = t.last
        high = observation.quantity >= self.minimum
        discontinuity = prior is not None and (observation.epoch <= prior.epoch or t.crosses(prior.epoch, observation.epoch))
        verified = self.verified_through(prior, observation) if prior is not None and self.verified_through else prior.epoch if prior is not None else None
        if prior is not None and (verified is None or not prior.epoch <= verified < observation.epoch):
            verified = prior.epoch
        too_sparse = prior is not None and observation.epoch - verified > self.maximum_bracket
        transition = prior is not None and high != t.current
        provider_transition = transition and observation.source != prior.source
        if self.recovered_bounds is not None and (transition or discontinuity or too_sparse):
            t.onset = None
            self.recovered_bounds = None
        if discontinuity or too_sparse:
            self.pending = None
            t.last = observation
            t.current = high
            t.onset = None
            return
        if provider_transition:
            self.pending = {'state': high, 'earliest': verified, 'latest': observation.epoch, 'source': observation.source}
            t.add(observation)
            return
        pending = self.pending
        if pending is not None:
            if high != pending['state']:
                self.pending = None
            elif 20 <= observation.epoch - pending['latest'] <= self.maximum_bracket:
                t.add(observation)
                if t.onset is None:
                    t.onset = pending['latest']
                    self.recovered_bounds = (pending['earliest'], pending['latest'])
                    self.recoveries.append(dict(pending, confirmed=observation.epoch))
                self.pending = None
                return
            elif observation.epoch - pending['latest'] > self.maximum_bracket:
                self.pending = None
        t.add(observation)

    def asof(self):
        state = self.tracker.asof()
        if self.recovered_bounds is not None:
            state.update(phase_anchor_status='RECOVERED_BOUNDED_PROVIDER_TRANSITION', phase_onset_earliest_epoch=self.recovered_bounds[0], phase_onset_latest_epoch=self.recovered_bounds[1], phase_duration_eligible_for_training=False)
        else:
            state['phase_anchor_status'] = 'PENDING_CONFIRMATION' if self.pending else 'ORIGINAL_TRACKER'
        return state
class StableEpisodeClock:

    def __init__(self, bulk, verified_through, window=180):
        self.bulk = bulk
        bulk.tracker = BoundedPhaseRecovery(bulk.tracker, verified_through=verified_through)
        self.window = window
        self.pending = []
        self.last_actual = None
        self.interrupted = False
        self.interruptions = []

    def __getattr__(self, name):
        return getattr(self.bulk, name)

    def _feed(self, obs):
        before = len(self.bulk.tracker.recoveries)
        self.bulk.add(obs)
        if len(self.bulk.tracker.recoveries) > before and self.bulk.tracker.recoveries[-1]['state']:
            opened = self.bulk.tracker.recoveries[-1]['latest']
            if opened not in self.bulk.openings:
                self.bulk.openings.append(opened)
                self.bulk.openings.sort()

    def _commit_low(self):
        if self.interrupted:
            self.bulk.tracker.tracker.onset = None
            self.bulk.tracker.recovered_bounds = None
            self.interrupted = False
        for obs in self.pending:
            self._feed(obs)
        self.pending = []

    def add(self, obs):
        previous = self.last_actual
        self.last_actual = obs
        if self.pending:
            first = self.pending[0]
            if obs.quantity > 30:
                last_positive = self.bulk.last
                continuation = 0 < obs.epoch - first.epoch <= self.window and last_positive is not None and (not self.bulk.tracker.crosses(last_positive.epoch, obs.epoch)) and (obs.quantity <= last_positive.quantity + max(30, round(last_positive.quantity * 0.05)))
                if continuation:
                    self.interruptions.append({'low_epoch': first.epoch, 'return_epoch': obs.epoch, 'previous_quantity': last_positive.quantity, 'return_quantity': obs.quantity, 'classification': 'BRIEF_RETURN_SAME_EPISODE_UNCERTAIN_AVAILABILITY'})
                    self.pending = []
                    self.interrupted = True
                    self._feed(obs)
                    return
                self._commit_low()
                self._feed(obs)
                return
            self.pending.append(obs)
            if obs.epoch - first.epoch >= self.window:
                self._commit_low()
            return
        if self.bulk.active and obs.quantity <= 30:
            self.pending = [obs]
            return
        self._feed(obs)

    def tick(self, now, source_fresh):
        if self.pending and source_fresh and (now - self.pending[0].epoch >= self.window):
            self._commit_low()

    def state(self):
        state = self.bulk.state()
        if self.last_actual is not None:
            state['last_observation'] = self.last_actual
        if self.pending:
            state.update(phase_transition_status='LOW_OBSERVATION_AWAITING_CONFIRMATION', observed_low_since_epoch=self.pending[0].epoch)
        elif self.interrupted:
            state['phase_transition_status'] = 'EPISODE_CONTINUES_WITH_OBSERVED_INTERRUPTION'
        return state

def apply_phase_uncertainty(forecast, state):
    """Expose anchor uncertainty in provisional ranges, without changing centers."""
    from copy import deepcopy
    f = deepcopy(forecast)
    earliest = state.get('phase_onset_earliest_epoch')
    latest = state.get('phase_onset_latest_epoch')
    width = max(0, latest - earliest) if type(earliest) is int and type(latest) is int else 0
    if state.get('phase_transition_status') == 'LOW_OBSERVATION_AWAITING_CONFIRMATION':
        width = max(width, 180)
    f['phase_anchor_status'] = state.get('phase_anchor_status', 'ORIGINAL_TRACKER')
    f['phase_anchor_bounds'] = {'earliest': earliest, 'latest': latest, 'range_expansion_seconds': width}
    f['phase_transition_status'] = state.get('phase_transition_status')
    if width:
        for e in f.get('restock_events', []):
            if type(e.get('restock_early_epoch')) is int:
                e['restock_early_epoch'] = max(1, e['restock_early_epoch'] - width)
            if type(e.get('restock_late_epoch')) is int:
                e['restock_late_epoch'] += width
            e['phase_anchor_uncertainty_seconds'] = width
    return f
Original=StableEpisodeClock
class PassthroughTracker:

    def __init__(self, tracker):
        self.tracker = tracker
        self.recoveries = []
        self.recovered_bounds = None

    def __getattr__(self, name):
        return getattr(self.tracker, name)

    def add(self, obs):
        self.tracker.add(obs)

    def asof(self):
        return self.tracker.asof()

class TransitionRecovery(PassthroughTracker):
    """Only recover an onset lost at a provider threshold conflict.

    A sparse bracket prevents a NEW recovery claim; it does not erase an
    existing clean onset or impose a new global historical sample filter.
    Actual collection gaps retain the original tracker's reset semantics.
    """

    def __init__(self, tracker, verified_through):
        super().__init__(tracker)
        self.verified_through = verified_through
        self.pending = None

    def add(self, obs):
        t = self.tracker
        prior = t.last
        high = obs.quantity >= 200
        gap = prior is not None and (obs.epoch <= prior.epoch or t.crosses(prior.epoch, obs.epoch))
        transition = prior is not None and high != t.current
        provider_conflict = transition and obs.source != prior.source
        if self.recovered_bounds is not None and (gap or transition):
            t.onset = None
            self.recovered_bounds = None
        t.add(obs)
        if gap:
            self.pending = None
            return
        if provider_conflict:
            verified = self.verified_through(prior, obs)
            if verified is None or not prior.epoch <= verified < obs.epoch:
                verified = prior.epoch
            self.pending = {'state': high, 'earliest': verified, 'latest': obs.epoch, 'source': obs.source} if 0 < obs.epoch - verified <= 180 else None
            return
        p = self.pending
        if p is None:
            return
        if high != p['state'] or obs.epoch - p['latest'] > 180:
            self.pending = None
            return
        if obs.source == p['source'] and 20 <= obs.epoch - p['latest'] <= 180:
            if t.onset is None:
                t.onset = p['latest']
                self.recovered_bounds = (p['earliest'], p['latest'])
                self.recoveries.append(dict(p, confirmed=obs.epoch))
            self.pending = None

    def asof(self):
        state = self.tracker.asof()
        if self.recovered_bounds is not None:
            state.update(phase_anchor_status='RECOVERED_BOUNDED_PROVIDER_TRANSITION', phase_onset_earliest_epoch=self.recovered_bounds[0], phase_onset_latest_epoch=self.recovered_bounds[1], phase_duration_eligible_for_training=False)
        elif self.pending:
            state['phase_anchor_status'] = 'PENDING_CONFIRMATION'
        return state

class BriefClock(StableEpisodeClock):

    def __init__(self, bulk, verified, recovery=False):
        tracker = bulk.tracker
        super().__init__(bulk, verified)
        bulk.tracker = TransitionRecovery(tracker, verified) if recovery else PassthroughTracker(tracker)

    def state(self):
        state = super().state()
        if self.pending:
            onset = self.pending[0].epoch
            state.update(phase='LOW', phase_onset=onset, phase_anchor_status='OBSERVED_LOW_EPISODE_CLASSIFICATION_PENDING', phase_onset_earliest_epoch=onset, phase_onset_latest_epoch=onset)
        return state
class SeparateCurrentAndFit:
    last = None

    def __init__(self, bulk, verified):
        self.fit = Original(bulk, verified)
        self.current = BriefClock(type(bulk)(bulk.crosses, bulk.minimum), verified, recovery=True)
        self.queries = 0
        SeparateCurrentAndFit.last = self

    def __getattr__(self, name):
        return getattr(self.fit, name)

    @property
    def openings(self):
        return self.current.openings

    @property
    def last_actual(self):
        return self.current.last_actual

    def add(self, obs):
        self.fit.add(obs)
        self.current.add(obs)

    def tick(self, now, fresh):
        self.fit.tick(now, fresh)
        self.current.tick(now, fresh)

    def state(self):
        phase = self.current.state()
        fit = self.fit.state()
        for key in ('stocked_durations', 'depleted_durations'):
            phase[key] = fit[key]
        self.queries += 1
        return phase
def hour(t):
    d = datetime.fromtimestamp(t, TZ)
    return d.hour + d.minute / 60

def nearest(v):
    return sorted(v)[math.ceil(len(v) * 0.5) - 1]

def duration_estimate(history, expected, now, kind):
    clean = [r for r in history if r['bulk']]
    fallback = nearest([r['duration'] for r in clean[-8:]]) if clean else None
    if kind == 'clean_last8':
        return (fallback, False, 0)
    if kind == 'clean_last2':
        return (nearest([r['duration'] for r in clean[-2:]]) if clean else None, False, 0)
    if kind == 'clean_last4':
        return (nearest([r['duration'] for r in clean[-4:]]) if clean else None, False, 0)
    if kind == 'hour_relative':
        recent = nearest([r['duration'] for r in clean[-4:]]) if clean else None
        days = defaultdict(list)
        today = datetime.fromtimestamp(now, TZ).date()
        for r in clean:
            d = datetime.fromtimestamp(r['start'], TZ).date()
            if r['start'] >= START and r['end'] >= now - 5 * 86400 and (d < today):
                days[d].append(r)
        ratios = []
        for day, values in days.items():
            if len(values) < 3:
                continue
            level = nearest([r['duration'] for r in values])
            ratios.extend((r['duration'] / level for r in values if min(abs(hour(r['start']) - hour(expected)), 24 - abs(hour(r['start']) - hour(expected))) <= 2))
        if recent is None or len(ratios) < 4:
            return (recent, False, len(ratios))
        factor = 1 + (median(ratios) - 1) * len(ratios) / (len(ratios) + 4)
        return (max(60, round(recent * factor)), True, len(ratios))
    width = 2 if kind == 'hour2_recent24' else int(kind.split('_')[-1])
    lookback = 86400 if kind == 'hour2_recent24' else 5 * 86400
    minimum = 2 if kind == 'hour2_recent24' else 4
    samples = [r for r in clean if r['start'] >= START and r['end'] >= now - lookback and (min(abs(hour(r['start']) - hour(expected)), 24 - abs(hour(r['start']) - hour(expected))) <= width)]
    if len(samples) < minimum:
        return (fallback, False, len(samples))
    return (nearest([r['duration'] for r in samples[-8:]]), True, len(samples[-8:]))
def modify(f, records, now, kind):
    if kind in ('baseline', 'fixed_baseline') or not f['restock_events']:
        return f
    from copy import deepcopy
    f = deepcopy(f)
    shift = 0
    for e in f['restock_events']:
        new, matched, count = duration_estimate(records, e['predicted_restock_epoch'] + shift, now, 'hour_relative')
        old = e['estimated_stocked_duration_seconds']
        new = new if new is not None else old
        if 'rise' in kind:
            clean = [r['duration'] for r in records if r['bulk']]
            if len(clean) >= 6:
                from statistics import median, mean
                previous = median(clean[-6:-2])
                if min(clean[-2:]) > 1.5 * previous:
                    new = max(new, round(mean(clean[-2:])))
                elif 'soft' in kind and len(clean) >= 5 and (clean[-1] > 1.5 * median(clean[-5:-1])):
                    new = max(new, round((new + clean[-1]) / 2))
        for key in ('predicted_restock_epoch', 'restock_early_epoch', 'restock_late_epoch'):
            if type(e.get(key)) is int:
                e[key] += shift
        e['estimated_stocked_duration_seconds'] = new
        e['predicted_stock_below_30_epoch'] = e['predicted_restock_epoch'] + new
        shift += new - old
    return f
def sa_predict_events(item, phases, *, asof, horizon=None, max_events=MAX_EVENTS, min_bounded=MIN_BOUNDED, recent_cycles=None, min_qty=MIN_QTY, phase_estimator=phase_quantiles):
    """All modeled replenishments up to horizon, not just selected flights.

    Causal input: phase evidence closed at or before asof, plus the
    known ongoing phase/censoring age. Model future cycle uncertainty
    grows; these are *estimates*, with no calibrated forecast accuracy.
    """
    if type(asof) is not int or asof <= 0 or type(min_qty) is not int or (min_qty < 1) or (horizon is not None and (type(horizon) is not int or horizon < 300)) or (type(max_events) is not int) or (not 1 <= max_events <= MAX_EVENTS) or (type(min_bounded) is not int) or (not 1 <= min_bounded <= 20) or (not isinstance(item, str)) or (item.count(':') != 1) or (item.split(':', 1)[0] not in TRAVEL_SECONDS) or (recent_cycles is not None and (type(recent_cycles) is not int or not 4 <= recent_cycles <= 128)):
        raise ValueError('invalid event forecast policy')
    common = {'item_key': item, 'asof_epoch': asof, 'status': 'INSUFFICIENT_BOUNDED_RESTOCK_HISTORY', 'predictions_are_provisional': True, 'restock_accuracy_verified': False, 'not_a_success_probability': True, 'arrival_stock_threshold': min_qty, 'flight_seconds': TRAVEL_SECONDS[item.split(':', 1)[0]], 'restock_events': [], 'current_stock_window': None, 'forecast_event_count': 0, 'currently_supported_departures': 0, 'unreachable_restock_events': 0, 'current_phase': phases.get('phase'), 'observed_current_quantity': getattr(phases.get('last_observation'), 'quantity', None), 'last_quantity_change_epoch': getattr(phases.get('last_observation'), 'epoch', None), 'phase_age_seconds': None, 'history_stocked_phases': len(phases.get('stocked_durations') or []), 'history_depleted_phases': len(phases.get('depleted_durations') or [])}
    high = phases.get('stocked_durations')
    low = phases.get('depleted_durations')
    if not isinstance(high, list) or not isinstance(low, list) or min(len(high), len(low)) < min_bounded:
        return common
    if recent_cycles is not None:
        high = high[-recent_cycles:]
        low = low[-recent_cycles:]
    common['cycle_window'] = recent_cycles if recent_cycles is not None else 'all'
    onset = phases.get('phase_onset')
    phase = phases.get('phase')
    last = phases.get('last_observation')
    if phase not in ('HIGH', 'LOW') or type(onset) is not int or onset > asof or (onset <= 0) or (last is None) or (type(last.epoch) is not int) or (last.epoch > asof):
        return dict(common, status='CURRENT_PHASE_UNKNOWN')
    age = asof - onset
    active = phase_estimator(high if phase == 'HIGH' else low, age=age)
    if active is None:
        return dict(common, status='CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS', phase_age_seconds=age)
    hi = phase_estimator(phases.get('future_stocked_durations', high))
    lo = phase_estimator(low)
    if hi is None or lo is None:
        return common
    common['phase_age_seconds'] = age
    common['status'] = 'EVENT_TIMELINE_FORECAST_AVAILABLE'
    if phase == 'HIGH':
        now_window = _window(item, asof, asof, active['middle'], asof, asof, active['early'])
        common['current_stock_window'] = now_window
        low_start = {p: asof + active[p] for p in ('early', 'middle', 'late')}
        next_restock = {p: low_start[p] + lo[p] for p in ('early', 'middle', 'late')}
    else:
        next_restock = {p: asof + active[p] for p in ('early', 'middle', 'late')}
    events = []
    for idx in range(max_events):
        median = next_restock['middle']
        if horizon is not None and median > asof + horizon:
            break
        window = _window(item, asof, median, hi['middle'], next_restock['early'], next_restock['late'], hi['early'])
        window['event_index'] = idx + 1
        window['restock_relative_to_now_seconds'] = median - asof
        window['restock_window_width_seconds'] = next_restock['late'] - next_restock['early']
        window['projected_beyond_first_cycle'] = idx > 0
        events.append(window)
        next_restock = {p: next_restock[p] + hi[p] + lo[p] for p in ('early', 'middle', 'late')}
    common['restock_events'] = events
    common['forecast_event_count'] = len(events)
    common['currently_supported_departures'] = sum((event['expected_departure_epoch'] is not None for event in events))
    common['unreachable_restock_events'] = sum((event['expected_departure_epoch'] is None for event in events))
    common['event_horizon_seconds'] = horizon
    common['event_horizon_type'] = 'EVENT_COUNT_ONLY' if horizon is None else 'LEGACY_TIME_BOUND'
    common['bounded_event_list_truncated'] = len(events) == max_events and (horizon is None or next_restock['middle'] <= asof + horizon)
    return common

def calculate(rows,gaps,receipts,asof,item,baseline):
    crosses=_gap_index(gaps,asof)
    rt=[r[0] for r in receipts]
    def verified(prior,obs):
        j=bisect_left(rt,obs.epoch)-1
        if j>=0:
            t,u,status=receipts[j]
            if status=='REPORTED' and u is not None and 0<=t-u<=180 and t>=prior.epoch:return t
        return prior.epoch
    clock=SeparateCurrentAndFit(Bulk(crosses,1250),verified) if item==KEY else BriefClock(Bulk(crosses,31),verified,recovery=True)
    records=[]
    for obs in rows:
        if obs.epoch>asof:raise ValueError('future observation')
        before=len(clock.tracker.high)
        clock.add(obs)
        if item==KEY and len(clock.tracker.high)>before:
            closed=max(clock.stocked.values(),key=lambda v:v['end'])
            ix=bisect_right([r.epoch for r in rows],closed['start'])-1
            records.append(dict(closed,bulk=ix>=0 and rows[ix].quantity>=1250))
    before=len(clock.tracker.high)
    clock.tick(asof,True)
    if item==KEY and len(clock.tracker.high)>before:
        closed=max(clock.stocked.values(),key=lambda v:v['end'])
        ix=bisect_right([r.epoch for r in rows],closed['start'])-1
        records.append(dict(closed,bulk=ix>=0 and rows[ix].quantity>=1250))
    state=clock.state()
    if item!=KEY:
        for k in ('stocked_durations','depleted_durations','observed_bounded_stocked_windows','observed_bounded_depleted_windows'):
            state[k]=baseline[k]
    state['reviewed_foundation_policy']=POLICY
    state['_reviewed_clock']=clock
    state['_reviewed_records']=records
    return state

def sa_forecast(item,state,*,asof,horizon=None,min_qty=31):
    clock=state['_reviewed_clock']
    curve=[] if clock.interrupted else clock.points
    f=modify(forecast(state,clock.tracker.high,curve,asof),state['_reviewed_records'],asof,'fixed_combined_rise')
    f=apply_phase_uncertainty(f,state)
    if clock.last_actual and clock.last_actual.quantity<=30:f['current_stock_window']=None
    f['sa_model_policy']='SA_RECENT4_HOUR_RATE_SUSTAINED_RISE_V1'
    f['reviewed_foundation_policy']=POLICY
    return f
