"""V144: bounded read-only 24-hour stock transition and V128 abstention diagnosis.

The existence of stock restocks and the existence of a V128 scored ARRIVAL
are very different questions. Distinguish:
  - observed crossings to >=30, vs 0->positive, vs provider/gap ambiguity;
  - successful as-issued V128 records vs source/status reasons for abstaining;
  - observed cadence (only from >=3 clean crossings), not a restock promise.

No source/prediction model fitting, DB creation, network, gameplay or writes.
Print bounded aggregate per-item evidence, never item raw history or secrets.
Default DB paths are the *existing* private research/collector paths.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from research.v128_full24_earliest_shadow import (
    COLLECTOR, SIDECAR, exact_roster,
)

DAY = 86400
MAX_ROWS_PER_ITEM = 10000
MAX_ISSUES = 12000


def readonly(path):
    f = Path(path).resolve(strict=True)
    if not f.is_file():
        raise ValueError("missing database")
    uri = f.as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=10)
    con.execute("PRAGMA query_only=ON")
    return con


def _crosses_gap(gaps, a, b):
    return any(start <= b and (end is None or end >= a)
               for start,end in gaps)


def event_diagnostic(observations, *, asof, earliest, gaps=()):
    """Pure classification of actual observed stock deltas, no assumptions.

    A provider switch can produce an apparent 0->stock change; count it as
    AMBIGUOUS, not as a certified within-source restock. A source state still
    above 30 may never cross the threshold even if quantity replenishes.
    """
    clean = []
    zero_to_positive = 0
    replenished_30 = 0
    depleted_30 = 0
    ambiguous_replenish = 0
    provider_switches = 0
    gap_crossings = 0
    # We retain the immediately preceding observation to classify a
    # transition across the start of the requested 24-hour window.
    before = None
    recent = 0
    clean_30_epochs = []
    last = None
    for e,q,source in observations:
        if type(e) is not int or type(q) is not int or q < 0 or not source:
            continue
        if e > asof:
            raise ValueError("future observation in audit")
        if last is not None and e <= last[0]:
            raise ValueError("unordered timestamps")
        if e < earliest:
            before = (e,q,source)
            last = before
            continue
        recent += 1
        if last is not None:
            old_t, old_q, old_source = last
            provider_changed = source != old_source
            gap = _crosses_gap(gaps,old_t,e)
            provider_switches += int(provider_changed)
            gap_crossings += int(gap)
            fresh = not provider_changed and not gap
            if old_q == 0 and q > 0:
                zero_to_positive += int(fresh)
            if old_q < 30 and q >= 30:
                if fresh:
                    replenished_30 += 1
                    clean_30_epochs.append(e)
                else:
                    ambiguous_replenish += 1
            if old_q >= 30 and q < 30 and fresh:
                depleted_30 += 1
        last = (e,q,source)
    # No reliable cadence from a couple of events or unknown provider gap.
    spacings = [b-a for a,b in zip(clean_30_epochs, clean_30_epochs[1:])]
    cadence = int(statistics.median(spacings)) if len(spacings)>=2 else None
    return {
        "recent_observations":recent,
        "has_baseline_before_window":before is not None,
        "observed_clean_crossings_to_30":replenished_30,
        "observed_clean_zero_to_positive":zero_to_positive,
        "observed_clean_drops_below_30":depleted_30,
        "ambiguous_crossings_to_30_source_or_gap":ambiguous_replenish,
        "provider_switch_count":provider_switches,
        "collector_gap_crossings":gap_crossings,
        "most_recent_clean_30_crossing_epoch": (
            clean_30_epochs[-1] if clean_30_epochs else None),
        "median_between_clean_30_crossings_seconds":cadence,
        "cadence_is_based_on_three_or_more_events":cadence is not None,
        "no_stored_change_means_no_game_restock":False,
        "country_source_freshness_verified":False,
    }


def snapshot(conn, country, item, *, asof, earliest):
    prev=conn.execute(
        """SELECT timestamp,quantity,source FROM stock_history
           WHERE country=? AND lower(item_name)=lower(?)
             AND timestamp<?
           ORDER BY timestamp DESC,id DESC LIMIT 1""",
        (country,item,earliest)).fetchone()
    rows=conn.execute(
        """SELECT timestamp,quantity,source FROM stock_history
           WHERE country=? AND lower(item_name)=lower(?)
             AND timestamp>=? AND timestamp<=?
           ORDER BY timestamp ASC,id ASC LIMIT ?""",
        (country,item,earliest,asof,MAX_ROWS_PER_ITEM+1)).fetchall()
    if len(rows)>MAX_ROWS_PER_ITEM:
        raise ValueError(f"too many recent rows for {country}:{item}")
    # Simultaneous collector deltas can exist; keep the last state for a
    # timestamp, matching ORDER BY timestamp DESC, id DESC as-of lookup.
    collected={}
    if prev:
        collected[int(prev[0])]=(int(prev[0]),int(prev[1]),str(prev[2]))
    for t,q,source in rows:
        if t is None or q is None or source is None:
            continue
        collected[int(t)]=(int(t),int(q),str(source))
    return [collected[t] for t in sorted(collected)]


def diagnose(*,collector=COLLECTOR, sidecar=SIDECAR, now=None, days=1):
    if type(days) is not int or days!=1:
        raise ValueError("audit intentionally limited to one day")
    epoch=int(time.time()) if now is None else now
    if type(epoch) is not int or epoch<=DAY:
        raise ValueError("invalid asof timestamp")
    beginning=epoch-DAY
    keys=exact_roster()
    if Path(collector).resolve(strict=True)==Path(sidecar).resolve(strict=True):
        raise ValueError("collector and sidecar must be different")
    with closing(readonly(collector)) as db, closing(readonly(sidecar)) as v128:
        gaps=db.execute(
            """SELECT start_timestamp,end_timestamp
               FROM collection_gaps
               WHERE start_timestamp<=?
                 AND (end_timestamp IS NULL OR end_timestamp>=?)
               ORDER BY start_timestamp""",
            (epoch,beginning-DAY)).fetchall()
        issues=v128.execute(
            """SELECT item_key,issued_epoch,source_status,decision_status
               FROM v128_issued
               WHERE issued_epoch>=? AND issued_epoch<=?
               ORDER BY issued_epoch,item_key LIMIT ?""",
            (beginning,epoch,MAX_ISSUES+1)).fetchall()
        if len(issues)>MAX_ISSUES:
            raise ValueError("too many recent private shadow records")
        issue_counts=defaultdict(Counter)
        latest={}
        for key,issued,source_status,decision_status in issues:
            if key not in keys:
                continue
            issue_counts[key]["ticks"]+=1
            issue_counts[key]["decision:"+str(decision_status)]+=1
            issue_counts[key]["source:"+str(source_status)]+=1
            latest[key]={
                "issued_epoch":int(issued),
                "source_status":str(source_status),
                "decision_status":str(decision_status),
            }
        result={}
        for key in sorted(keys):
            country,item=key.split(":",1)
            rows=snapshot(db,country,item,asof=epoch,earliest=beginning)
            observed=event_diagnostic(
                rows,asof=epoch,earliest=beginning,gaps=gaps)
            counts=issue_counts[key]
            abstentions=sum(n for label,n in counts.items()
                            if label.startswith("decision:ABSTAIN_")
                            or label in (
                                "decision:NO_SUPPORTED_DEPARTURE_WITHIN_EIGHT_HOURS",))
            result[key]={
                **observed,
                "v128_issue_ticks_last_day":counts["ticks"],
                "v128_abstained_or_unsupported_ticks":abstentions,
                "v128_accepted_departure_ticks":(
                    counts["ticks"]-abstentions),
                "v128_source_status_counts":dict(sorted(
                    (key.removeprefix("source:"),val)
                    for key,val in counts.items()
                    if key.startswith("source:"))),
                "v128_decision_status_counts":dict(sorted(
                    (key.removeprefix("decision:"),val)
                    for key,val in counts.items()
                    if key.startswith("decision:"))),
                "last_v128_issue":latest.get(key),
                "uncalibrated_arrival_score_not_a_restock_count":True,
            }
    return {
        "status":"READ_ONLY_FOREIGN_RESTOCK_OBSERVABILITY",
        "asof_epoch":epoch,"lookback_seconds":DAY,
        "exact_item_count":len(result),
        "all24_present":len(result)==24,
        "collector_only_observed_changes_not_true_shop_restock_events":True,
        "measured_restocks_can_be_underobserved_or_provider_ambiguous":True,
        "databases_modified":False,
        "items":result,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collector",type=Path,default=COLLECTOR)
    parser.add_argument("--sidecar",type=Path,default=SIDECAR)
    parser.add_argument("--asof-epoch",type=int,default=None)
    args=parser.parse_args()
    print(json.dumps(diagnose(collector=args.collector,sidecar=args.sidecar,
                              now=args.asof_epoch),sort_keys=True,indent=2))


if __name__ == "__main__":
    main()
