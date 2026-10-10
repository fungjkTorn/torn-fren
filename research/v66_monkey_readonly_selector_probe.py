"""V66 one-off READ-ONLY original Monkey selector validation on V65 mirror.

No model admission, output publication, cache mutation, or live WAL source reads.
Rejects stale snapshots, missing experts, gap/backfill changes, future evidence,
and any original-vs-optimized one-tick prediction mismatch.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

from research.plushie_champions.common import (
    connect, load_gaps, Timeline, TemplatePlanner, STEP, MAX_WAIT,
)
from research.v45_online_template_probe import EXPERTS, TARGETS
from research.v46_fast_template import FastTemplatePlanner
from research.v47_online_expert_cache import (
    eligible_starts, gap_fingerprint, score_experts,
)
from research.v57_exception_fingerprint import fingerprint

SNAPSHOT=Path("/var/lib/torn-fren-v38/v65_stock_snapshot.db")
CACHE=Path("/var/lib/torn-fren-v47/online_expert_cache.db")
MAX_AGE=180

def safe_result(status, **extra):
    return {"status":status,"research_only":True,
            "published_to_website":False,
            "live_admission":False,"collector_written":False,
            "v48_cache_written":False,**extra}


def same_plan(a,b):
    if (a is None)!=(b is None):
        return False
    if a is None:
        return True
    if int(a[0])!=int(b[0]) or abs(float(a[1])-float(b[1]))>1e-9:
        return False
    fa,fb=a[2],b[2]
    if set(fa)!=set(fb):
        return False
    return all(abs(float(fa[k])-float(fb[k]))<=1e-9 for k in fa)


def audit(snapshot,cache,*,clock=time.time,fast_planner=FastTemplatePlanner,
          original_planner=TemplatePlanner, compare_planners=True):
    country,item,days=TARGETS["monkey"]
    key=f"{country}:{item}"
    snapshot=Path(snapshot).resolve(strict=True)
    cache=Path(cache).resolve(strict=True)
    if snapshot==cache:
        raise ValueError("source and ledger must be different files")

    # immutable=1 applies ONLY to the V65 private DELETE-mode file,
    # never the live collector or V48 WAL cache.
    s=sqlite3.connect(snapshot.as_uri()+"?mode=ro&immutable=1",uri=True,timeout=5)
    try:
        s.execute("PRAGMA query_only=ON")
        s.execute("BEGIN")
        hb=s.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
                         WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
        asof=int(clock())
        age=asof-int(hb) if hb is not None else None
        if age is None or not 0<=age<=MAX_AGE:
            return safe_result("V66_STALE_SNAPSHOT",heartbeat_age_seconds=age)
        journal=s.execute("PRAGMA journal_mode").fetchone()[0]
        if journal!="delete":
            return safe_result("V66_UNSAFE_SNAPSHOT_MODE")

        gs,ge=load_gaps(s)
        timeline=Timeline(s,gs,ge,country,item)
        if timeline.ts[-1]>hb:
            return safe_result("V66_SOURCE_AFTER_VERIFIED_HEARTBEAT")
        anchors=eligible_starts(timeline,gs,ge,country,int(hb),days)
        if not anchors:
            return safe_result("V66_NO_FULLY_RESOLVED_ANCHORS")
        source_max=int(s.execute("SELECT COALESCE(MAX(id),0) FROM stock_history").fetchone()[0])

        c=sqlite3.connect(cache.as_uri()+"?mode=ro",uri=True,timeout=5)
        try:
            c.execute("PRAGMA query_only=ON")
            c.execute("BEGIN")
            state=c.execute("""SELECT gap_fingerprint,source_max_id
                    FROM expert_source_state WHERE item_key=?""",(key,)).fetchone()
            if not state or str(state[0])!=gap_fingerprint(gs,ge):
                return safe_result("V66_CACHE_GAP_REVISION_INVALID",target=key)
            prior=int(state[1])
            if prior>source_max:
                return safe_result("V66_CACHE_SOURCE_RESET_OR_MISMATCH")
            if prior<source_max:
                # Match V47's original backdated-target invalidation check.
                last_resolved=c.execute("""SELECT MAX(resolved_at)
                  FROM expert_resolutions WHERE item_key=?""",(key,)).fetchone()[0]
                if last_resolved is not None:
                    changed=s.execute("""SELECT 1 FROM stock_history
                      WHERE id>? AND country=? AND lower(item_name)=lower(?)
                        AND timestamp<=? LIMIT 1""",
                        (prior,country,item,int(last_resolved))).fetchone()
                    if changed:
                        return safe_result("V66_BACKDATED_TARGET_REQUIRES_REFRESH")

            rows=c.execute("""SELECT anchor_ts,expert_id,status,success,
                              resolved_at,departure,arrival
                              FROM expert_resolutions
                              WHERE item_key=? AND anchor_ts BETWEEN ? AND ?""",
                              (key,anchors[0],anchors[-1])).fetchall()
            wanted=set(anchors)
            entries={}
            bad=0
            for anchor,expert,status,success,resolved,dep,arrival in rows:
                anchor,expert=int(anchor),int(expert)
                if anchor not in wanted:
                    continue
                if not 0<=expert<len(EXPERTS) or (anchor,expert) in entries:
                    bad+=1
                    continue
                if status=="RESOLVED_EXPERT_DECISION":
                    ok=(type(success) is int and success in (0,1) and
                        type(resolved) is int and anchor<resolved<=hb and
                        dep is not None and arrival is not None)
                elif status=="NO_RESOLVED_EXPERT_DECISION":
                    ok=(success is None and resolved is None)
                else:
                    ok=False
                if not ok:
                    bad+=1
                    continue
                entries[(anchor,expert)]=(success,resolved)
            expected=len(anchors)*len(EXPERTS)
            complete=sum((anchor,idx) in entries for anchor in anchors
                         for idx in range(len(EXPERTS)))
            base=dict(item_key=key,heartbeat_age_seconds=age,
                      required_decisions=expected,cached_decisions=complete,
                      missing_decisions=expected-complete,
                      complete_anchors=sum(
                          all((a,e) in entries for e in range(len(EXPERTS)))
                          for a in anchors),
                      required_anchors=len(anchors),invalid_rows=bad,
                      gap_fingerprint_matches=True)
            if bad or complete!=expected:
                return safe_result("V66_CACHE_NOT_READY",**base)
            chosen=score_experts(entries,anchors,int(hb),days,
                                 count=len(EXPERTS))
            if chosen is None:
                return safe_result("V66_SELECTOR_NOT_READY",**base)
            idx=int(chosen["expert_index"])
            expert=EXPERTS[idx]
            # Re-check wall clock before a potentially costly parity test.
            if int(clock())-int(hb)>MAX_AGE:
                return safe_result("V66_STALE_BEFORE_PARITY",**base)
            q=(int(clock())//STEP)*STEP
            if float(timeline.ts[-1])>q:
                return safe_result("V66_FUTURE_ROWS_RELATIVE_TO_SLOT",**base)
            ctx=SimpleNamespace(timelines={(country,item):timeline})
            options=dict(lags=expert[0],lookback=expert[1],shift_range=expert[2])
            fast=fast_planner(ctx,country,item,**options).plan(float(q))
            original=original_planner(ctx,country,item,**options).plan(float(q)) if compare_planners else fast
            equal=same_plan(fast,original)
            end_age=int(clock())-int(hb)
            result=dict(**base,chosen_expert_index=idx,
                        selected_resolved_count=chosen["resolved_count"],
                        selected_research_score_uncalibrated=chosen["posterior_score"],
                        source_parity_one_slot=bool(equal),
                        end_heartbeat_age_seconds=end_age)
            if end_age>MAX_AGE:
                return safe_result("V66_STALE_AFTER_PARITY",**result)
            if not equal:
                return safe_result("V66_ORIGINAL_PARITY_MISMATCH",**result)
            if fast is None:
                return safe_result("V66_VALIDATED_NO_RECOMMENDATION",**result)
            departure=int(fast[0])
            if not q<=departure<=asof+MAX_WAIT:
                return safe_result("V66_DEPARTURE_OUT_OF_BOUNDS",**result)
            return safe_result("V66_MONKEY_SELECTOR_VALIDATED",
                **result,
                recommended_departure_timestamp=departure,
                # candidate only; never confused with public probabilities.
                uncalibrated_analog_score=float(fast[1]))
        finally:
            c.close()
    finally:
        s.close()


def main():
    # Explicit fixed read-only inputs. Do not accept a live collector CLI arg.
    from research.v60_private_snapshot_probe import approved_collector_source
    try:
        for p in (SNAPSHOT,CACHE):
            if not p.is_file() or p.is_symlink():
                raise ValueError("missing/nonregular research input")
        output=audit(SNAPSHOT,CACHE)
    except Exception as exc:
        output=safe_result("V66_READONLY_PROBE_ERROR",**fingerprint(exc))
    print(json.dumps(output,sort_keys=True))
    if output["status"]=="V66_READONLY_PROBE_ERROR":
        raise SystemExit(1)


if __name__=="__main__":
    main()
