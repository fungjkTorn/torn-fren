#!/usr/bin/env python3
"""Standalone, loopback-only 24-item live V160 research board.

Only reads the isolated prospective SQLite ledger. Does not import or alter
the production web app, collector, specialist timers or either existing page.
Launch on the VM and reach it through an SSH local port-forward.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

LEDGER = Path("/var/lib/torn-fren-v38/v160_v151_prospective24.db")
ROSTER = Path("/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json")
POLICY = "v160_v151_independent_paired_asissued_20261013"
MAX_TICK_AGE = 660
MAX_SOURCE_HEARTBEAT_AGE = 180
MAX_CAPTURE_LATENCY = 90
MIN_STOCK = 30
FLIGHTS = {
    "mex": 1020, "cay": 1380, "can": 1620, "haw": 5340,
    "uni": 6360, "arg": 6660, "swi": 6960, "jap": 8940,
    "chi": 9600, "uae": 10800, "sou": 11820,
}
COUNTRIES = {
    "mex": "Mexico", "cay": "Cayman Islands", "can": "Canada",
    "haw": "Hawaii", "uni": "United Kingdom", "arg": "Argentina",
    "swi": "Switzerland", "jap": "Japan", "chi": "China",
    "uae": "United Arab Emirates", "sou": "South Africa",
}
VARIANTS = ("independent", "paired_complete")
MAX_ROWS = 24
HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-store">
<title>Torn Fren · Live 24-item Research Beta</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif;background:#111820;color:#ecf2f7}
*{box-sizing:border-box}body{max-width:1550px;margin:auto;padding:24px}
h1{margin:0 0 8px;font-size:1.7rem}h2{font-size:1.1rem}
a{color:#8bd4ff}.muted{color:#b0bfcc}.warn{color:#ffd697}.good{color:#8ae0bb}
.top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap}
.sub{font-size:.94rem;margin:8px 0 22px}
.banners{background:#202c39;border:1px solid #52657b;border-radius:12px;padding:15px;margin:12px 0}
.metrics{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.metric{border:1px solid #405065;background:#192430;padding:12px 17px;border-radius:10px;min-width:130px}
.metric strong{font-size:1.5rem;display:block}
.controls{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0}
button,select,input{background:#1c2a38;color:#eef5fa;padding:10px;border:1px solid #536c82;border-radius:8px;font:inherit}
button{cursor:pointer}button:focus,input:focus,select:focus{outline:2px solid #8bd4ff}
.tablewrap{overflow:auto;border:1px solid #33495b;border-radius:10px}
table{width:100%;border-collapse:collapse;min-width:1050px}
th,td{padding:12px 11px;text-align:left;border-bottom:1px solid #314151;vertical-align:top}
th{background:#233141;position:sticky;top:0;white-space:nowrap}
tbody tr:hover{background:#1d2b39}
.small{font-size:.8rem;line-height:1.5;color:#b0bfcc}
strong{font-weight:650}.mono{font-variant-numeric:tabular-nums}
.status{font-weight:650}footer{font-size:.86rem;line-height:1.6;padding:16px 0}
@media(max-width:700px){body{padding:12px}th,td{padding:8px}}
</style></head><body>
<div class="top"><div><h1>Torn Fren · Live research beta</h1>
<p class="sub muted">24 foreign items · V160 forward snapshots · refreshed every 30 seconds</p></div>
<button id="refresh" type="button">Refresh now</button></div>
<div class="banners"><strong>Research-only — not a verified travel instruction.</strong>
Predicted availability means modeled ≥30 stock upon arrival, not guaranteed real-game stock.
Do not interpret scenario fractions as calibrated success probabilities. Future departures must be reconfirmed within five minutes of leaving.</div>
<div id="health" class="banners" role="status">Loading current research ledger…</div>
<div class="metrics"><div class="metric"><strong id="covered">—</strong><span class="small">Items with fresh proposals</span></div>
<div class="metric"><strong id="agree">—</strong><span class="small">Model agreement (within 5m)</span></div>
<div class="metric"><strong id="updated">—</strong><span class="small">Latest issue (your time)</span></div></div>
<div class="controls"><label>Search <input id="search" type="search" placeholder="Item or country"></label>
<label>Show <select id="filter"><option value="all">All 24 items</option>
<option value="proposals">With departure candidates</option>
<option value="watch">Future watches</option>
<option value="none">No usable forecast</option></select></label>
<label>Sort <select id="sort"><option value="departure">Earliest departure</option>
<option value="country">Country / item</option></select></label></div>
<div class="tablewrap"><table><thead><tr><th>Destination / item</th><th>Observed last quantity</th>
<th>Independent model</th><th>Paired model</th><th>Research status</th><th>Flight</th></tr></thead>
<tbody id="rows"><tr><td colspan="6">Loading…</td></tr></tbody></table></div>
<footer class="muted">This is a separate private preview, not a replacement for the existing original V2 stock graph or experimental dashboard.
Provider freshness is not verified separately by country. No real player flights or purchases are validated.
If this feed goes stale, departure recommendations disappear rather than remaining actionable.</footer>
<script>
"use strict";
let current=null, loadedAt=0;
const byId=x=>document.getElementById(x);
const local=t=>Number.isInteger(t)?new Date(t*1000).toLocaleString():"—";
const duration=s=>{if(!Number.isFinite(s))return "—";const n=Math.max(0,Math.floor(s));
 return Math.floor(n/3600)+"h "+Math.floor(n%3600/60)+"m "+n%60+"s";};
function cell(tr,value,cls){const td=tr.insertCell();td.textContent=value;
 if(cls)td.className=cls;return td;}
function candidate(row,variant,now,fresh){
 const v=row.models[variant];if(!v)return "No model data";
 if(!Number.isInteger(v.departure)){
  const reason=typeof v.status==="string"?v.status.replaceAll("_"," ").toLowerCase():"unknown";
  return "No departure · "+reason;
 }
 if(!fresh)return "STALE · recheck feed";
 if(v.departure<now-30)return "PASSED · await a fresh forecast";
 const when=v.departure<=now+30?"LEAVE NOW · research only":
    "WATCH · "+duration(v.departure-now);
 const frac=typeof v.fraction==="number"?" · scenario "+Math.round(v.fraction*100)+"%":"";
 return when+" | "+local(v.departure)+" | arrival "+local(v.arrival)+frac;
}
function sortKey(row,now){
 const ds=Object.values(row.models).map(v=>v.departure)
   .filter(x=>Number.isInteger(x)&&x>=now-30);
 return ds.length?Math.min(...ds):9999999999;
}
function render(){
 if(!current)return;
 const now=Math.floor(Date.now()/1000),rows=current.items.slice();
 const fresh=current.healthy && now-current.issued_epoch<=660;
 const q=byId("search").value.trim().toLowerCase(),filter=byId("filter").value;
 const matches=r=>r.item_key.toLowerCase().includes(q)||r.country_name.toLowerCase().includes(q);
 function has(r){return fresh&&Object.values(r.models).some(v=>Number.isInteger(v.departure)&&v.departure>=now-30);}
 function isWatch(r){return has(r)&&Object.values(r.models).some(v=>Number.isInteger(v.departure)&&v.departure>now+30);}
 const filtered=rows.filter(r=>matches(r)&&
  (filter==="all"||(filter==="proposals"&&has(r))||
   (filter==="watch"&&isWatch(r))||(filter==="none"&&!has(r))));
 const sort=byId("sort").value;
 filtered.sort((a,b)=>sort==="country"?a.item_key.localeCompare(b.item_key):
  sortKey(a,now)-sortKey(b,now)||a.item_key.localeCompare(b.item_key));
 const body=byId("rows");body.replaceChildren();
 for(const r of filtered){
  const tr=body.insertRow();
  cell(tr,r.country_name+" · "+r.item);
  cell(tr,r.source_quantity===null?"Unknown":r.source_quantity+" (last observed)");
  cell(tr,candidate(r,"independent",now,fresh));
  cell(tr,candidate(r,"paired_complete",now,fresh));
  const a=r.models.independent,b=r.models.paired_complete;
  const both=has(r)&&Number.isInteger(a.departure)&&Number.isInteger(b.departure)&&
   a.departure>=now-30&&b.departure>=now-30;
  const label=both?(Math.abs(a.departure-b.departure)<=300?
   "AGREE ≤5m · still unvalidated":"DISAGREE · do not assume winner"):
   has(r)?"ONE MODEL ONLY · unvalidated":"NO CURRENT DEPARTURE";
  cell(tr,label,r.available?"status":"status warn");
  cell(tr,duration(r.flight_seconds));
 }
 if(!filtered.length){const tr=body.insertRow();cell(tr,"No matching items").colSpan=6;}
 const valid=rows.filter(has);
 byId("covered").textContent=valid.length+"/24";
 byId("agree").textContent=valid.filter(r=>Number.isInteger(r.models.independent.departure)&&
  Number.isInteger(r.models.paired_complete.departure)&&
  r.models.independent.departure>=now-30&&r.models.paired_complete.departure>=now-30&&
  Math.abs(r.models.independent.departure-r.models.paired_complete.departure)<=300).length;
 byId("updated").textContent=current.issued_epoch?new Date(current.issued_epoch*1000).toLocaleTimeString():"—";
 byId("health").textContent=(!fresh?"NOT FRESH · forecasts hidden. ":
 "LIVE PRIVATE RESEARCH · ")+"Last issue "+local(current.issued_epoch)+
 ", collector heartbeat age at issue "+duration(current.source_heartbeat_age_seconds)+
 ". "+current.note;
 byId("health").className="banners "+(fresh?"good":"warn");
}
async function refresh(){
 try{
  const response=await fetch("/api/live",{cache:"no-store"});
  const data=await response.json();
  if(!data||!Array.isArray(data.items)||data.items.length!==24)
   throw Error("Incomplete research batch or no ledger yet");
  current=data;loadedAt=Date.now();render();
 }catch(err){
  current=null;byId("covered").textContent="0/24";byId("agree").textContent="—";
  byId("health").textContent="LIVE BETA UNAVAILABLE: "+err.message+
   ". Research forecasts are hidden until a complete 24-item batch is available.";
  byId("health").className="banners warn";byId("rows").replaceChildren();
 }
}
for(const id of ["search","filter","sort"])byId(id).addEventListener("input",render);
byId("refresh").addEventListener("click",refresh);
setInterval(()=>{if(current)render();},1000);
setInterval(refresh,30000);refresh();
</script></body></html>"""


