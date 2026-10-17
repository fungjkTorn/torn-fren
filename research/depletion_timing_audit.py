"""True-zero depletion and separate >=30 availability-loss scoring."""
from deploy.scripts import v163_readonly_event_first_preview as model


def observed_availability_losses(rows, crosses):
    events=[]
    for a,b in zip(rows,rows[1:]):
        if (a.epoch<b.epoch and a.quantity>=30>b.quantity and a.source==b.source
            and not crosses(a.epoch,b.epoch)):
            events.append(b.epoch)
    return events


def predicted_availability_losses(stream, *, start, end):
    windows=list(stream.get('restock_events') or [])
    if stream.get('current_stock_window'):
        windows.append(stream['current_stock_window'])
    return sorted({w['predicted_stock_below_30_epoch'] for w in windows
                   if type(w.get('predicted_stock_below_30_epoch')) is int
                   and start<w['predicted_stock_below_30_epoch']<=end})


def count_events(counts,predicted,observed):
    counts['observed']+=len(observed);counts['forecast']+=len(predicted)
    for tolerance in (15,60,600):
        result=model.match_events(predicted,observed,tolerance=tolerance)
        counts[f'matched_{tolerance}s']+=result['matched']
        counts[f'matched_absolute_error_sum_{tolerance}s']+=result['sum_absolute_timing_error_seconds']


def observed_depletions(rows, crosses):
    return [b.epoch for a,b in zip(rows,rows[1:])
            if a.epoch<b.epoch and a.quantity>0 and b.quantity==0
            and a.source==b.source and not crosses(a.epoch,b.epoch)]


def observed_restocks(rows, crosses):
    return [b.epoch for a,b in zip(rows,rows[1:])
            if a.epoch<b.epoch and a.quantity==0 and b.quantity>0
            and a.source==b.source and not crosses(a.epoch,b.epoch)]


def predicted_depletions(stream, *, start, end):
    windows=list(stream.get('true_depletion_events') or [])
    windows+=list(stream.get('restock_events') or [])
    if stream.get('current_stock_window'):
        windows.append(stream['current_stock_window'])
    return sorted({w['predicted_true_depletion_epoch'] for w in windows
                   if type(w.get('predicted_true_depletion_epoch')) is int
                   and start<w['predicted_true_depletion_epoch']<=end})
