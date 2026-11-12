"""Causal country freshness selection; never supplies item availability."""
from bisect import bisect_left, bisect_right


class ProviderFreshness:
    def __init__(self, receipts, maximum_age=180):
        # Rows: receipt time, provider, upstream country update, clock status.
        self.rows = sorted(receipts, key=lambda r: r[0])
        self.times = [r[0] for r in self.rows]
        self.maximum_age = maximum_age

    def evidence(self, at):
        age = self.maximum_age
        latest = {}
        for row in self.rows[bisect_left(self.times, at-age):bisect_right(self.times, at)]:
            latest[row[1]] = row
        valid = [r for r in latest.values()
                 if r[3] == 'REPORTED' and r[2] is not None
                 and 0 <= at-r[2] <= age and 0 <= at-r[0] <= age]
        return sorted(valid, key=lambda r: (r[2], r[0]), reverse=True)

    def fresh(self, at):
        return bool(self.evidence(at))


def receipt_for(db,country,issued,asof=None):
    at=issued if asof is None else asof
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='country_stock_observations'").fetchone():return None
    rows=db.execute('SELECT received_epoch,source,country_update_epoch,clock_status FROM country_stock_observations WHERE country=? AND received_epoch BETWEEN ? AND ? ORDER BY received_epoch,id',(country,at-180,issued)).fetchall()
    good=ProviderFreshness(rows).evidence(at)
    if good:
        t,source,u,status=good[0]
        return t,u,status
    # Preserve unavailable status when reports exist but none is fresh.
    r=db.execute('SELECT received_epoch,country_update_epoch,clock_status FROM country_stock_observations WHERE country=? AND received_epoch<=? ORDER BY received_epoch DESC,id DESC LIMIT 1',(country,issued)).fetchone()
    return r if r else (0,None,'MISSING')