def _int(v):
    return type(v) is int


def snapshot(ledger=LEDGER, roster=ROSTER, *, now=None):
    """Return public-safe projections, never raw ledger records or API secrets."""
    now=int(time.time() if now is None else now)
    ledger=Path(ledger)
    if ledger.is_symlink() or not ledger.is_file():
        raise ValueError("V160 private ledger missing or is a symlink")
    roster=Path(roster)
    if roster.is_symlink() or not roster.is_file():
        raise ValueError("V160 pinned roster missing or is a symlink")
    spec=json.loads(roster.read_text(encoding="utf-8"))["items"]
    if not isinstance(spec,dict) or len(spec)!=MAX_ROWS:
        raise ValueError("invalid 24-item roster")
    source=ledger.resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True,timeout=3)) as db:
        db.execute("PRAGMA query_only=ON")
        tick=db.execute(
            "SELECT issued_epoch,captured_epoch,source_heartbeat_epoch,"
            "roster_count,policy_id FROM v160_ticks ORDER BY issued_epoch DESC LIMIT 1"
        ).fetchone()
        if tick is None:
            raise ValueError("V160 has no genuine forward issue yet")
        issued,captured,heartbeat,count,policy=tick
        if policy!=POLICY or count!=MAX_ROWS or not _int(issued) or not _int(captured):
            raise ValueError("invalid V160 issue header")
        raw=db.execute(
            "SELECT item_key,payload_json FROM v160_issued "
            "WHERE issued_epoch=? AND policy_id=? ORDER BY item_key LIMIT 25",
            (issued,POLICY)
        ).fetchall()
    if len(raw)!=MAX_ROWS or {key for key,_ in raw}!=set(spec):
        raise ValueError("incomplete or unknown V160 issuance")
    age=now-issued
    hb_age=issued-heartbeat if _int(heartbeat) else None
    healthy=(0<=age<=MAX_TICK_AGE and 0<=captured-issued<=MAX_CAPTURE_LATENCY
             and hb_age is not None and 0<=hb_age<=MAX_SOURCE_HEARTBEAT_AGE)
    items=[]
    for key,blob in raw:
        country,item=key.split(":",1)
        if country not in FLIGHTS:
            raise ValueError("unknown country")
        data=json.loads(blob)
        if (not isinstance(data,dict) or data.get("item_key")!=key or
            data.get("issued_epoch")!=issued or data.get("policy_id")!=POLICY or
            data.get("research_only") is not True or
            data.get("published_to_website") is not False):
            raise ValueError("invalid or contaminated V160 item issue")
        models=data.get("models")
        if not isinstance(models,dict) or set(models)!=set(VARIANTS):
            raise ValueError("missing V160 model variants")
        public={}
        for name in VARIANTS:
            m=models[name]
            if not isinstance(m,dict):
                raise ValueError("invalid V160 variant payload")
            dep,arr=m.get("departure_epoch"),m.get("arrival_epoch")
            if dep is not None and (
                not _int(dep) or not _int(arr) or
                not issued<=dep<=issued+28800 or arr!=dep+FLIGHTS[country]
                or m.get("wait_seconds")!=dep-issued):
                raise ValueError("invalid flight geometry")
            if dep is None and (arr is not None or m.get("wait_seconds") is not None):
                raise ValueError("invalid abstention")
            frac=m.get("scenario_fraction")
            if frac is not None and (
                type(frac) not in (float,int) or not 0<=frac<=1):
                raise ValueError("invalid scenario fraction")
            # A stale recommendation is never given a departure timestamp.
            public[name]={
                "departure":dep if healthy and dep is not None and dep>=now-30 else None,
                "arrival":arr if healthy and dep is not None and dep>=now-30 else None,
                "fraction":float(frac) if healthy and dep is not None and dep>=now-30 and frac is not None else None,
                "status":m.get("status") if isinstance(m.get("status"),str) else "UNKNOWN",
            }
        qty=data.get("source_last_qty")
        items.append({
            "item_key":key,"country_name":COUNTRIES[country],"item":item,
            "flight_seconds":FLIGHTS[country],
            "source_quantity":qty if _int(qty) and qty>=0 else None,
            "models":public,
            "available":any(v["departure"] is not None for v in public.values()),
        })
    return {
        "status":"V160_PRIVATE_LIVE_RESEARCH_BETA",
        "healthy":healthy,"issued_epoch":issued,"captured_epoch":captured,
        "source_heartbeat_age_seconds":hb_age,
        "items":items,"min_arrival_stock":MIN_STOCK,
        "recorded_items":len(items),"research_only":True,
        "country_provider_freshness_verified":False,
        "actual_player_flights_verified":False,
        "note":"Models are provisional; future WATCH must be reconfirmed near departure.",
    }


