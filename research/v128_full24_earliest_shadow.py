"""V128: all 24 exact research-roster earliest-credible arrival shadow.

EXPERIMENTAL challenger only. The incumbent 21+3 specialists remain unchanged,
including Japan Xanax, Panda and Lion; no shared model is promoted. Record
a separate first-high-enough-arrival-score candidate for ALL 24 items using
each destination's own flight duration and historical threshold=30 cycles.

The original frozen v38_roster.json enumerates 22; the two v42-approved
generic Xanax keys can:Xanax and uni:Xanax complete the EXACT 24. Fail
closed on drift, duplicate entries, missing keys, stale heartbeat, unknown
phase start, gaps/provider changes, insufficient survivors, invalid history,
overbudget computation, or bad DB identities. Every item yields a row,
including explicit abstentions / skipped status, not invented predictions.

Only past as-of collector data is read, pinned primary source read-only; no
API requests, gameplay, public routing, model changes or automated deployment.
--preview is the default: ZERO writes. --record is explicit and writes only
/var/lib/torn-fren-v38/v128_earliest24_shadow.db. Independent frozen
five-minute-issued evidence is needed to test forward policy value.
Raw empirical Monte Carlo scores are NOT calibrated game-stock probabilities.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import random
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.plushie_champions.common import (
    TRAVEL_SECONDS, MAX_WAIT, STEP, GRACE,
)
from research.v107_explicit_restock_cycle_baseline import (
    StockObservation, completed_phases,
)
from research.v60_private_snapshot_probe import (
    approved_collector_source, read_heartbeat,
)
from research.v125_earliest_credible_shadow import (
    earliest_credible as uk_earliest_selector,
    SCORE_FLOOR, MIN_CONSECUTIVE, SEED as UK_SEED,
    MAX_LAST_CHANGE_AGE_SECONDS,
)

ROSTER=Path(__file__).with_name("v38_roster.json")
COLLECTOR=Path("/opt/torn-fren/data/stock_history.db")
PRIVATE_ROOT=Path("/var/lib/torn-fren-v38")
SIDECAR=PRIVATE_ROOT/"v128_earliest24_shadow.db"
GENERATION="v128_first_credible_24_country_travel_mc128_v1"
EXTRA_XANAX={
    "can:Xanax":("V19","dyn8"),
    "uni:Xanax":("V19","dyn3"),
}
EXPLICIT_NEW_PREVIEWS=frozenset(
    ("chi:Panda Plushie","sou:Lion Plushie","jap:Xanax")
)
SCENARIOS=128
MIN_PHASES=5
MAX_ITEM_ROWS=50000
MAX_GAPS=10000
GLOBAL_HEARTBEAT_LIMIT=180
MAX_COMPUTE_SECONDS=90
MAX_VALID_ISSUE_LATENCY=90
MIN_QTY=30
MAX_ITEMS=24


def exact_roster(path=ROSTER):
    """All 24 known specialists; only this exact pinned identity is allowed."""
    payload=json.loads(Path(path).read_text(encoding="utf-8"))
    entries=payload["items"]
    if len(entries)!=22 or any(not isinstance(k,str) or ":" not in k
                               for k in entries):
        raise ValueError("base roster must be exactly 22 pinned keys")
    result={
        key:{
            "incumbent_model_family":str(value["model_family"]),
            "incumbent_model_config":value.get("config_name"),
            "incumbent_source_verified":bool(value["source_verified"]),
            "incumbent_preview_only":key in EXPLICIT_NEW_PREVIEWS,
        }
        for key,value in entries.items()
    }
    if set(result)&set(EXTRA_XANAX):
        raise ValueError("duplicate v42 Xanax roster mapping")
    for key,(family,config) in EXTRA_XANAX.items():
        result[key]={
            "incumbent_model_family":family,
            "incumbent_model_config":config,
            "incumbent_source_verified":True,
            "incumbent_preview_only":False,
        }
    if (len(result)!=MAX_ITEMS or
        set(result)&{"uni:Obsolete"} or
        not EXPLICIT_NEW_PREVIEWS.issubset(result) or
        not {"uni:Nessie Plushie","uni:Red Fox Plushie"}.issubset(result) or
        any(k.split(":",1)[0] not in TRAVEL_SECONDS for k in result)):
        raise ValueError("unexpected exact 24-item collector/model roster")
    return dict(sorted(result.items()))


def _gap_index(gaps,asof):
    """O(log gaps) crossing check matching V107's inclusive gap definition."""
    if len(gaps)>MAX_GAPS:
        raise ValueError("too many unbounded collection gaps")
    usable=sorted((int(lo), int(hi) if hi is not None else 2**63-1)
                  for lo,hi in gaps if int(lo)<=asof)
    starts=[]
    prefix=[]
    maximum=-1
    for start,end in usable:
        starts.append(start)
        maximum=max(maximum,end)
        prefix.append(maximum)
    def crosses(low,high):
        i=bisect.bisect_right(starts,high)-1
        return i>=0 and prefix[i]>=low
    return crosses


