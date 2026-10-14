"""Bounded causal challenger; completed zero cycles plus current stock declines.

Rates are sampled inventory decline, not certified purchases. No fit uses an
unfinished cycle's eventual duration. This is research, never a live selector.
"""
from collections import deque
from statistics import median

from research.true_zero_cycles import ZeroCycles, model


class QuantityRateCycles(ZeroCycles):
    def __init__(self,crosses):
        super().__init__(crosses)
        self.rates=deque(maxlen=64)
        self.segment=deque(maxlen=128)
        self.rate_batch=None

    def add(self,obs):
        prev=self.last
        valid=(prev is not None and obs.epoch>prev.epoch
               and obs.source==prev.source
               and not self.crosses(prev.epoch,obs.epoch))
        if not valid:
            self.rate_batch=None
            self.segment.clear()
        elif prev.quantity==0 and obs.quantity>0:
            self.rate_batch=(obs.epoch,obs.quantity)
            self.segment.clear()
        elif obs.quantity>prev.quantity:
            # Positive top-ups are not clean zero-to-zero batches.
            self.rate_batch=None
            self.segment.clear()
        elif prev.quantity>0 and obs.quantity==0:
            if self.rate_batch is not None:
                start,quantity=self.rate_batch
                if obs.epoch>start:
                    self.rates.append(quantity/(obs.epoch-start))
            self.rate_batch=None
            self.segment.clear()
        if obs.quantity>0:
            self.segment.append(obs)
        super().add(obs)

    def _current_rates(self,asof):
        if not self.rates or self.last is None or self.last.quantity<=0:
            return list(self.rates)
        # At least three observed drops over >=3 minutes. Include elapsed
        # no-change time to issuance; do not extrapolate an old burst forever.
        recent=[o for o in self.segment if asof-600<=o.epoch<=asof]
        if len(recent)<4 or asof-self.last.epoch>180:
            return list(self.rates)
        first=recent[0]
        elapsed=asof-first.epoch
        drops=sum(a.quantity>b.quantity for a,b in zip(recent,recent[1:]))
        if elapsed<180 or drops<3 or first.quantity<=self.last.quantity:
            return list(self.rates)
        observed=(first.quantity-self.last.quantity)/elapsed
        center=median(self.rates)
        # Fixed shrinkage and cap chosen before evaluation, not per-item tuning.
        ratio=max(.25,min(4.,observed/center))
        factor=(1.+ratio)/2.
        return [r*factor for r in self.rates]

    def _physical_state(self,asof):
        state=dict(super()._physical_state(asof))
        for field in ('stocked_durations','depleted_durations'):
            state[field]=state[field][-64:]
        if len(self.rates)<model.MIN_BOUNDED or not self.restock_quantities:
            return state
        batch=median(self.restock_quantities[-64:])
        durations=[max(1,round(batch/r)) for r in self.rates]
        if state['phase']=='HIGH' and state['phase_onset'] is not None:
            age=asof-state['phase_onset']
            # The event builder conditions on age. Encode current quantity's
            # residual, preserving the separate completed future lifetimes.
            state['stocked_durations']=[age+max(1,round(self.last.quantity/r))
                                        for r in self._current_rates(asof)]
            state['future_stocked_durations']=durations
        else:
            state['stocked_durations']=durations
        return state

    def _available_history(self):
        if len(self.rates)<model.MIN_BOUNDED or not self.restock_quantities:
            return self.available_durations[-64:]
        quantity=median(self.restock_quantities[-64:])
        return [max(1,round(max(0,quantity-29)/r)) for r in self.rates]

    def _current_available(self,asof,availability):
        if len(self.rates)<model.MIN_BOUNDED:
            return super()._current_available(asof,availability)
        remaining=[max(1,round(max(0,self.last.quantity-29)/r))
                   for r in self._current_rates(asof)]
        return model.phase_quantiles(remaining)

    def forecast(self,key,*,asof):
        result=super().forecast(key,asof=asof)
        result.update(model_name='true_zero_quantity_rate_v1',
                      cycle_window='true_zero_rate_recent64',
                      completed_rate_samples=len(self.rates),
                      rate_units='sampled_stock_units_per_second',
                      rate_model_is_calibrated=False)
        return result
