"""Bounded ten-item beta publisher; source read-only, evidence append-only."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

from services.first_release_schedule import (
    FIRST_RELEASE_MODELS, build_first_release_decision, forecast_first_release_item,
)
from services import first_release_evidence as evidence


def atomic_json(path, payload):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("refuse symlinked public snapshot")
    raw = json.dumps(payload,sort_keys=True,allow_nan=False).encode()
    fd,tmp = tempfile.mkstemp(prefix=".beta-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(raw); out.flush(); os.fsync(out.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return hashlib.sha256(raw).hexdigest()


def readonly(path):
    db = sqlite3.connect(Path(path).resolve(strict=True).as_uri()+"?mode=ro",uri=True,timeout=15)
    db.execute("PRAGMA query_only=ON")
    return db


def publish(source, state, *, model_sha, item_runner=None, clock=time.time,
            live_source=None, publisher_sha=None, model_roster=FIRST_RELEASE_MODELS,
            time_budget_seconds=45, item_timeout_seconds=15, challenger_cohort=False):
    if not re.fullmatch("[0-9a-f]{40}",model_sha):
        raise ValueError("immutable source revision required")
    if publisher_sha is not None and not re.fullmatch("[0-9a-f]{40}",publisher_sha):
        raise ValueError("immutable publisher revision required")
    state = Path(state)
    if state.is_symlink() or not state.is_dir():
        raise ValueError("ordinary existing state directory required")
    started = int(clock())
    from research.plushie_champions.common import TRAVEL_SECONDS
    from services.frozen_candidate_worker_v31 import inspect_live_source
    # One consistent sanitized snapshot for all models; never fit inside HTTP.
    with tempfile.TemporaryDirectory(prefix=".input-",dir=state) as td:
        frozen = Path(td)/"stock.sqlite"
        with closing(readonly(source)) as src, closing(sqlite3.connect(frozen)) as dest:
            src.backup(dest,pages=1024,sleep=.01)
        issued = int(clock())
        source_refresh = None
        if live_source is not None:
            from services.first_release_source import refresh_tail
            source_refresh = refresh_tail(frozen,live_source,cutoff=issued,model_roster=model_roster)
        health = inspect_live_source(frozen,issued)
        if health["status"] != "FRESH":
            raise ValueError("source unavailable: "+health["status"])
        rows = {}
        item_runtimes = {}
        failures = []
        for key in model_roster:
            item_started = time.monotonic()
            flight = TRAVEL_SECONDS[key.split(":",1)[0]]
            if int(clock())-started > time_budget_seconds:
                raise TimeoutError(f"publisher exceeded {time_budget_seconds}-second inference budget")
            try:
                if item_runner is None:
                    command=[sys.executable,"-B","-m","services.first_release_live","item",
                        "--source",str(frozen),"--key",key,"--issued",str(issued),
                        "--flight",str(flight)]
                    if challenger_cohort:command.append('--challenger-cohort')
                    child = subprocess.run(command,text=True,capture_output=True,
                        timeout=min(item_timeout_seconds,max(1,time_budget_seconds-(int(clock())-started))))
                    if child.returncode:
                        raise RuntimeError("native item process failed: "+child.stderr[-2000:])
                    row = json.loads(child.stdout)
                else:
                    row = item_runner(frozen,key,now=issued,flight_seconds=flight)
                if row.get("item_key") != key or row.get("asof_epoch") != issued:
                    raise ValueError("item identity or issue clock mismatch")
                rows[key] = row
                item_runtimes[key] = round(time.monotonic()-item_started,3)
            except (ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
                failures.append({"item_key":key,"error_type":type(error).__name__,"detail":str(error)[-2000:]})
        # Do not replace a coherent ten-item feed with a partial one.
        if failures or len(rows) != len(model_roster):
            raise RuntimeError("incomplete publisher batch: "+json.dumps(failures))
        published = int(clock())
        if published-started > time_budget_seconds:
            raise TimeoutError(f"publisher exceeded {time_budget_seconds}-second inference budget")
        poll_age = published-health["last_successful_heartbeat"]
        if published-issued >= 180 or poll_age > 180:
            raise ValueError("source expired while preparing publication")
        evidence_started = time.monotonic()
        with closing(readonly(frozen)) as src, closing(evidence.connect(state/"forecasts.sqlite")) as ledger:
            # Reproject publication-time flight geometry. Never display a
            # departure already past or shift the landing by a grace period.
            for key,row in rows.items():
                old = row.get("decision") or {}
                native_departure = old.get("estimated_departure_epoch")
                d = build_first_release_decision(row["forecast"],now=published,
                    flight_seconds=old["player_flight_seconds"],poll_age_seconds=poll_age,
                    timing_choice=lambda **kw: ({"departure":native_departure,
                        "score":old.get("advisory_timing_score")} if type(native_departure) is int and native_departure>=published else None),
                    model_roster=model_roster)
                row["decision"] = d
                row["published_epoch"] = published
                row["source_heartbeat_epoch"] = health["last_successful_heartbeat"]
                row["publisher_sha"] = publisher_sha or model_sha
                row["source_refresh"] = source_refresh
                # Global poll coverage is disclosed; provider country clocks,
                # where available, are reported without inventing per-item age.
                country = key.split(":",1)[0]
                has_clock = src.execute("SELECT 1 FROM sqlite_master WHERE name='country_stock_observations'").fetchone()
                receipt = src.execute("SELECT received_epoch,country_update_epoch,clock_status FROM country_stock_observations WHERE country=? AND received_epoch<=? ORDER BY received_epoch DESC,id DESC LIMIT 1",(country,issued)).fetchone() if has_clock else None
                row["country_clock"] = dict(received_epoch=receipt[0],reported_update_epoch=receipt[1],clock_status=receipt[2]) if receipt else None
                # An explicitly stale or invalid upstream report must not
                # become a departure merely because the global poll succeeded.
                if receipt and (published-receipt[0]>180 or receipt[2]!="REPORTED" or receipt[1] is None or not 0<=published-receipt[1]<=180):
                    d["status"]="STALE_COUNTRY_DATA"
                    for field in ("estimated_departure_epoch","estimated_arrival_epoch","estimated_arrival_plus_grace_epoch","departure_countdown_seconds"):
                        d[field]=None
                evidence.record(ledger,row,model_sha=model_sha)
            evidence.score(ledger,src,cutoff=issued,model_sha=model_sha)
            metrics = {key:evidence.summary(ledger,src,item_key=key,model_sha=model_sha,cutoff=issued) for key in rows}
            ledger.commit()
            prior = ledger.execute("SELECT DISTINCT p.issued,p.published FROM publications p JOIN issues i ON i.issued=p.issued WHERE i.model_sha=? ORDER BY p.issued DESC LIMIT 2",(model_sha,)).fetchall()
            snapshot = {"schema_version":1,"status":"LIVE_BETA","model_sha":model_sha,
                "publisher_sha":publisher_sha or model_sha,"source_refresh":source_refresh,
                "asof_epoch":issued,"published_epoch":published,
                "source_heartbeat_epoch":health["last_successful_heartbeat"],
                "valid_until_epoch":min(issued+300,health["last_successful_heartbeat"]+180),
                "stock_success_rule":"quantity > 30 at calculated landing",
                "flight_profile":"PI + pilot","items":rows,"live_metrics":metrics,
                "historical_accuracy_included":False,"actual_player_flights_required":False}
            snapshot["recent_publications"] = [{"issued_epoch":issued,"published_epoch":published}]+[
                {"issued_epoch":r[0],"published_epoch":r[1]} for r in prior]
            digest = atomic_json(state/"latest.json",snapshot)
            ledger.execute("INSERT INTO publications VALUES(?,?,?)",(issued,published,digest))
            ledger.commit()
        os.chmod(state/"forecasts.sqlite",0o600)
    return {"status":"SIX_ITEM_SNAPSHOT_PUBLISHED" if challenger_cohort else "TEN_ITEM_SNAPSHOT_PUBLISHED","asof_epoch":issued,
            "publisher_sha":publisher_sha or model_sha,"source_refresh":source_refresh,
            "published_epoch":published,"items":len(model_roster),"model_sha":model_sha,
            "elapsed_seconds":int(clock())-started,"item_runtime_seconds":item_runtimes,"evidence_runtime_seconds":round(time.monotonic()-evidence_started,3),"snapshot_sha256":digest}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="action",required=True)
    item=sub.add_parser("item"); item.add_argument("--source",required=True)
    item.add_argument("--key",required=True); item.add_argument("--issued",type=int,required=True)
    item.add_argument("--flight",type=int,required=True)
    item.add_argument('--challenger-cohort',action='store_true')
    pub=sub.add_parser("publish"); pub.add_argument("--source",required=True)
    pub.add_argument("--state",required=True); pub.add_argument("--model-sha",required=True)
    pub.add_argument("--live-source");pub.add_argument("--publisher-sha")
    args=p.parse_args()
    if args.action=="item":
        extra={}
        if args.challenger_cohort:
            from services.forward_beta_roster import CHALLENGER_MODELS,FULL_HISTORY
            extra=dict(model_roster=CHALLENGER_MODELS,timing_full_history=FULL_HISTORY)
        value=forecast_first_release_item(args.source,args.key,now=args.issued,flight_seconds=args.flight,**extra)
    else:
        value=publish(args.source,args.state,model_sha=args.model_sha,
                      live_source=args.live_source,publisher_sha=args.publisher_sha)
    print(json.dumps(value,sort_keys=True))


if __name__=="__main__":
    main()
