"""V88 read-only forward flight evaluation using *poll-time reconstructed state*.

The collector saves stock_history only on quantity/cost changes, but stores
successful poll_heartbeats every cycle. V76's required two nearby stock-history
rows therefore selects item transitions and can distort success rates.

V88 evaluates *first-as-issued* V75 forecast/arrival targets at the nearest
successful poll heartbeat before and after arrival +10 seconds. It reconstructs
each observed state by carrying forward the latest stock-history record
at/before that heartbeat. Agreement on both sides is evidence, not exact
game state or actual player's purchase opportunity. A successful global poll
does NOT certify fresh per-country YATA update; keep unvalidated labeling.

Also reports same-issuance 'depart immediately' counterfactual, scored on
matched forecast instances only. These instances can share restock cycles.
Never modifies collector, prediction sidecars, or the website.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from research.v76_forward_research_report import (
    V75, SOURCE, MAX_PROXY_EVENTS, eligible, ro, select_unique, strict_samples
)
from research.plushie_champions.common import TRAVEL_SECONDS
from research.v60_private_snapshot_probe import approved_collector_source

GRACE = 10
THRESHOLD = 30
MAX_BRACKET_SECONDS = 180
MAX_STATE_AGE_SECONDS = 24 * 3600
# A heartbeat certifies our fetch/save, not the country-specific provider age.
# Treat very old delta states as unknown rather than recycling week-old stock.
PENDING_BUFFER = 180
OBSERVATION_VERSION = 'poll-state-v2-continuous-bracket'


def observation(conn, country, item, arrival, asof):
    """Classify a predicted arrival with *successful poll snapshots*.

    Persisted per-item stock rows are DELTAS; never demand stock changes
    near arrival as evidence of ordinary unchanged item stock.
    """
    if asof < arrival + GRACE + PENDING_BUFFER:
        return "PENDING", None, {}

    pre = conn.execute(
        """SELECT timestamp,source FROM poll_heartbeats
           WHERE mode='poll-cycle' AND success=1 AND timestamp<=?
           ORDER BY timestamp DESC,id DESC LIMIT 1""", (arrival,)
    ).fetchone()
    post = conn.execute(
        """SELECT timestamp,source FROM poll_heartbeats
           WHERE mode='poll-cycle' AND success=1
             AND timestamp>=? AND timestamp<=?
           ORDER BY timestamp ASC,id ASC LIMIT 1""",
        (arrival+GRACE,asof)
    ).fetchone()
    if pre is None or post is None:
        return "NO_POLL_BRACKET", None, {}
    before = int(pre[0]); after = int(post[0])
    metadata = {"observation_version":OBSERVATION_VERSION,
                "pre_poll_lag_s":arrival-before,
                "post_poll_lag_s":after-(arrival+GRACE),
                "pre_provider":pre[1],"post_provider":post[1]}
    if (arrival-before > MAX_BRACKET_SECONDS
            or after-(arrival+GRACE) > MAX_BRACKET_SECONDS):
        return "POLL_COVERAGE_TOO_SPARSE",None,metadata

    gap = conn.execute(
        """SELECT 1 FROM collection_gaps
           WHERE start_timestamp<=?
             AND COALESCE(end_timestamp,9223372036854775807)>=?
           LIMIT 1""",(after,before)
    ).fetchone()
    if gap:
        return "KNOWN_COLLECTION_GAP",None,metadata

    if pre[1] != post[1]:
        return "PROVIDER_SWITCH",None,metadata

    states = []
    for poll_time in (before, after):
        row = conn.execute(
            """SELECT timestamp,quantity,source FROM stock_history
               WHERE country=? AND item_name=? AND timestamp<=?
               ORDER BY timestamp DESC,id DESC LIMIT 1""",
            (country,item,poll_time)
        ).fetchone()
        if row is None:
            return "NO_STOCK_STATE",None,metadata
        if poll_time-int(row[0]) > MAX_STATE_AGE_SECONDS:
            return "STOCK_STATE_OLDER_THAN_24H",None,metadata
        # A change-only stock row from a different upstream provider cannot
        # be assumed to describe the same current observation stream.
        if row[2] != pre[1]:
            return "STOCK_STATE_PROVIDER_MISMATCH",None,metadata
        states.append((int(row[1]),int(row[0])))
    metadata["pre_quantity"], metadata["post_quantity"] = states[0][0],states[1][0]
    metadata["pre_state_age_s"] = before-states[0][1]
    metadata["post_state_age_s"] = after-states[1][1]
    earlier, later = (q>=THRESHOLD for q,_ in states)
    if earlier != later:
        return "THRESHOLD_TRANSITION_BRACKET",None,metadata
    # Matching endpoints do not establish continuity: an item can sell out
    # and refill (or change providers and switch back) inside this bracket.
    # Such evidence is ambiguous, not a success or a known miss.
    interior = conn.execute(
        """SELECT quantity,source FROM stock_history
           WHERE country=? AND item_name=? AND timestamp>? AND timestamp<=?
           ORDER BY timestamp,id""", (country,item,before,after)
    )
    for quantity, source in interior:
        if source != pre[1]:
            return "STOCK_STATE_PROVIDER_MISMATCH",None,metadata
        if (int(quantity)>=THRESHOLD) != earlier:
            return "THRESHOLD_TRANSITION_BRACKET",None,metadata
    switched = conn.execute(
        """SELECT 1 FROM poll_heartbeats
           WHERE mode='poll-cycle' AND success=1 AND timestamp>? AND timestamp<?
             AND (source IS NULL OR source!=?) LIMIT 1""",
        (before,after,pre[1])
    ).fetchone()
    if switched:
        return "PROVIDER_SWITCH",None,metadata
    return ("POLL_STATE_PROXY_SUCCESS",True,metadata) if earlier else (
        "POLL_STATE_PROXY_MISS",False,metadata)


def report(*, ledger=V75, stock=SOURCE, days=1, limit=MAX_PROXY_EVENTS,
           now=None):
    if not 1<=days<=14 or not 1<=limit<=MAX_PROXY_EVENTS:
        raise ValueError("invalid days / limit")
    if Path(ledger).resolve(strict=True)==Path(stock).resolve(strict=True):
        raise ValueError("stock and research sidecar must be distinct")
    asof = int(time.time() if now is None else now)
    with closing(ro(ledger)) as evidence:
        events,raw,invalid = select_unique(
            evidence,start=asof-days*86400,end=asof)
    if len(events)>limit:
        raise ValueError("more arrival targets than safe cap: use smaller days")

    counts=Counter()
    by_item=defaultdict(Counter)
    paired=Counter()
    paired_by_item=defaultdict(Counter)
    direct=Counter()
    state_age=Counter()
    with closing(ro(stock)) as collector:
        for row in events:
            key=row["item_key"]
            country,item=key.split(":",1)
            result, success,meta=observation(
                collector,country,item,int(row["arrival"]),asof)
            counts[result]+=1
            by_item[key][result]+=1
            if result in ("POLL_STATE_PROXY_SUCCESS","POLL_STATE_PROXY_MISS"):
                age = max(meta["pre_state_age_s"],meta["post_state_age_s"])
                state_age["<=3min" if age<=180 else
                          "<=1hour" if age<=3600 else
                          "<=1day" if age<=86400 else ">1day"]+=1

            if result!="PENDING":
                direct[strict_samples(collector,country,item,int(row["arrival"]))]+=1

            # Baseline: flying at the time the recommendation was issued.
            # Compare only matched resolved proxy outcomes, without treating
            # distinct five-minute forecasts as independent stock cycles.
            baseline_arrival=int(row["computed_at"])+TRAVEL_SECONDS[country]
            b_result,b_success,_=observation(
                collector,country,item,baseline_arrival,asof)
            if success is not None and b_success is not None:
                paired["count"]+=1
                paired["recommendation_successes"]+=int(success)
                paired["immediate_departure_successes"]+=int(b_success)
                bucket = ("both_success" if success and b_success else
                          "recommendation_only" if success else
                          "immediate_only" if b_success else "both_miss")
                paired[bucket]+=1
                paired_by_item[key]["count"]+=1
                paired_by_item[key][bucket]+=1

    scored=counts["POLL_STATE_PROXY_SUCCESS"]+counts["POLL_STATE_PROXY_MISS"]
    return {
        "status":"V88_POLL_STATE_FORWARD_RESEARCH_REPORT",
        "observation_version":OBSERVATION_VERSION,
        "read_only":True,
        "research_only":True,
        "exact_10s_accuracy_certified":False,
        "independent_restock_cycles_certified":False,
        "per_country_YATA_snapshot_freshness_certified":False,
        "actual_player_departure_observed":False,
        "collector_written":False,
        "sidecar_written":False,
        "evidence_warning":(
            "Global heartbeat + carried-forward delta state is an observed-stock "
            "proxy. No per-country provider update timestamps are persisted; "
            "upstream feed can be stale. Correlated arrival targets are not "
            "independent restock cycles. Not gameplay success certification."
        ),
        "asof_epoch":asof,
        "issued_window_days":days,
        "raw_candidate_rows":raw,
        "excluded_invalid_or_abstained":invalid,
        "unique_item_arrival_targets":len(events),
        "proxy_scorable":scored,
        "proxy_success":counts["POLL_STATE_PROXY_SUCCESS"],
        "proxy_miss":counts["POLL_STATE_PROXY_MISS"],
        "proxy_success_fraction":(
            round(counts["POLL_STATE_PROXY_SUCCESS"]/scored,4) if scored else None),
        "pending":counts["PENDING"],
        "outcomes":dict(sorted(counts.items())),
        "per_item":{key:dict(sorted(c.items())) for key,c in sorted(by_item.items())},
        "direct_stock_change_samples":dict(sorted(direct.items())),
        "scored_max_last_change_age_buckets":dict(sorted(state_age.items())),
        "matched_immediate_departure_baseline":dict(sorted(paired.items())),
        "matched_baseline_by_item":{
            k:dict(sorted(v.items())) for k,v in sorted(paired_by_item.items())}
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days",type=int,default=1)
    p.add_argument("--limit",type=int,default=1200)
    a=p.parse_args()
    if not approved_collector_source(SOURCE):
        raise SystemExit("STOP: collector location does not match approved source")
    result=report(days=a.days,limit=a.limit)
    print(json.dumps(result,sort_keys=True))


if __name__ == "__main__":
    main()
