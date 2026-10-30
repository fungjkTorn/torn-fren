"""Observed item-specific refill/reset signatures; never infer purchases.

Profiles are fixed using history BEFORE tracking starts. A log-quantity mixture
separates the compact normal-refill population from small/broad sellback tails.
Every bound and training sample count is exposed for operational review.
"""
from collections import Counter
import bisect
import math


def normal_quantity_group(quantities):
    """Peel distinct lower populations until the normal band is stable.

    Isolating a tiny 10-unit cluster must not prevent a separate 400-unit
    sellback tail from being separated from recurring 10,000-unit refills.
    The same separation guard applies at every step, including variable bands.
    """
    group=quantities;excluded=0
    while True:
        bulk,removed=_quantity_split(group)
        excluded+=removed
        if not removed:return bulk,excluded
        group=bulk


def _quantity_split(quantities):
    """Separate a small-quantity cluster from normal refills in log space.

    A decade of center separation OR a broad lower tail with tenfold greater
    log variance and twofold center separation is required; an ordinary
    variable refill band (e.g. 1000–2500) must not be split in half.
    Bounds are actual observed quantities, not extrapolated Gaussian tails.
    """
    x=[math.log(q) for q in quantities]
    means=[min(x),max(x)];variances=[1.,1.];weights=[.2,.8]
    responsibility=[]
    for _ in range(80):
        responsibility=[]
        for value in x:
            logs=[math.log(max(weights[k],1e-12))-.5*math.log(variances[k])-(value-means[k])**2/(2*variances[k]) for k in (0,1)]
            maximum=max(logs);p=[math.exp(v-maximum) for v in logs];total=sum(p)
            responsibility.append([v/total for v in p])
        for k in (0,1):
            mass=sum(r[k] for r in responsibility)
            if mass<1e-8:continue
            means[k]=sum(r[k]*value for r,value in zip(responsibility,x))/mass
            variances[k]=max(1e-4,sum(r[k]*(value-means[k])**2 for r,value in zip(responsibility,x))/mass)
            weights[k]=mass/len(x)
    upper=0 if means[0]>means[1] else 1
    lower=1-upper;separation=means[upper]-means[lower]
    distinct=separation>=math.log(10) or (separation>=math.log(2) and variances[lower]>=10*variances[upper])
    if not distinct:return quantities,0
    bulk=[q for q,r in zip(quantities,responsibility) if r[upper]>=.5]
    return (bulk,len(quantities)-len(bulk)) if len(bulk)>=5 else (quantities,0)


def clean_pairs(rows,gaps):
    starts=[];ends=[];maximum=-1
    for lo,hi in sorted(gaps):
        starts.append(lo);maximum=max(maximum,hi if hi is not None else 2**63-1);ends.append(maximum)
    for a,b in zip(rows,rows[1:]):
        if b[0]<=a[0] or a[2]!=b[2]:continue
        index=bisect.bisect_right(starts,b[0])-1
        if index>=0 and ends[index]>=a[0]:continue
        yield a,b


def learn(rows,gaps,cutoff):
    history=[r for r in rows if r[0]<cutoff]
    quantities=sorted(b[1] for a,b in clean_pairs(history,gaps) if a[1]==0<b[1])
    result={'training_cutoff':cutoff,'zero_refill_samples':len(quantities),
            'status':'INSUFFICIENT_HISTORY','normal_min':None,'normal_max':None,
            'reset_base':None,'reset_training_samples':0}
    if len(quantities)<5:return result
    bulk,split=normal_quantity_group(quantities)
    if min(bulk)<=30:return dict(result,status='AMBIGUOUS_SMALL_REFILL_POPULATION')
    base=Counter(bulk).most_common(1)[0][0]
    resets=sum(a[1]>max(bulk) and b[1]==base for a,b in clean_pairs(history,gaps))
    result.update(status='LEARNED',normal_min=min(bulk),normal_max=max(bulk),
        normal_samples=len(bulk),excluded_small_samples=split,
        reset_base=base if resets>=3 else None,reset_training_samples=resets,
        reset_candidate_base=base,classification_is_observational=True)
    result['method']='ITERATED_LOG_QUANTITY_CLUSTER_WITH_OBSERVED_RANGE'
    return result


def events(rows,gaps,profile):
    if profile['status']!='LEARNED':return []
    lo,hi=profile['normal_min'],profile['normal_max'];base=profile['reset_base'];out=[]
    for a,b in clean_pairs(rows,gaps):
        kind=None
        if a[1]==0 and lo<=b[1]<=hi:kind='NORMAL_ZERO_REFILL'
        elif a[1]>0 and lo<=b[1]<=hi and lo<=b[1]-a[1]<=hi:kind='IN_STOCK_BULK_REFILL'
        elif base is not None and a[1]>hi and b[1]==base:kind='SURPLUS_TO_BASE_RESET'
        if kind:out.append({'epoch':b[0],'previous_epoch':a[0],'before':a[1],
            'quantity':b[1],'kind':kind,'provider':b[2]})
    return out
