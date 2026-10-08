"""Explicit opt-in, LOCAL-ONLY private shadow capture (one pass, no scheduler).

Records genuine current private V2/challenger recommendations BEFORE outcomes.
Uses a private token only in an HTTP header, never query strings or logs.
No Torn gameplay action, no account API keys, no stock DB writes, no auto-travel.

Run (on the machine serving the private API):
  python -m research.v32_capture_pilot --endpoint http://127.0.0.1:8000 \
      --item can:'Fire Hydrant' --evidence-db data/v32_private_evidence.db \
      --experiment v32pilot-20261008 --acknowledge-private-research

Enable both private shadow flags separately only after you have inspected the
host configuration and ensured the public site is unaffected.
"""
from __future__ import annotations
import argparse
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from research.v31_shadow_evidence_capture import record_private_decision

TOKEN_KEY="TORN_FREN_CHAMPION_SHADOW_TOKEN"


def _safe_local_endpoint(raw):
    u=urllib.parse.urlsplit(raw)
    if u.scheme!="http" or u.hostname not in ("127.0.0.1","localhost","::1"):
        raise ValueError("only local loopback HTTP endpoint is accepted for initial private pilot")
    if u.username or u.password or u.query or u.fragment or u.path not in ("","/"):
        raise ValueError("private pilot endpoint must be the bare local base URL")
    return raw.rstrip("/")


def capture_once(base,item_key,evidence_db,experiment,token,*,fetch=None):
    base=_safe_local_endpoint(base)
    if len(token)<32:
        raise ValueError("missing long private research token")
    if ":" not in item_key:
        raise ValueError("expected country:item")
    country,item=item_key.split(":",1)
    if len(country)!=3 or not item:
        raise ValueError("invalid catalog item")
    url=base+"/api/research/champion-shadow?"+urllib.parse.urlencode({
        "country":country,"item":item
    })
    request=urllib.request.Request(url,headers={
        "X-Torn-Fren-Shadow-Token":token,
        "Accept":"application/json",
    },method="GET")
    http=fetch or urllib.request.urlopen
    with http(request,timeout=70) as response:
        if response.status!=200:
            raise RuntimeError("private shadow HTTP request failed")
        body=response.read(32769)
        if len(body)>32768:
            raise ValueError("oversized private response")
    data=json.loads(body)
    if data.get("key")!=item_key:
        raise ValueError("returned item key does not match requested key")
    out=record_private_decision(evidence_db,data,experiment)
    return {"item_key":item_key,**out}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--endpoint",default="http://127.0.0.1:8000")
    p.add_argument("--item",action="append",required=True,
                   help="Exact 3-letter-country:item key; max 4 per invocation")
    p.add_argument("--evidence-db",required=True)
    p.add_argument("--experiment",required=True)
    p.add_argument("--acknowledge-private-research",action="store_true")
    a=p.parse_args()
    if not a.acknowledge_private_research:
        p.error("private pilot requires explicit acknowledgement")
    items=list(dict.fromkeys(a.item))
    if len(items)>4:
        p.error("first pilot is limited to 4 items per invocation")
    secret=os.environ.get(TOKEN_KEY,"")
    if len(secret)<32:
        p.error("a 32+ character environment-held shadow token is required")
    if Path(a.evidence_db).name=="stock_history.db":
        p.error("refusing to write into stock collector database")
    results=[]
    for key in items:
        try:
            results.append(capture_once(a.endpoint,key,a.evidence_db,a.experiment,secret))
        except Exception as exc:
            # Do not leak host paths, request headers, or the research token.
            results.append({"item_key":key,"status":"CAPTURE_FAILED",
                            "error_type":type(exc).__name__})
    print(json.dumps({"mode":"PRIVATE_READ_ONLY_CAPTURE",
                      "gameplay_automated":False,
                      "results":results},indent=2))


if __name__=="__main__":
    main()