def fast_phases(observations,*,asof,gaps=()):
    """Linear change-only phase extraction with indexed discontinuity checks."""
    cross=_gap_index(gaps,asof)
    last=None
    state=None
    start=None
    prior_source=None
    high=[]
    low=[]
    for o in observations:
        if o.epoch>asof:
            raise ValueError("future item observation is inadmissible")
        if (type(o.epoch) is not int or type(o.quantity) is not int
            or o.quantity<0 or not o.source):
            continue
        flag=o.quantity>=MIN_QTY
        if last is not None and (
            o.epoch<=last.epoch or o.source!=prior_source
            or cross(last.epoch,o.epoch)
        ):
            state=None
            start=None
        if state is None:
            state=flag
            start=None
        elif state!=flag:
            if start is not None and o.epoch>start:
                (high if state else low).append(o.epoch-start)
            state=flag
            start=o.epoch
        last=o
        prior_source=o.source
    return {
        "phase":("HIGH" if state is True else
                 "LOW" if state is False else "UNKNOWN"),
        "phase_onset":start,
        "last_observation":last,
        "stocked_durations":high,
        "depleted_durations":low,
    }


def _read_item(conn,key,issued):
    country,item=key.split(":",1)
    raw=conn.execute(
        """SELECT timestamp,quantity,source FROM stock_history
           WHERE country=? AND lower(item_name)=lower(?)
             AND timestamp<=?
           ORDER BY timestamp DESC,id DESC LIMIT ?""",
        (country,item,issued,MAX_ITEM_ROWS+1),
    ).fetchall()
    if len(raw)>MAX_ITEM_ROWS:
        return None,"MAX_SOURCE_ROWS_EXCEEDED"
    rows=[]
    for epoch,qty,source in reversed(raw):
        if (epoch is None or qty is None or source is None or
            int(qty)<0):
            continue
        rows.append(StockObservation(int(epoch),int(qty),str(source)))
    return rows,None


