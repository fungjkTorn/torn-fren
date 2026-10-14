"""Physical inventory clock: positive stock -> exactly zero -> restock.

The >=30 availability window is trained separately and never starts the
empty/restock clock. All training phases must finish before issuance.
"""
from deploy.scripts import v163_readonly_event_first_preview as model


class ZeroCycles:
    def __init__(self,crosses):
        self.crosses=crosses
        self.physical=model._ReplayPhases(crosses)
        self.availability=model._ReplayPhases(crosses)
        self.last=None
        self.batch_start=None
        self.batch_quantity=None
        self.first_unavailable=None
        self.availability_valid=True
        self.available_durations=[]
        self.restock_quantities=[]
        self.zero_onset_bracket=None

    def add(self,obs):
        prev=self.last
        positive=obs.quantity>0
        invalid=prev is None or obs.epoch<=prev.epoch or self.crosses(prev.epoch,obs.epoch)
        if prev is not None and obs.source!=prev.source and positive!=(prev.quantity>0):
            invalid=True
        if invalid:
            self.batch_start=self.batch_quantity=self.first_unavailable=None
            self.availability_valid=True
            self.zero_onset_bracket=None
        elif prev.quantity==0 and positive:
            self.restock_quantities.append(obs.quantity)
            self.batch_start=obs.epoch
            self.batch_quantity=obs.quantity
            self.first_unavailable=None
            self.availability_valid=True
        elif self.batch_start is not None:
            if (prev.quantity>=30)!=(obs.quantity>=30) and obs.source!=prev.source:
                self.availability_valid=False
            if prev.quantity>=30>obs.quantity and self.first_unavailable is None:
                self.first_unavailable=obs.epoch
            if prev.quantity>0 and obs.quantity==0:
                self.zero_onset_bracket={'after_epoch':prev.epoch,'by_epoch':obs.epoch}
                if (self.batch_quantity>=30 and self.first_unavailable is not None
                    and self.availability_valid):
                    duration=self.first_unavailable-self.batch_start
                    if duration>0:self.available_durations.append(duration)
                self.batch_start=self.batch_quantity=self.first_unavailable=None
        # Explicit binary encoding lets the established continuity tracker
        # identify physical positive/zero phases without altering its legacy
        # >=30 baseline. Keep the real last quantity in the external contract.
        self.physical.add(model.OBS(obs.epoch,200 if positive else 0,obs.source))
        self.availability.add(obs)
        self.last=obs

    def forecast(self,key,*,asof):
        if self.last is not None and self.last.epoch>asof:
            raise ValueError('future physical stock observation')
        state=self.physical.asof()
        state['last_observation']=self.last
        result=model.predict_events(key,state,asof=asof)
        result.update(model_name='true_zero_anchored_cycles_v1',cycle_window='true_zero_all',
            depletion_stock_quantity=0,arrival_stock_threshold=30,
            restock_timer_anchor='FIRST_OBSERVED_ZERO_AFTER_POSITIVE_STOCK',
            physical_phase_onset_epoch=state['phase_onset'],
            physical_inventory_phase={'HIGH':'NONZERO','LOW':'EMPTY'}.get(state['phase'],'UNKNOWN'),
            availability_phase=self.availability.asof()['phase'],
            observed_zero_epoch=state['phase_onset'] if state['phase']=='LOW' else None,
            observed_zero_onset_bracket=self.zero_onset_bracket if state['phase']=='LOW' else None,
            true_depletion_events=[],true_restock_events=[],
            legacy_threshold_phase_clock_used=False)
        # V163's internal end fields represent PHYSICAL positive->zero in
        # this explicit binary track. Do not expose those as >=30 end clocks.
        raw_events=result['restock_events']
        physical_current=result['current_stock_window']
        result['restock_events']=[];result['current_stock_window']=None
        result['forecast_event_count']=0
        result['physical_restock_event_count']=len(raw_events)
        result['currently_supported_departures']=0
        result['unreachable_restock_events']=0
        if physical_current:
            result['true_depletion_events'].append({
                'predicted_true_depletion_epoch':physical_current['predicted_stock_below_30_epoch']})
        for event in raw_events:
            result['true_restock_events'].append({
                'predicted_restock_epoch':event['predicted_restock_epoch'],
                'restock_early_epoch':event['restock_early_epoch'],
                'restock_late_epoch':event['restock_late_epoch'],
                'predicted_true_depletion_epoch':event['predicted_stock_below_30_epoch']})
            result['true_depletion_events'].append({
                'predicted_true_depletion_epoch':event['predicted_stock_below_30_epoch']})
        if result['status']!='EVENT_TIMELINE_FORECAST_AVAILABLE':
            return result
        if self.restock_quantities:
            result['median_observed_restock_quantity']=model.quantile(self.restock_quantities,.5)
        if result.get('median_observed_restock_quantity',0)<30:
            result['status']='RESTOCK_QUANTITY_TARGET_UNSUPPORTED'
            return result
        if len(self.available_durations)<model.MIN_BOUNDED:
            result['status']='INSUFFICIENT_SEPARATE_30_ITEM_AVAILABILITY_HISTORY'
            return result
        available=model.phase_quantiles(self.available_durations)
        for event in raw_events:
            start=event['predicted_restock_epoch']
            zero=event['predicted_stock_below_30_epoch']
            lifetime=min(available['middle'],zero-start)
            window=model._window(key,asof,start,lifetime,event['restock_early_epoch'],
                                 event['restock_late_epoch'],min(available['early'],lifetime))
            window.update(predicted_true_depletion_epoch=zero,
                          event_index=event['event_index'])
            result['restock_events'].append(window)
        # Residual 1..29 stock never creates a current >=30 opportunity.
        a=self.availability.asof()
        if self.last is not None and self.last.quantity>=30 and a['phase_onset'] is not None:
            remaining=model.phase_quantiles(self.available_durations,age=asof-a['phase_onset'])
            if remaining and physical_current:
                zero=physical_current['predicted_stock_below_30_epoch']
                duration=min(remaining['middle'],zero-asof)
                result['current_stock_window']=model._window(key,asof,asof,duration,
                    asof,asof,min(remaining['early'],duration))
                result['current_stock_window']['predicted_true_depletion_epoch']=zero
        result['forecast_event_count']=len(result['restock_events'])
        result['currently_supported_departures']=sum(w['expected_departure_epoch'] is not None for w in result['restock_events'])
        result['unreachable_restock_events']=sum(w['expected_departure_epoch'] is None for w in result['restock_events'])
        return result
