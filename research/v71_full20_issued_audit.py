"""V71: READ-ONLY as-issued audit of V70's completed isolated 20-model ledger.

V70 emitted 20/20 complete research proposals; five departure timestamps
became past by the end of its ~2 minute all-model run. A historical smoke
should verify that every proposal WAS valid at issuance, separately reporting
which ones ceased to be actionable at audit time.

This is NOT a new live forecast. No model routing, timers, collector, cache,
or sidecar writes. The source remains the frozen V70 research snapshot only.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from research.plushie_champions.common import STEP, MAX_WAIT, GRACE, TRAVEL_SECONDS
from research.v63_full_mirror_smoke import exact_roster
from research.v68_monkey_isolated_canary import KEY as MONKEY, FAMILY, CONFIG
from research.v57_exception_fingerprint import fingerprint

ROOT=Path("/var/lib/torn-fren-v38")
SNAPSHOT=ROOT/"v70_full20_stock_snapshot.db"
SIDECAR=ROOT/"v70_full20_private_canary.db"
SUCCESS="V71_FULL20_AS_ISSUED_VERIFIED"
ISSUE_AGE_LIMIT=180


def result(status,**data):
    return {
        "status":status,
        "research_only":True,
        "historical_as_issued_audit":True,
        "currently_live_predictions":False,
        "collector_written":False,
        "v48_cache_written":False,
        "v65_sidecar_written":False,
        "website_changed":False,
        "model_20_scheduled":False,
        **data,
    }


def _conn(path,*,immutable=False):
    p=Path(path).resolve(strict=True)
    if not p.is_file() or p.is_symlink():
        raise ValueError("audit source must be regular file")
    uri=p.as_uri()+"?mode=ro"+("&immutable=1" if immutable else "")
    c=sqlite3.connect(uri,uri=True,timeout=4)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    return c


def _issue_errors(row,heartbeat):
    key=row["item_key"]
    errors=[]
    try:
        country,item=key.split(":",1)
        country=country.strip()
        if not item or country not in TRAVEL_SECONDS:
            errors.append("UNKNOWN_TRAVEL_TARGET")
    except ValueError:
        errors.append("MALFORMED_ITEM_KEY")
        country=None

    issued,stock,valid,due,dep,arr=(row[k] for k in (
        "computed_at","stock_as_of","valid_until","next_due_at",
        "departure","arrival"))
    if row["status"]!="RESEARCH_PROPOSAL_ONLY" or int(row["executed"])!=1:
        errors.append("NOT_EXECUTED_PROPOSAL")
    if (type(issued) is not int or type(stock) is not int
            or not 0<=issued-stock<=ISSUE_AGE_LIMIT):
        errors.append("SOURCE_NOT_FRESH_AT_ISSUE")
    if type(stock) is not int or stock!=heartbeat:
        errors.append("NOT_FROM_FROZEN_SNAPSHOT")
    if type(issued) is not int or type(valid) is not int or valid!=issued+STEP:
        errors.append("INCORRECT_ISSUE_TTL")
    if type(issued) is not int or type(due) is not int or due<issued:
        errors.append("INVALID_NEXT_DUE")
    if (type(issued) is not int or type(dep) is not int
            or not issued<=dep<=issued+MAX_WAIT):
        errors.append("DEPARTURE_INVALID_AT_ISSUE")
    if (type(arr) is not int or type(dep) is not int or
        country not in TRAVEL_SECONDS or
        arr-dep!=TRAVEL_SECONDS[country]):
        errors.append("ARRIVAL_TRAVEL_MISMATCH")
    return errors


def audit(snapshot,sidecar,*,clock=time.time):
    mirror=Path(snapshot).resolve(strict=True)
    ledger=Path(sidecar).resolve(strict=True)
    if mirror==ledger:
        raise ValueError("source and ledger must be distinct")
    expected=set(exact_roster())|{MONKEY}
    if len(expected)!=20:
        raise ValueError("roster changed since V70")
    now=int(clock())

    s=_conn(snapshot,immutable=True)
    try:
        if s.execute("PRAGMA journal_mode").fetchone()[0]!="delete":
            return result("V71_UNSAFE_SNAPSHOT_MODE")
        hb=s.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
                    WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
        if type(hb) is not int:
            return result("V71_MISSING_SNAPSHOT_HEARTBEAT")
        c=_conn(sidecar)
        try:
            latest=c.execute("""SELECT item_key,model_family,model_config,status,
                    computed_at,stock_as_of,valid_until,next_due_at,departure,
                    arrival,executed FROM latest_predictions
                    ORDER BY item_key""").fetchall()
            frozen=c.execute("""SELECT item_key,computed_at,model_family,
                    model_config,stock_as_of,status,departure,arrival,
                    valid_until,actual_player_departure
                    FROM v42_candidate_decisions ORDER BY item_key""").fetchall()
        finally:
            c.close()
    finally:
        s.close()

    issues={}
    now_expired=[]
    now_ttl=[]
    fresh_now=[]
    latest_by_key={r["item_key"]:r for r in latest}
    original_keys=set(latest_by_key)
    for r in latest:
        key=r["item_key"]
        errors=_issue_errors(r,int(hb))
        if key==MONKEY and (r["model_family"]!=FAMILY or
                            r["model_config"]!=CONFIG):
            errors.append("MONKEY_WRONG_ORIGINAL_SELECTOR")
        if errors:
            issues[key]=sorted(set(errors))
        dep=r["departure"]
        until=r["valid_until"]
        if type(dep) is int and dep<now:
            now_expired.append(key)
        if type(until) is int and until<=now:
            now_ttl.append(key)
        if (not errors and type(dep) is int and type(until) is int
                and dep>=now and until>now and 0<=now-int(hb)<=ISSUE_AGE_LIMIT):
            fresh_now.append(key)

    # Compare immutable proposal evidence to the upserted latest table.
    frozen_by_key={}
    for r in frozen:
        key=r["item_key"]
        if key in frozen_by_key:
            issues.setdefault(key,[]).append("DUPLICATE_FROZEN_EVIDENCE")
        frozen_by_key[key]=r
    fields=("item_key","computed_at","model_family","model_config",
            "stock_as_of","status","departure","arrival","valid_until")
    for key in expected:
        row=latest_by_key.get(key)
        evidence=frozen_by_key.get(key)
        if row is None or evidence is None:
            issues.setdefault(key,[]).append("MISSING_ORIGINAL_EVIDENCE")
        elif any(row[f]!=evidence[f] for f in fields):
            issues.setdefault(key,[]).append("FROZEN_EVIDENCE_MISMATCH")
        if evidence is not None and evidence["actual_player_departure"]!=0:
            issues.setdefault(key,[]).append("FALSE_PLAYER_DEPARTURE")

    extra=sorted((original_keys|set(frozen_by_key))-expected)
    missing=sorted(expected-original_keys)
    valid=(len(latest)==20 and len(frozen)==20 and
           original_keys==expected and set(frozen_by_key)==expected and
           not issues)
    return result(
        SUCCESS if valid else "V71_FULL20_AS_ISSUED_REJECTED",
        verified_as_issued=valid,
        snapshot_heartbeat=int(hb),
        snapshot_age_at_audit_seconds=now-int(hb),
        persisted_count=len(latest),
        frozen_evidence_count=len(frozen),
        expected_models=20,
        original_19_rows=sum(k in latest_by_key for k in expected-{MONKEY}),
        monkey_row_present=MONKEY in latest_by_key,
        historical_valid_proposal_count=(20 if valid else
            sum(k in expected and k not in issues for k in latest_by_key)),
        source_pinned_invalid_issues=issues,
        missing_item_keys=missing,
        extra_item_keys=extra,
        departure_passed_by_audit_count=len(now_expired),
        departure_passed_by_audit=sorted(now_expired),
        five_minute_validity_elapsed_count=len(now_ttl),
        currently_actionable_in_this_old_snapshot_count=len(fresh_now),
    )


def main():
    try:
        root=ROOT.resolve(strict=True)
        for p in (SNAPSHOT,SIDECAR):
            if p.parent.resolve(strict=True)!=root or p.is_symlink():
                raise ValueError("audit path outside private research directory")
        out=audit(SNAPSHOT,SIDECAR)
    except Exception as exc:
        out=result("V71_READONLY_AUDIT_ERROR",**fingerprint(exc))
    print(json.dumps(out,sort_keys=True))
    if out["status"]!=SUCCESS:
        raise SystemExit(1)


if __name__=="__main__":
    main()