def empirical_arrival_scores(history,item_key,*,asof,
                             scenarios=SCENARIOS,seed=UK_SEED):
    """Country-specific flight, past-only HIGH/LOW Monte Carlo paths."""
    country=item=item_key.split(":",1)[0]
    if country not in TRAVEL_SECONDS or scenarios<1 or scenarios>512:
        raise ValueError("invalid model input")
    last=history["last_observation"]
    common={
        "phase":history["phase"],"phase_onset":history["phase_onset"],
        "last_stock_change_epoch":None if last is None else last.epoch,
        "last_stock_quantity":None if last is None else last.quantity,
        "provider_source":None if last is None else last.source,
        "stock_change_age_seconds":None if last is None else asof-last.epoch,
        "completed_high":len(history["stocked_durations"]),
        "completed_low":len(history["depleted_durations"]),
        "score_is_calibrated_probability":False,
        "country_provider_freshness_verified":False,
    }
    if last is None:
        return dict(common,status="NO_ITEM_STOCK_HISTORY")
    if history["phase"] not in ("LOW","HIGH"):
        return dict(common,status="UNKNOWN_STOCK_STATE")
    if history["phase_onset"] is None:
        return dict(common,status="CURRENT_PHASE_ONSET_UNKNOWN")
    if not 0<=asof-last.epoch<=MAX_LAST_CHANGE_AGE_SECONDS:
        return dict(common,status="STOCK_CHANGE_TOO_OLD")
    durations={
        "HIGH":[int(n) for n in history["stocked_durations"] if n>=STEP],
        "LOW":[int(n) for n in history["depleted_durations"] if n>=STEP],
    }
    if min(map(len,durations.values()))<MIN_PHASES:
        return dict(common,status="INSUFFICIENT_COMPLETED_CYCLES")
    age=asof-int(history["phase_onset"])
    if age<0:raise AssertionError("future phase onset")
    phase=history["phase"]
    surviving=[n-age for n in durations[phase] if n>age]
    if len(surviving)<MIN_PHASES:
        return dict(common,status="NO_SURVIVING_PHASE_ANALOGS")

    # Preserve exact V125 UK baseline PRNG as an invariant for original 2.
    flight=TRAVEL_SECONDS[country]
    rng=random.Random(seed+asof%100003)
    grid=[flight+d for d in range(0,MAX_WAIT+1,STEP)]
    if len(grid)!=97:
        raise AssertionError("unexpected five-minute grid")
    horizon=grid[-1]+GRACE
    hits=[0]*len(grid)
    for _ in range(scenarios):
        position=float(rng.choice(surviving))
        state=phase
        highs=[(0.,position)] if state=="HIGH" else []
        guard=0
        while position<=horizon:
            guard+=1
            if guard>1000:raise RuntimeError("unbounded cycle sampling")
            state="LOW" if state=="HIGH" else "HIGH"
            length=rng.choice(durations[state])
            if state=="HIGH":
                highs.append((position,position+length))
            position+=length
        for j,arrival in enumerate(grid):
            if any(lo-GRACE<=arrival<hi for lo,hi in highs):
                hits[j]+=1
    scores=[round(h/scenarios,8) for h in hits]
    return dict(
        common,status="ISSUED_EMPIRICAL_TWO_PHASE_CURVE",
        asof_epoch=asof,
        delay_seconds=list(range(0,MAX_WAIT+1,STEP)),
        scores=scores,
        scenario_count=scenarios,
        earliest_immediate_arrival_score=scores[0],
        scores_distinct=len(set(scores)),
        phase_age_seconds=age,
        surviving_analogs=len(surviving),
    )


def earliest_credible_for_country(curve,key):
    """No depart-now preference; earliest two ≥.60 bins within eight hours."""
    country=key.split(":",1)[0]
    flight=TRAVEL_SECONDS[country]
    if curve["status"]!="ISSUED_EMPIRICAL_TWO_PHASE_CURVE":
        return dict(status="ABSTAIN_"+curve["status"],departure=None,
                    arrival=None,score=None)
    ds=curve["delay_seconds"]
    scores=curve["scores"]
    for i in range(len(ds)-MIN_CONSECUTIVE+1):
        if all(scores[i+k]>=SCORE_FLOOR
               and ds[i+k]==ds[i]+k*STEP
               for k in range(MIN_CONSECUTIVE)):
            dep=curve["asof_epoch"]+ds[i]
            return dict(
                status="EARLIEST_NOW" if ds[i]==0
                    else "EARLIEST_WAIT_SUPPORTED",
                departure=dep,arrival=dep+flight,
                score=scores[i],
                wait_seconds=ds[i],
            )
    return dict(status="NO_SUPPORTED_DEPARTURE_WITHIN_EIGHT_HOURS",
                departure=None,arrival=None,score=None)