def handler_factory(ledger=LEDGER,roster=ROSTER):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path=self.path.split("?",1)[0]
            if path=="/":
                content=HTML.encode("utf-8")
                code=200;mime="text/html; charset=utf-8"
            elif path=="/api/live":
                try:
                    data=snapshot(ledger,roster)
                    code=200 if data["healthy"] else 503
                except (ValueError,KeyError,TypeError,sqlite3.Error,OSError,UnicodeError,json.JSONDecodeError):
                    data={"status":"RESEARCH_UNAVAILABLE","items":[],
                          "note":"Missing, incomplete or invalid V160 research evidence."}
                    code=503
                content=json.dumps(data,separators=(",",":"),sort_keys=True).encode()
                mime="application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(code)
            self.send_header("Content-Type",mime)
            self.send_header("Content-Length",str(len(content)))
            self.send_header("Cache-Control","no-store, max-age=0")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(content)
        def log_message(self,fmt,*args):
            return
    return Handler


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port",type=int,default=8765)
    a=p.parse_args()
    if not 1024<=a.port<=65535:
        p.error("port must be between 1024 and 65535")
    # No public bind option: private beta can only be reached through SSH.
    with ThreadingHTTPServer(("127.0.0.1",a.port),handler_factory()) as server:
        print("V160 private research beta listening on 127.0.0.1:"+str(a.port),flush=True)
        server.serve_forever()


if __name__=="__main__":
    main()
