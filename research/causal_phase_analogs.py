"""Bounded item-local regime analogs, using completed phases only.

Research challenger, not parity with the archived global-regime specialists.
Each neighbor's features were known at its phase onset. Its duration becomes
eligible only at completion. Provider/gap continuity matches V145.
"""
import math
from collections import deque

from deploy.scripts import v163_readonly_event_first_preview as model


class PhaseAnalogs:
    def __init__(self, crosses, *, neighbors=18, capacity=512):
        if type(neighbors) is not int or not 4 <= neighbors <= 64:
            raise ValueError('invalid neighbor count')
        if type(capacity) is not int or not neighbors <= capacity <= 2048:
            raise ValueError('invalid history capacity')
        self.crosses = crosses
        self.neighbors = neighbors
        self.capacity = capacity
        self.records = {True: deque(maxlen=capacity), False: deque(maxlen=capacity)}
        self.last = None
        self.phase = self.onset = self.features = None
        self.previous_duration = None

    @staticmethod
    def feature(epoch, quantity, previous_duration):
        angle = 2 * math.pi * (epoch % 86400) / 86400
        return (math.sin(angle), math.cos(angle), math.log1p(quantity),
                math.log1p(previous_duration) if previous_duration is not None else None)

    def add(self, obs):
        high = obs.quantity >= 30
        if self.last is None:
            self.phase = high
        elif (obs.epoch <= self.last.epoch or self.crosses(self.last.epoch, obs.epoch)
              or (obs.source != self.last.source and high != self.phase)):
            self.phase, self.onset, self.features = high, None, None
            self.previous_duration = None
        elif high != self.phase:
            duration = obs.epoch - self.onset if self.onset is not None else None
            if duration is not None and duration > 0:
                self.records[self.phase].append((self.features, duration, obs.epoch))
            self.previous_duration = duration
            self.phase, self.onset = high, obs.epoch
            self.features = self.feature(obs.epoch, obs.quantity, duration)
        self.last = obs

    def forecast(self, key, state, *, asof):
        # This check also protects callers from accidentally feeding future rows.
        if self.last is not None and self.last.epoch > asof:
            raise ValueError('future observation in analog tracker')
        selected = {}
        counts = {}
        for high, field in ((True, 'stocked_durations'), (False, 'depleted_durations')):
            history = self.records[high]
            counts[field] = len(history)
            if len(history) < self.neighbors or self.features is None:
                selected[field] = []
                continue
            # For the opposite phase, only shared clock/regime coordinates are
            # comparable; current entry quantity belongs to the current phase.
            axes = (0, 1, 2, 3) if high == self.phase else (0, 1)
            def distance(record):
                f, _, completed = record
                if completed > asof:
                    raise ValueError('unresolved analog')
                return sum((f[i] - self.features[i]) ** 2 for i in axes
                           if f[i] is not None and self.features[i] is not None)
            nearest = sorted(history, key=lambda r: (distance(r), -r[2]))[:self.neighbors]
            selected[field] = [r[1] for r in nearest]
        forecast = model.predict_events(key, dict(state, **selected), asof=asof)
        forecast.update(model_name='causal_item_phase_analogs_v1',
                        analog_neighbors=self.neighbors, analog_history_counts=counts,
                        cycle_window=f'phase_analogs_{self.neighbors}'+(f'_recent{self.capacity}' if self.capacity!=512 else ''), calibration_state='UNCALIBRATED')
        return forecast