def item_record(key,roster,observations,gaps,*,issued):
    country=key.split(":",1)[0]
    evidence=dict(
        item_key=key,issued_epoch=issued,policy_id=GENERATION,
        country=country,travel_seconds=TRAVEL_SECONDS[country],
        min_stock_at_arrival=MIN_QTY,
        collector_country_freshness_verified=False,
        historical_scores_not_calibrated=True,
        source_asof_issued_epoch=issued,
        research_only=True,
        incumbent_model_family=roster["incumbent_model_family"],
        incumbent_model_config=roster["incumbent_model_config"],
        incumbent_preview_only=roster["incumbent_preview_only"],
        baseline_leave_now_departure=issued,
        baseline_leave_now_arrival=issued+TRAVEL_SECONDS[country],
    )
    if observations is None:
        curve={"status":"MAX_SOURCE_ROWS_EXCEEDED"}
    else:
        curve=empirical_arrival_scores(
            fast_phases(observations,asof=issued,gaps=gaps),
            key,asof=issued)
    choice=earliest_credible_for_country(curve,key)
    dep=choice["departure"]
    if dep is not None and not issued<=dep<=issued+MAX_WAIT:
        raise AssertionError("invalid country-specific departure")
    return dict(
        evidence,
        source_status=curve["status"],
        phase=curve.get("phase"),
        phase_onset=curve.get("phase_onset"),
        last_stock_quantity=curve.get("last_stock_quantity"),
        last_stock_change_epoch=curve.get("last_stock_change_epoch"),
        collector_source=curve.get("provider_source"),
        score_at_leave_now=curve.get("earliest_immediate_arrival_score"),
        earliest_departure=dep,
        earliest_arrival=choice["arrival"],
        earliest_score=choice["score"],
        wait_minutes=None if dep is None else round((dep-issued)/60,2),
        decision_status=choice["status"],
        departure_state=(
            "ABSTAIN" if dep is None else
            "RESEARCH_NOW" if dep==issued else
            "RESEARCH_READY_WITHIN_5M" if dep-issued<=STEP else
            "RESEARCH_FUTURE_WATCH_UNCONFIRMED"
        ),
        scenario_count=curve.get("scenario_count"),
        scores_distinct=curve.get("scores_distinct"),
        completed_high=curve.get("completed_high"),
        completed_low=curve.get("completed_low"),
        score_gate=SCORE_FLOOR,
        minimum_consecutive_points=MIN_CONSECUTIVE,
        actual_game_departure_verified=False,
        published_to_website=False,
    )


def safe_paths(source=COLLECTOR,sidecar=SIDECAR,*,canonical=True):
    src=Path(source).resolve(strict=True)
    dst=Path(sidecar)
    root=PRIVATE_ROOT if canonical else dst.parent
    if not root.is_dir():
        raise ValueError("private destination parent does not exist")
    parent=root.resolve(strict=True)
    if (dst.is_symlink() or src==dst.resolve(strict=False)
        or dst.resolve(strict=False).parent!=parent
        or not dst.name.endswith(".db")
        or (canonical and
            (src!=COLLECTOR.resolve(strict=True) or
             dst.resolve(strict=False)!=SIDECAR))):
        raise ValueError("unapproved collector or private-only output path")
    if canonical and not approved_collector_source(src):
        raise ValueError("source not approved")
    return src,dst


def write_sidecar(path,issued,heartbeat,rows,*,captured):
    if path.is_symlink():
        raise ValueError("no output symlinks")
    with closing(sqlite3.connect(path,timeout=15)) as conn:
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("""CREATE TABLE IF NOT EXISTS v128_ticks(
            issued_epoch INTEGER PRIMARY KEY,
            captured_epoch INTEGER NOT NULL,
            source_heartbeat INTEGER NOT NULL,
            roster_size INTEGER NOT NULL,
            policy_id TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS v128_issued(
            id INTEGER PRIMARY KEY,
            item_key TEXT NOT NULL,
            issued_epoch INTEGER NOT NULL,
            policy_id TEXT NOT NULL,
            source_status TEXT NOT NULL,
            decision_status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(item_key,issued_epoch,policy_id)
        )""")
        conn.execute("""INSERT OR IGNORE INTO v128_ticks(
            issued_epoch,captured_epoch,source_heartbeat,roster_size,policy_id
        ) VALUES (?,?,?,?,?)""",(issued,captured,heartbeat,MAX_ITEMS,GENERATION))
        conn.executemany("""INSERT OR IGNORE INTO v128_issued(
            item_key,issued_epoch,policy_id,source_status,
            decision_status,payload_json
        ) VALUES (?,?,?,?,?,?)""",[
            (key,issued,GENERATION,rows[key]["source_status"],
             rows[key]["decision_status"],json.dumps(rows[key],sort_keys=True))
            for key in sorted(rows)
        ])
        conn.commit()
    os.chmod(path,0o600)


