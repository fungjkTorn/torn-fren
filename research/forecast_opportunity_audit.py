"""Retrospective research-only opportunity identity audit, not native inference.

Match the event forecaster's provider-continuous >30 phase semantics: switching
providers while both rows agree on availability does not create a new opening
or erase an observed one. A conflicting switch still makes identity unknown.
Never change the saved landing grade or choose the best forecast revision.
"""
from services.first_release_evidence import TargetIndex

POLICY='PROVIDER_CONTINUOUS_OBSERVED_ORDINAL_FIRST_ISSUE_V1'


class ProviderContinuousTargetIndex(TargetIndex):
    def __init__(self,rows,gaps):
        super().__init__(rows,gaps)
        self.switches=[b[0] for a,b in zip(rows,rows[1:])
            if a[2]!=b[2] and (a[1]>30)!=(b[1]>30)]


def first_forecasts(records,index):
    """Return earliest issued forecast per physical observed ordinal target."""
    grouped={};unmatched=[]
    for record in sorted(records,key=lambda r:r['issued']):
        row=record.get('row') or {};decision=row.get('decision') or {}
        if type(decision.get('estimated_departure_epoch')) is not int:continue
        target=index.target(row)
        if target is None:unmatched.append(record)
        else:grouped.setdefault(target['epoch'],(record,target))
    return grouped,unmatched
