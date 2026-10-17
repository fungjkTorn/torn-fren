"""Resource-aware research cadence, never a gameplay automation schedule.

Prospective actionable plans are always due in 300 seconds; cold/rare items
may be observed continuously by the stock poller without heavy re-inference.
"""
STEP=300
MAX_WATCH=3600


def next_due_seconds(*, worker_status, active=False, stock_changed=False,
                     median_restock_seconds=None):
    if active or worker_status=="RESEARCH_PROPOSAL_ONLY":
        return STEP
    if stock_changed:
        return STEP
    if worker_status in {"NO_RECOMMENDATION","INSUFFICIENT_HISTORY",
                         "COLLECTOR_STALE_OR_NO_HEARTBEAT","NO_OBSERVATIONS"}:
        if median_restock_seconds is not None and median_restock_seconds >= 86400:
            return MAX_WATCH
        return 1800
    return STEP