def observe(*,source=COLLECTOR,sidecar=SIDECAR,roster=ROSTER,
            issued=None,record=False,canonical=True,
            clock=time.time,monotonic=time.monotonic,
            budget_seconds=MAX_COMPUTE_SECONDS):
    started=monotonic()
    issued=int(clock() if issued is None else issued)
    allowed=exact_roster(roster)
    src,dst=safe_paths(source,sidecar,canonical=canonical)
    rows={}
    with closing(sqlite3.connect(src.as_uri()+"?mode=ro",
                                uri=True,timeout=15)) as collector:
        collector.execute("PRAGMA query_only=ON")
        # A read transaction freezes the source view for all 24 items.
        collector.execute("BEGIN")
        hb=read_heartbeat(collector)
        hb_age=None if hb is None else issued-int(hb)
        fresh=hb_age is not None and 0<=hb_age<=GLOBAL_HEARTBEAT_LIMIT
        gaps=[
            (int(a),None if b is None else int(b))
            for a,b in collector.execute("""SELECT start_timestamp,end_timestamp
                FROM collection_gaps WHERE start_timestamp<=?""",(issued,))
        ] if fresh else []
        for key,meta in allowed.items():
            if not fresh:
                rec=item_record(key,meta,None,[],issued=issued)
                rec["source_status"]="GLOBAL_COLLECTOR_HEARTBEAT_STALE"
                rec["decision_status"]="ABSTAIN_GLOBAL_HEARTBEAT_STALE"
                rows[key]=rec
                continue
            if monotonic()-started>budget_seconds:
                rec=item_record(key,meta,None,[],issued=issued)
                rec["source_status"]="SKIPPED_RESOURCE_BUDGET"
                rec["decision_status"]="ABSTAIN_RESOURCE_BUDGET"
                rows[key]=rec
                continue
            observations,invalid=_read_item(collector,key,issued)
            rec=item_record(key,meta,observations,gaps,issued=issued)
            if invalid is not None:
                rec["source_status"]=invalid
            rows[key]=rec
        collector.execute("ROLLBACK")
    captured=int(clock())
    elapsed=monotonic()-started
    if (len(rows)!=24 or set(rows)!=set(allowed)):
        raise AssertionError("not exact 24 research rows")
    if not (0<=captured-issued<=MAX_VALID_ISSUE_LATENCY
            and elapsed<=MAX_VALID_ISSUE_LATENCY):
        # An expired batch is not a credible as-issued 5m model decision;
        # prohibit storing apparently actionable timestamps.
        for r in rows.values():
            r.update(
                earliest_departure=None,earliest_arrival=None,
                earliest_score=None,decision_status="ABSTAIN_OVERDUE_BATCH",
                departure_state="ABSTAIN",source_status="BATCH_EXPIRED"
            )
    if record:
        write_sidecar(dst,issued,hb if hb is not None else 0,rows,
                      captured=captured)
    return {
        "status":"V128_RECORDED_24_PRIVATE" if record
                 else "V128_PREVIEW_24_NO_WRITES",
        "issued_epoch":issued,"captured_epoch":captured,
        "elapsed_seconds":round(elapsed,3),
        "collector_heartbeat_age_seconds":hb_age,
        "all_24_keys_recorded_including_abstentions":len(rows)==24,
        "experimental":True,"research_only":True,
        "stock_collector_written":False,
        "website_modified":False,
        "incumbent_models_changed":False,
        "verified_country_specific_update_freshness":False,
        "private_sidecar":str(dst) if record else None,
        "decision_status_counts":dict(Counter(
            r["decision_status"] for r in rows.values())),
        "roster_count":len(rows),"predictions":rows,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument("--preview",action="store_true")
    mode.add_argument("--record",action="store_true")
    a=p.parse_args()
    result=observe(record=a.record)
    print(json.dumps(result,sort_keys=True))
    if result["roster_count"]!=24:
        raise SystemExit(1)


if __name__=="__main__":
    main()
