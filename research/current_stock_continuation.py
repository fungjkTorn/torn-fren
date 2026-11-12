"""Research-only UK long-phase continuation, retaining native timing identity.

An ongoing availability phase exceeding all completed lifetimes does not imply
stock is gone. Estimate its current buying window from quantity depletion rates
in all causal history. Never reset the phase clock or invent a future restock.
"""
from copy import deepcopy
import math
import statistics
from services.restock_signatures import clean_pairs,learn,events
from deploy.scripts.v163_readonly_event_first_preview import _window

POLICY='UK_CURRENT_QUANTITY_CONTINUATION_V1'


def extend_current_stock(forecast,rows,gaps,asof):
    if forecast['item_key']!='uni:Xanax':return forecast
    if forecast.get('current_stock_window') is not None:return forecast
    if forecast.get('status') not in ('CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS','INSUFFICIENT_BOUNDED_RESTOCK_HISTORY'):
        return forecast
    quantity=forecast.get('observed_current_quantity')
    if type(quantity) is not int or quantity<=30:return forecast
    # _read_item provides causal observation objects; the function also accepts ordinary
    # observation tuples for boundary tests. Source freshness is checked before
    # this hook and country freshness remains mandatory at issuance/arrival.
    def observation(r):
        return (r.epoch,r.quantity,r.source) if hasattr(r,"epoch") else (int(r[0]),int(r[1]),r[2])
    history=[r for r in map(observation,rows) if r[0]<=asof]
    if not history:return forecast
    signature=learn(history,gaps,asof)
    reset_times={e['epoch'] for e in events(history,gaps,signature) if e['kind']=='SURPLUS_TO_BASE_RESET'}
    rates=[(a[1]-b[1])/(b[0]-a[0]) for a,b in clean_pairs(history,gaps)
        if a[1]>b[1] and b[0] not in reset_times]
    if len(rates)<3:return forecast
    ordered=sorted(rates)
    middle=statistics.median(ordered)
    # These are empirical bounds, not calibrated confidence intervals.
    def rate_quantile(p):return ordered[max(0,math.ceil(len(ordered)*p)-1)]
    duration=max(1,math.ceil((quantity-30)/middle))
    early=max(1,math.ceil((quantity-30)/rate_quantile(.75)))
    late=max(1,math.ceil((quantity-30)/rate_quantile(.25)))
    out=deepcopy(forecast)
    out['current_stock_window']=_window('uni:Xanax',asof,asof,duration,asof,asof,early)
    out['current_stock_continuation']={'policy':POLICY,'original_event_status':forecast['status'],
        'training_policy':'ALL_AVAILABLE_CAUSAL_HISTORY_NO_ROLLING_LOOKBACK',
        'depletion_rate_samples':len(rates),'median_loss_per_second':middle,
        'quantity_at_issue':quantity,'estimated_below_31_epoch':asof+duration,
        'early_below_31_epoch':asof+early,'late_below_31_epoch':asof+late,
        'qualified_resets_excluded':len(reset_times),'phase_onset_reset':False,
        'future_restocks_invented':False,'calibration_state':'UNCALIBRATED'}
    out['status']='EVENT_TIMELINE_FORECAST_AVAILABLE'
    return out
