"""Fixed component ablations, all on physical zero-stock clocks."""
from research.true_zero_cycles import ZeroCycles
from research.quantity_rate_cycles import QuantityRateCycles


class ComponentHybrid(QuantityRateCycles):
    MODES=('recent64','current_rate','physical_rate','fast_wait')

    def __init__(self,crosses,mode):
        if mode not in self.MODES:
            raise ValueError('unknown component hybrid')
        super().__init__(crosses)
        self.mode=mode

    def _physical_state(self,asof):
        empirical=dict(ZeroCycles._physical_state(self,asof))
        for field in ('stocked_durations','depleted_durations'):
            empirical[field]=empirical[field][-64:]
        if self.mode=='recent64':
            return empirical
        result=super()._physical_state(asof)
        if self.mode!='physical_rate':
            # Keep quantity/rate only for the CURRENT positive phase. Future
            # stock lifetimes remain empirical completed physical lifetimes.
            if result['phase']=='HIGH':
                result['future_stocked_durations']=empirical['stocked_durations']
            else:
                result['stocked_durations']=empirical['stocked_durations']
        if self.mode=='fast_wait':
            result['depleted_durations']=result['depleted_durations'][-8:]
        return result

    def _available_history(self):
        # Deliberately retain empirical >=30 windows. This isolates whether
        # the rate model helps physical timing while harming buying windows.
        return self.available_durations[-64:]

    def _current_available(self,asof,availability):
        return ZeroCycles._current_available(self,asof,availability)

    def forecast(self,key,*,asof):
        result=super().forecast(key,asof=asof)
        result.update(model_name='true_zero_component_'+self.mode+'_v1',
                      cycle_window='true_zero_component_'+self.mode,
                      buying_window_model='empirical_recent64',
                      physical_component_mode=self.mode)
        return result
