#!/usr/bin/env python3
"""Bounded HTTP readiness probe for *only* the localhost V160 beta board.

One-shot systemd 'restart' may report success before Python binds the socket.
Distinguish that startup race from a persistent crash, and never report 200
merely because a TCP port is open: verify HTML plus the actual 24-item API.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

PORT=8765
MAX_WAIT=45.0


def readiness(*, port=PORT, deadline_seconds=35, interval=1.0,
              expected="new", now_fn=time.monotonic, sleep_fn=time.sleep,
              open_fn=urlopen):
    if not (1024<=port<=65535 and 0<deadline_seconds<=MAX_WAIT and
            .05<=interval<=5 and expected in ("new","rollback")):
        raise ValueError("unbounded/unsupported beta probe parameters")
    base="http://127.0.0.1:"+str(port)
    deadline=now_fn()+deadline_seconds
    attempts=0
    last_error="not tried"
    while True:
        attempts+=1
        try:
            with open_fn(base+"/",timeout=3) as response:
                if response.status!=200:
                    raise ValueError("HTML HTTP "+str(response.status))
                page=response.read(200_001).decode("utf-8")
            if len(page)>200_000:
                raise ValueError("oversize private beta HTML")
            if expected=="new":
                for phrase in ("Where should I fly?",
                               "Recalculate this item NOW",
                               "RECENT_ISSUED_NOW_RECHECK"):
                    if phrase not in page:
                        raise ValueError("new HTML missing "+phrase)
            elif "<html" not in page.lower():
                raise ValueError("rollback HTML missing")
            try:
                with open_fn(base+"/api/live",timeout=3) as response:
                    body=response.read(100_001)
                    status=response.status
            except HTTPError as err:
                status=err.code
                body=err.read(100_001)
            if len(body)>100_000:
                raise ValueError("oversize beta API")
            result=json.loads(body)
            items=result.get("items")
            if (not isinstance(items,list) or len(items)!=24 or
                not all(isinstance(row,dict) and
                        "item_key" in row and "models" in row
                        for row in items)):
                raise ValueError("private beta API missing 24 complete items")
            if expected=="new":
                if status!=200 or result.get("healthy") is not True:
                    raise ValueError("new beta evidence stale or API HTTP "+str(status))
                if any("signal" not in variant for row in items
                       for variant in row["models"].values()):
                    raise ValueError("new beta API missing issued signal state")
            elif status not in (200,503):
                raise ValueError("rollback API HTTP "+str(status))
            return {"status":"V160_BETA_HTTP_READY",
                    "mode":expected,"attempts":attempts,"http":status,
                    "records":len(items),"source_healthy":result.get("healthy")}
        except (HTTPError,URLError,OSError,TimeoutError,ValueError,
                KeyError,TypeError,UnicodeError,json.JSONDecodeError) as exc:
            last_error=type(exc).__name__+": "+str(exc)[:300]
        remaining=deadline-now_fn()
        if remaining<=0:
            raise TimeoutError("V160 "+expected+" HTTP readiness timed out after "+
                               str(attempts)+" tries; last failure: "+last_error)
        sleep_fn(min(interval,remaining))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=("new","rollback"),default="new")
    parser.add_argument("--wait",type=float,default=35)
    parser.add_argument("--port",type=int,default=PORT)
    args=parser.parse_args()
    try:
        print(json.dumps(readiness(port=args.port,
             deadline_seconds=args.wait,expected=args.mode),sort_keys=True))
    except (ValueError,TimeoutError) as err:
        print("V160_BETA_NOT_READY: "+str(err),file=sys.stderr)
        raise SystemExit(1) from None


if __name__=="__main__":
    main()
