"""Classify frozen failed arrivals by nearest observed zero/restock boundary.

Zero depletion is >0 -> 0, refill is 0 -> >0. Purchase eligibility remains
>30. Unknown boundaries and positive-but-insufficient stock stay explicit.
"""
import bisect
from collections import Counter
from statistics import median


def boundary_index(rows,gaps):
    zeros=[];refills=[];conflicts=[]
    for a,b in zip(rows,rows[1:]):
        if a[2]!=b[2] and (a[1]==0)!=(b[1]==0):conflicts.append(b[0])
        if a[2]!=b[2] or b[0]<=a[0]:continue
        if any(lo<=b[0] and (hi is None or hi>=a[0]) for lo,hi in gaps):continue
        if a[1]>0 and b[1]==0:zeros.append((b[0],a[0]))
        if a[1]==0 and b[1]>0:refills.append((b[0],a[0]))
    return zeros,refills,conflicts


def classify(arrival,outcome,rows,gaps,*,index=None):
    times=[r[0] for r in rows]
    i=bisect.bisect_right(times,arrival)-1
    if i<0:return {'classification':'UNKNOWN','reason':'no item state'}
    quantities=[outcome.get('pre_quantity'),outcome.get('post_quantity')]
    if any(q is None for q in quantities):return {'classification':'UNKNOWN','reason':'no landing bracket quantities'}
    if all(q>0 for q in quantities):
        return {'classification':'POSITIVE_STOCK_AT_OR_BELOW_30','quantities':quantities}
    if any(q>0 for q in quantities):return {'classification':'UNKNOWN_ZERO_BOUNDARY','quantities':quantities}
    zeros,refills,conflicts = boundary_index(rows,gaps) if index is None else index
    previous=next((b for b in reversed(zeros) if b[0]<=arrival),None)
    following=next((b for b in refills if b[0]>arrival),None)
    result={'classification':'UNKNOWN','previous_zero_epoch':previous[0] if previous else None,
            'next_restock_epoch':following[0] if following else None}
    if not previous or not following:return dict(result,reason='both surrounding boundaries required')
    if any(previous[0]<=t<=following[0] for t in conflicts) or any(lo<=following[0] and (hi is None or hi>=previous[0]) for lo,hi in gaps):
        return dict(result,reason='provider conflict or gap between boundaries')
    late=(arrival-previous[0])/60;early=(following[0]-arrival)/60
    result.update(minutes_after_zero=late,minutes_before_restock=early,
        zero_boundary_interval=[previous[1],previous[0]],restock_boundary_interval=[following[1],following[0]],
        classification='LATE' if late<early else 'EARLY' if early<late else 'TIE')
    return result


def summarize(records):
    counts=Counter(r['classification'] for r in records)
    return {'counts':dict(counts),'median_late_minutes':median([r['minutes_after_zero'] for r in records if r['classification']=='LATE']) if counts['LATE'] else None,
        'median_early_minutes':median([r['minutes_before_restock'] for r in records if r['classification']=='EARLY']) if counts['EARLY'] else None}
