"""Causal stocked-window repair and provisional-low advice guard.

No price, flight, model fitting or history-retention choices live here. Caller
supplies its existing fitting window and the observations known at issue time.
"""
from bisect import bisect_left,bisect_right
from statistics import median


def provisional_low_guard(clock, observations):
    """Hold new advice while a brief low is still awaiting classification."""
    if not clock.pending:
        return False
    low=clock.pending[0];prior=clock.bulk.last
    onset=clock.bulk.state().get('phase_onset')
    if onset is not None and 0<=low.epoch-onset<=180:
        return True
    if prior is None or low.epoch<=prior.epoch:
        return False
    points=[o for o in observations if max(onset or prior.epoch-600,prior.epoch-600)<=o.epoch<=prior.epoch and o.source==prior.source and o.quantity>30]
    if len(points)<3 or points[-1].epoch-points[0].epoch<120:
        return False
    if any(b.quantity>a.quantity+max(30,.05*a.quantity)for a,b in zip(points,points[1:])):
        return False
    slopes=[(a.quantity-b.quantity)/(b.epoch-a.epoch)for i,a in enumerate(points)for b in points[i+1:]if b.epoch-a.epoch>=30 and a.quantity>=b.quantity]
    if not slopes:
        return False
    expected=median(slopes)*(low.epoch-prior.epoch)
    return prior.quantity-low.quantity>max(30,4*expected)


def repaired_stocked_windows(observations, *, asof, since, retained_windows,
                            crosses_gap, fresh, verified_through, floor=None):
    """Replace closed post-regime windows; retain earlier incumbent history.

    Includes small batches. A brief return is merged only if its quantity is
    compatible with the preceding decline. No observed stock rows are deleted.
    """
    active=None;pending=None;last=None;records=[]
    def close():
        nonlocal active,pending
        if active and active['valid'] and active['start']>=since:
            if floor is None or active['start']>=floor:
                records.append((active['start'],pending))
        active=None;pending=None
    for obs in observations:
        at,q,source=obs.epoch,obs.quantity,obs.source
        if at>asof:
            raise ValueError('Future observation in stocked-window repair')
        if pending is not None and at-pending>180:
            close()
        if active and last and crosses_gap(last.epoch,at):
            active['valid']=False
        if q>=31:
            if pending is not None:
                if q<=active['last_quantity']+max(30,round(active['last_quantity']*.05)):
                    pending=None
                else:
                    close()
            if active is None:
                valid=last is not None and last.quantity<=30 and fresh(at) and not crosses_gap(last.epoch,at)
                if valid and last.source!=source:
                    bound=verified_through(last,obs)
                    valid=bound is not None and 0<=at-bound<=180
                active={'start':at,'valid':valid,'last_quantity':q}
            active['last_quantity']=q
        elif active and pending is None:
            pending=at;active['valid'] &= fresh(at)
        last=obs
    if pending is not None and asof-pending>180:
        close()
    assert all(a<b<=asof for a,b in records)
    return [(a,b)for a,b in retained_windows if a<since]+records
