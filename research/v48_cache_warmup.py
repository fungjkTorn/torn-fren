"""V48 optional low-priority unattended Monkey/Chamois cache backfill.

This advances at most ONE existing V47 target per run. It never edits the
public collector or existing 19-item V38/V44 private scheduler. Systemd
timer frequency, CPU/memory and watchdog are separately enforced.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

from research.v38_capacity_guard import inspect as inspect_capacity
from research.v47_online_expert_cache import DEFAULT_CACHE, run as warmup

TARGETS=("monkey","chamois")
DIR=Path(DEFAULT_CACHE).parent
LOCK=DIR/"v48_warmup.lock"


def unit_active(name):
    try:
        return subprocess.run(
            ["systemctl","is-active","--quiet",name],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            check=False,timeout=4,
        ).returncode==0
    except (subprocess.TimeoutExpired,OSError):
        return False


def preflight(is_active=unit_active,capacity=inspect_capacity):
    required=("torn-fren-v38-private-shadow.timer",
              "torn-fren-web.service",
              "torn-fren-poller.service",
              "torn-fren-bot.service")
    if any(not is_active(u) for u in required):
        return "PREREQUISITE_SERVICE_INACTIVE"
    if is_active("torn-fren-v38-private-shadow.service"):
        return "DEFERRED_19_MODEL_RESEARCH_ACTIVE"
    admission=capacity()
    if not admission.get("allowed"):
        return "DEFERRED_HOST_CPU_PRESSURE"
    return None


def select_next(con):
    con.execute("""CREATE TABLE IF NOT EXISTS v48_warmup_turn(
      singleton INTEGER PRIMARY KEY CHECK(singleton=1),
      next_target TEXT NOT NULL, last_attempt INTEGER NOT NULL)""")
    row=con.execute(
        "SELECT next_target FROM v48_warmup_turn WHERE singleton=1"
    ).fetchone()
    target=row[0] if row and row[0] in TARGETS else TARGETS[0]
    next_target=TARGETS[1] if target==TARGETS[0] else TARGETS[0]
    with con:
        con.execute("""INSERT INTO v48_warmup_turn VALUES(1,?,?)
          ON CONFLICT(singleton) DO UPDATE SET
          next_target=excluded.next_target,
          last_attempt=excluded.last_attempt""",(next_target,int(time.time())))
    return target


def work_once(db,cache,*,budget=40,max_decisions=24,
              active=unit_active,capacity=inspect_capacity,runner=warmup):
    reason=preflight(active,capacity)
    if reason:
        return {"status":reason,"research_only":True}
    directory=Path(cache).parent
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/"v48_warmup.lock").open("a+b") as f:
        try:
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status":"DEFERRED_WARMUP_ALREADY_RUNNING",
                    "research_only":True}
        # Check again after acquiring lock: a research cycle can start while
        # we waited on the filesystem. CPU quota remains a final backstop.
        reason=preflight(active,capacity)
        if reason:
            return {"status":reason,"research_only":True}
        with sqlite3.connect(cache,timeout=3) as con:
            target=select_next(con)
        result=runner(db,cache,target,int(time.time()),
                      budget_seconds=budget,max_decisions=max_decisions)
        return {"status":"V48_TICK_COMPLETE","target":target,
                "outcome":result,"research_only":True,
                "modified_v38_sidecar":False,
                "modified_collector":False}


def read_status(cache):
    path=Path(cache)
    if not path.exists():
        return {"status":"CACHE_MISSING","research_only":True}
    try:
        with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",
                             uri=True,timeout=2) as c:
            try:
                counts=dict(c.execute("""SELECT item_key,COUNT(*)
                    FROM expert_resolutions GROUP BY item_key""").fetchall())
            except sqlite3.OperationalError:
                counts={}
            try:
                row=c.execute("SELECT next_target,last_attempt FROM v48_warmup_turn WHERE singleton=1").fetchone()
            except sqlite3.OperationalError:
                row=None
            return {"status":"CACHE_FOUND",
                    "cached_rows":{
                        "arg:Monkey Plushie":counts.get("arg:Monkey Plushie",0),
                        "swi:Chamois Plushie":counts.get("swi:Chamois Plushie",0)},
                    "next_target":row[0] if row else None,
                    "last_attempt":row[1] if row else None,
                    "research_only":True}
    except sqlite3.Error:
        return {"status":"CACHE_UNAVAILABLE","research_only":True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",default="/opt/torn-fren/data/stock_history.db")
    p.add_argument("--cache",default=DEFAULT_CACHE)
    p.add_argument("--status",action="store_true")
    p.add_argument("--budget",type=float,default=40)
    p.add_argument("--max-decisions",type=int,default=24)
    a=p.parse_args()
    try:
        if a.status:
            r=read_status(a.cache)
        else:
            if not 1<=a.budget<=45 or not 1<=a.max_decisions<=24:
                raise ValueError("V48 must respect capped resource budget")
            r=work_once(a.db,a.cache,budget=a.budget,
                        max_decisions=a.max_decisions)
    except Exception as exc:
        r={"status":"V48_WARMUP_ERROR","error_type":type(exc).__name__,
           "research_only":True}
    print(json.dumps(r,sort_keys=True))
    # systemd records error, but harmless resource deferrals exit success.
    if r.get("status")=="V48_WARMUP_ERROR":
        raise SystemExit(1)


if __name__=="__main__":
    main()
