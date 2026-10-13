#!/usr/bin/env python3
"""Standalone, loopback-only 24-item live V160 research board.

Only reads the isolated prospective SQLite ledger. Does not import or alter
the production web app, collector, specialist timers or either existing page.
Launch on the VM and reach it through an SSH local port-forward.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import threading
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
RECHECK_HELPER = Path("/home/ubuntu/torn-fren-private-models/v160_single_item_recheck.py")
RECHECK_PYTHON = Path("/home/ubuntu/torn-fren-v38-probe/.venv/bin/python")
RECHECK_TIMEOUT_SECONDS = 65
RECHECK_COOLDOWN_SECONDS = 20
_RECHECK_MUTEX = threading.Lock()
_RECHECK_LAST = {}
# V128's actual exact_roster() adds the two V42-approved generic Xanax
# specialists to the original 22-key v38_roster.json. This standalone
# stdlib-only reader must reconstruct the SAME keys without importing V128.
BASE_ROSTER_ROWS = 22
EXTRA_XANAX_KEYS = frozenset(("can:Xanax", "uni:Xanax"))
HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-store">
<title>TORN-FREN · Departure Planner Beta</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0f1721;color:#eaf2fa;font-size:14px}
*{box-sizing:border-box}body{max-width:1450px;margin:auto;padding:20px}
h1{font-size:1.7rem;margin:0 0 5px}h2{font-size:1.15rem;margin:0 0 8px}
p{line-height:1.55;margin:6px 0}.muted{color:#a7b9cc}.sub{font-size:.85rem;color:#9eb1c1}
a{color:#91d6ff}.head{display:flex;justify-content:space-between;align-items:start;gap:14px;flex-wrap:wrap}
.meta{margin:9px 0 16px;color:#bfd2e1}.banner{padding:13px 15px;border:1px solid #42576b;border-radius:9px;background:#1b2b39;margin:12px 0}
.banner.fault{border-color:#a56950;background:#392520}.banner.good{border-color:#426a61}
.stats{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:11px;margin:14px 0 20px}
.stat{padding:13px;background:#192735;border:1px solid #354a5f;border-radius:9px}
.stat b{font-size:1.45rem;display:block;margin-bottom:3px}.stat span{color:#b1c1d0;font-size:.84rem}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:0 0 18px}
.panel{padding:15px;background:#16232f;border:1px solid #33485b;border-radius:10px;min-height:150px}
.opportunity{border-top:1px solid #2e4154;padding:11px 0}
.opportunity:first-of-type{border-top:0}.opportunity strong{display:block}
.opportunity .why{font-size:.85rem;color:#adc2d4;margin:4px 0}
.tag{display:inline-block;padding:3px 7px;border-radius:5px;font-weight:650;font-size:.75rem;background:#334557;color:#d8e8f5}
.tag.watch{background:#244b48;color:#a6f2d1}
.tag.review{background:#55442a;color:#f8d8a1}
.tag.none{background:#3b4249;color:#c4cfda}
.controls{display:flex;gap:11px;align-items:end;flex-wrap:wrap;margin:15px 0}
label{font-size:.88rem}label>*{display:block;margin-top:5px}
input,select,button{font:inherit;color:inherit;background:#223343;border:1px solid #516b80;border-radius:7px;padding:9px}
button{cursor:pointer}button:focus,select:focus,input:focus{outline:2px solid #8bd4ff}
.tablewrap{overflow:auto;border:1px solid #34485b;border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:1060px}
th{text-align:left;background:#243446;color:#e6f2fb;white-space:nowrap}
th,td{padding:12px 10px;vertical-align:top;border-bottom:1px solid #2d3f50}
tbody tr:hover{background:#1a2a38}.small{font-size:.84rem;color:#aec0d0;line-height:1.45}
.when{font-variant-numeric:tabular-nums;font-weight:700}.hint{font-size:.78rem;color:#c3b5a0;margin-top:3px}
.countdown{font-variant-numeric:tabular-nums;color:#b2f2d5}
footer{padding:20px 2px;color:#a7bacb;font-size:.84rem;line-height:1.6}
@media(max-width:800px){body{padding:12px}.stats{grid-template-columns:repeat(2,minmax(130px,1fr))}.columns{grid-template-columns:1fr}}
</style></head>
<body>
<header class="head"><div><h1>Where should I fly?</h1>
<p class="meta">TORN-FREN · 24-item departure planner · latest genuine V160 research issues</p></div>
<button id="refresh">Refresh predictions</button></header>
<div class="banner"><strong>Provisional guidance—not verified stock on landing.</strong>
 A model finding a supported arrival at its issue time does not mean it will still be safe minutes later.
 The site separates upcoming windows, recent NOW signals requiring another check, and true abstentions.
 <span class="muted"> ≥30 stock at arrival · PI + pilot flights · 5-minute research updates.</span></div>
<div id="health" class="banner" role="status">Connecting to private prospective ledger…</div>
<section class="stats" aria-label="Research signal counts">
<div class="stat"><b id="availableCount">—</b><span>Future / currently due forecasts</span></div>
<div class="stat"><b id="recheckCount">—</b><span>Recent NOW signals to reconfirm</span></div>
<div class="stat"><b id="noCount">—</b><span>Without a usable proposal</span></div>
<div class="stat"><b id="agreeCount">—</b><span>Both variants agree ≤5 min</span></div>
<div class="stat"><b id="nextTick">—</b><span>Next planned 5-min issue</span></div>
</section>
<section class="panel" id="singleCheck" style="margin:12px 0 18px">
<h2>Check one item right now</h2>
<p class="small">Uses the current collector snapshot to recalculate both models for the selected item, rather than relying on a five-minute-old NOW signal. Research-only, not guaranteed stock; results expire quickly. This preview is not added to forward-accuracy metrics.</p>
<div class="controls"><label>Destination / item<select id="recheckItem"><option value="">Select an item</option></select></label>
<button id="checkNow" type="button">Recalculate this item NOW</button></div>
<div id="recheckOutput" class="banner">Select an item, then request a fresh one-item calculation.</div>
</section>
<div class="columns">
<section class="panel"><h2>Upcoming departure opportunities</h2>
<p class="small">Scheduled WATCH signals from this issue. Check again near departure before acting.</p>
<div id="upcoming"></div></section>
<section class="panel"><h2>Recently indicated “leave now”</h2>
<p class="small">These models recommended departing at their issue timestamp. The timestamp has passed; this is a prompt to reconfirm, <strong>not</strong> a fresh departure instruction.</p>
<div id="recheck"></div></section></div>
<h2>All 24 items and why</h2>
<div class="controls">
<label>Search<input type="search" id="search" placeholder="Country or item"></label>
<label>Decisions<select id="filter"><option value="all">All items</option>
<option value="upcoming">Upcoming / due</option><option value="recheck">Reconfirm NOW signal</option>
<option value="none">No candidate / passed</option></select></label>
<label>Sort<select id="sort"><option value="priority">Decision priority</option>
<option value="time">Departure time</option><option value="country">Country / item</option></select></label>
</div>
<div class="tablewrap"><table><thead><tr><th>Destination / item</th><th>Observed stock</th>
<th>Independent</th><th>Paired</th><th>What to do next</th><th>Flight</th></tr></thead>
<tbody id="rows"><tr><td colspan="6">Loading…</td></tr></tbody></table></div>
<footer>The “last observed” quantity can be high even if the model predicts that stock will be sold before your flight arrives. The model's scenario fraction is <strong>not</strong> a validated success probability. A missing proposal means no departure met the current model's criteria, not that restocking will never happen.
 Neither country-specific provider freshness nor player flights have been verified. The original V2 detailed graph and deployed experimental dashboard remain unchanged.</footer>
<script>
"use strict";
let latest=null;
const el=id=>document.getElementById(id);
const clock=t=>Number.isInteger(t)?new Date(t*1000).toLocaleTimeString():"—";
const local=t=>Number.isInteger(t)?new Date(t*1000).toLocaleString():"—";
function span(seconds){
 if(!Number.isFinite(seconds))return "—";
 const n=Math.max(0,Math.floor(seconds)),h=Math.floor(n/3600),m=Math.floor((n%3600)/60),s=n%60;
 return h>0?h+"h "+m+"m":m+"m "+s+"s";
}
function addCell(tr,main,cls,sub){
 const td=tr.insertCell(),strong=document.createElement("div");strong.textContent=main;
 if(cls)strong.className=cls;td.append(strong);
 if(sub){const small=document.createElement("div");small.className="small";small.textContent=sub;td.append(small);}
 return td;
}
function classify(row,now,healthy){
 const all=Object.values(row.models);
 if(!healthy)return "stale";
 if(all.some(v=>v.signal==="FUTURE_WATCH"||v.signal==="DUE_NOW")&&
    all.some(v=>Number.isInteger(v.departure)&&v.departure>=now-30))return "upcoming";
 if(all.some(v=>v.signal==="RECENT_ISSUED_NOW_RECHECK"||
          (v.issued_now && v.issued_departure!==null && now-v.issued_departure<300 && now>=v.issued_departure)))return "recheck";
 return "none";
}
function proposalText(v,now,healthy){
 if(!healthy)return ["STALE · no live guidance","Wait for a current complete issue"];
 if(v.signal==="FUTURE_WATCH")return ["WATCH · leave in "+span(v.departure-now),
   "Depart "+local(v.departure)+" · arrive "+local(v.arrival)+" · modeled "+Math.round((v.fraction||0)*100)+"%"];
 if(v.signal==="DUE_NOW")return ["DUE NOW · research only",
   "As issued "+local(v.issued_departure)+" · projected arrival "+local(v.issued_arrival)];
 if(v.signal==="RECENT_ISSUED_NOW_RECHECK")return ["RECHECK NOW SIGNAL",
   "Model said leave at "+clock(v.issued_departure)+" · refresh before flight"];
 if(v.signal==="DEPARTURE_PASSED")return ["MISSED ISSUE-TIME WINDOW",
   "Last proposed departure "+clock(v.issued_departure)+" · await next issue"];
 if(v.signal==="STALE_RESEARCH_ISSUE")return ["STALE · recheck feed",
   "Prior issue "+clock(v.issued_departure)];
 const reason=(v.status||"unknown").replaceAll("_"," ").toLowerCase();
 return ["NO QUALIFYING DEPARTURE",reason];
}
function firstDeparture(row,now){
 return Math.min(...Object.values(row.models).map(v=>v.departure)
     .filter(x=>Number.isInteger(x)&&x>=now-30).concat([9999999999]));
}
function render(){
 if(!latest)return;
 const now=Math.floor(Date.now()/1000);
 const healthy=latest.healthy && now-latest.issued_epoch<=660;
 const items=latest.items.map(r=>({...r,decision:classify(r,now,healthy)}));
 const upcoming=items.filter(r=>r.decision==="upcoming")
   .sort((a,b)=>firstDeparture(a,now)-firstDeparture(b,now));
 const recheck=items.filter(r=>r.decision==="recheck")
   .sort((a,b)=>b.source_quantity-a.source_quantity);
 el("availableCount").textContent=upcoming.length+"/24";
 el("recheckCount").textContent=recheck.length;
 el("noCount").textContent=items.filter(r=>r.decision==="none"||r.decision==="stale").length;
 el("agreeCount").textContent=items.filter(r=>{
   const a=r.models.independent,b=r.models.paired_complete;
   return r.decision!=="stale" && a.issued_departure!==null && b.issued_departure!==null &&
      Math.abs(a.issued_departure-b.issued_departure)<=300;
 }).length;
 el("nextTick").textContent=span(latest.issued_epoch+300-now);
 el("health").textContent=(healthy?"Research feed current":"Research feed STALE · no actionable forecasts")+" · issued "+local(latest.issued_epoch)+
   " · "+span(now-latest.issued_epoch)+" ago · collector heartbeat age at issue "+span(latest.source_heartbeat_age_seconds)+
   ". Next five-minute refresh is an estimate, not guaranteed.";
 el("health").className="banner "+(healthy?"good":"fault");
 function paintCards(target,list,state){
  target.replaceChildren();
  if(!list.length){const p=document.createElement("p");p.className="small";
    p.textContent=healthy?"None at this snapshot. Check the next issue.":"Current feed unavailable; no recommendations.";target.append(p);return;}
  for(const row of list.slice(0,8)){
   const box=document.createElement("div");box.className="opportunity";
   const name=document.createElement("strong");name.textContent=row.country_name+" · "+row.item;box.append(name);
   const tag=document.createElement("div");tag.className="why";
   const models=Object.entries(row.models).filter(([k,v])=>
      state==="upcoming"?Number.isInteger(v.departure)&&v.departure>=now-30:v.signal==="RECENT_ISSUED_NOW_RECHECK");
   const details=models.map(([k,v])=>k.replace("_complete","")+" — "+
      (state==="upcoming"?"in "+span(v.departure-now)+" ("+clock(v.departure)+")":"said NOW at "+clock(v.issued_departure)));
   tag.textContent=details.join(" · ");box.append(tag);
   const sub=document.createElement("div");sub.className="small";
   sub.textContent="Flight "+span(row.flight_seconds)+
    " · last observed "+(row.source_quantity===null?"unknown":row.source_quantity)+
    " · "+(state==="upcoming"?"Reconfirm near departure":"Recheck next fresh issue; not a live NOW recommendation");
   box.append(sub);target.append(box);
  }
 }
 paintCards(el("upcoming"),upcoming,"upcoming");
 paintCards(el("recheck"),recheck,"recheck");
 const q=el("search").value.trim().toLowerCase(),filter=el("filter").value;
 const rows=items.filter(r=>(r.item_key+" "+r.country_name).toLowerCase().includes(q)
    &&(filter==="all"||filter===r.decision||(filter==="none"&&(r.decision==="none"||r.decision==="stale"))));
 if(el("sort").value==="country")rows.sort((a,b)=>a.item_key.localeCompare(b.item_key));
 else if(el("sort").value==="time")rows.sort((a,b)=>firstDeparture(a,now)-firstDeparture(b,now)||a.item_key.localeCompare(b.item_key));
 else {
  const priority={upcoming:0,recheck:1,none:2,stale:3};
  rows.sort((a,b)=>priority[a.decision]-priority[b.decision]||
    firstDeparture(a,now)-firstDeparture(b,now)||a.item_key.localeCompare(b.item_key));
 }
 const tbody=el("rows");tbody.replaceChildren();
 for(const row of rows){
  const tr=tbody.insertRow();
  addCell(tr,row.country_name+" · "+row.item,"",row.phase?"Latest phase "+row.phase:"");
  addCell(tr,row.source_quantity===null?"Unknown":String(row.source_quantity),"when",
    row.source_last_epoch?"Observed "+clock(row.source_last_epoch):"Last observed, age unknown");
  for(const name of ["independent","paired_complete"]){
   const [main,sub]=proposalText(row.models[name],now,healthy);
   addCell(tr,main,"when",sub);
  }
  const action={
    upcoming:["WATCH / DUE","Verify fresh signal near departure"],
    recheck:["RECHECK NOW","Previously issued leave-now; do not assume it remains valid"],
    none:["NO SUPPORTED WINDOW","Keep monitoring; do not infer arrival stock from current quantity"],
    stale:["FEED STALE","Wait for valid collection and reissue"]
  }[row.decision];
  addCell(tr,action[0],"when",action[1]);
  addCell(tr,span(row.flight_seconds),"small");
 }
 if(!rows.length){const tr=tbody.insertRow();addCell(tr,"No matching items").colSpan=6;}
}
function populateRecheckSelect(items){
 const sel=el("recheckItem"),chosen=sel.value;
 sel.replaceChildren();
 const def=document.createElement("option");def.value="";def.textContent="Select an item";sel.append(def);
 for(const r of items.slice().sort((a,b)=>(a.country_name+" "+a.item).localeCompare(b.country_name+" "+b.item))){
  const opt=document.createElement("option");opt.value=r.item_key;opt.textContent=r.country_name+" · "+r.item;sel.append(opt);
 }
 if(items.some(x=>x.item_key===chosen))sel.value=chosen;
}
async function recheckNow(){
 const key=el("recheckItem").value;
 if(!key){el("recheckOutput").textContent="Select an item first.";return;}
 const button=el("checkNow");button.disabled=true;
 el("recheckOutput").textContent="Calculating from current observed history. This may take a little while…";
 try{
  const response=await fetch("/api/recheck",{method:"POST",cache:"no-store",
    headers:{"Content-Type":"application/json","X-Torn-Fren-Action":"user-recheck"},
    body:JSON.stringify({item_key:key})});
  const r=await response.json();
  if(!response.ok||r.status!=="CURRENT_ITEM_RECHECK_RESEARCH_ONLY")
    throw Error(r.note||"Current research check unavailable (HTTP "+response.status+")");
  const age=Math.floor(Date.now()/1000)-r.issued_epoch;
  const messages=[];
  for(const name of ["independent","paired_complete"]){
   const m=r.models[name],label=name==="paired_complete"?"Paired":"Independent";
   if(!Number.isInteger(m.departure_epoch)){messages.push(label+": no qualifying departure ("+
    (m.status||"unknown").replaceAll("_"," ")+")");continue;}
   if(age>30){messages.push(label+": calculation is already >30s old; recheck again");continue;}
   const when=m.departure_epoch<=r.issued_epoch+30?
     "NOW, provisionally (checked "+clock(r.issued_epoch)+")":
     "WATCH "+clock(m.departure_epoch)+" · in "+span(m.departure_epoch-Math.floor(Date.now()/1000));
   messages.push(label+": "+when+"; modeled arrival "+local(m.arrival_epoch)+
      "; scenario support "+Math.round(m.scenario_stock_fraction*100)+"%"+
      (m.sustained_five_minute_support===false?"; narrow NOW window":""));
  }
  el("recheckOutput").textContent=key+" · freshly checked "+local(r.issued_epoch)+
   " · last observed quantity "+(r.source_last_quantity??"unknown")+" · flight "+span(r.flight_seconds)+
   ". "+messages.join(" | ")+". Provisional model support only, not a validated player arrival.";
  el("recheckOutput").className="banner "+(age>30?"fault":"good");
 }catch(e){el("recheckOutput").textContent="Recheck failed: "+e.message+
   ". No new departure time is authorized.";el("recheckOutput").className="banner fault";}
 finally{button.disabled=false;}
}
el("checkNow").addEventListener("click",recheckNow);
async function refresh(){
 try{
  const response=await fetch("/api/live",{cache:"no-store"});
  const data=await response.json();
  if(!Array.isArray(data.items)||data.items.length!==24)
   throw Error("Missing or incomplete V160 private batch");
  latest=data;populateRecheckSelect(data.items);render();
 }catch(e){
  latest=null;
  el("health").className="banner fault";
  el("health").textContent="Research unavailable: "+e.message+". No departure instructions.";
  for(const name of ["availableCount","recheckCount","noCount","agreeCount","nextTick"])el(name).textContent="—";
  for(const name of ["upcoming","recheck","rows"])el(name).replaceChildren();
 }
}
for(const name of ["search","filter","sort"])el(name).addEventListener("input",render);
el("refresh").addEventListener("click",refresh);
setInterval(()=>{if(latest)render();},1000);
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
    payload=json.loads(roster.read_text(encoding="utf-8"))
    spec=payload.get("items") if isinstance(payload,dict) else None
    if (not isinstance(spec,dict) or len(spec)!=BASE_ROSTER_ROWS or
        not all(isinstance(k,str) and k.count(":")==1 and
                k.split(":",1)[0] in FLIGHTS and isinstance(meta,dict)
                for k,meta in spec.items()) or
        not EXTRA_XANAX_KEYS.isdisjoint(spec)):
        raise ValueError("invalid 22-item pinned base roster")
    # Mirror research.v128_full24_earliest_shadow.exact_roster() precisely.
    identities=set(spec)|EXTRA_XANAX_KEYS
    if len(identities)!=MAX_ROWS:
        raise ValueError("invalid reconstructed 24-item roster")
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
    if (len(raw)!=MAX_ROWS or len({key for key,_ in raw})!=MAX_ROWS or
        {key for key,_ in raw}!=identities):
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
            # The previous viewer erased any NOW forecast after 30 seconds,
            # then mislabeled a genuine V151 candidate as 'No departure'.
            # Retain its *as-issued* evidence separately, NEVER turn an
            # expired issue-time forecast into a new actionable prediction.
            if dep is None:
                signal="NO_MODEL_CANDIDATE"
            elif not healthy:
                signal="STALE_RESEARCH_ISSUE"
            elif dep>=now-30:
                signal="DUE_NOW" if dep<=now+30 else "FUTURE_WATCH"
            elif dep<=issued+30 and now<issued+300:
                signal="RECENT_ISSUED_NOW_RECHECK"
            else:
                signal="DEPARTURE_PASSED"
            actionable_window=signal in ("DUE_NOW","FUTURE_WATCH")
            public[name]={
                "departure":dep if actionable_window else None,
                "arrival":arr if actionable_window else None,
                "fraction":float(frac) if actionable_window and frac is not None else None,
                "status":m.get("status") if isinstance(m.get("status"),str) else "UNKNOWN",
                "signal":signal,
                "issued_departure":dep,
                "issued_arrival":arr,
                "issued_fraction":float(frac) if frac is not None else None,
                "issued_now":dep is not None and dep<=issued+30,
            }
        qty=data.get("source_last_qty")
        items.append({
            "item_key":key,"country_name":COUNTRIES[country],"item":item,
            "flight_seconds":FLIGHTS[country],
            "source_quantity":qty if _int(qty) and qty>=0 else None,
            "source_last_epoch":data.get("source_last_epoch")
                if _int(data.get("source_last_epoch")) else None,
            "source_provider":data.get("source_last_provider")
                if data.get("source_last_provider") in ("yata","prometheus") else None,
            "phase":data.get("phase") if data.get("phase") in ("HIGH","LOW") else None,
            "models":public,
            "available":any(v["departure"] is not None for v in public.values()),
            "recent_now_signal":any(
                v["signal"]=="RECENT_ISSUED_NOW_RECHECK"
                for v in public.values()),
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


def handler_factory(ledger=LEDGER,roster=ROSTER,
                    helper=RECHECK_HELPER,python=RECHECK_PYTHON,
                    work=Path("/home/ubuntu/torn-fren-v38-probe")):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path!="/api/recheck":
                self.send_error(404)
                return
            # Localhost is not sufficient against cross-origin browser POSTs.
            if (self.headers.get("X-Torn-Fren-Action")!="user-recheck" or
                self.headers.get("Origin") not in (None,"http://127.0.0.1:8765")):
                self.send_error(403)
                return
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 2<=length<=180:
                    raise ValueError("invalid request size")
                body=json.loads(self.rfile.read(length))
                key=body["item_key"]
                if not isinstance(key,str):
                    raise ValueError("invalid identity")
                ledger_data=snapshot(ledger,roster)
                if not ledger_data["healthy"] or key not in {
                    row["item_key"] for row in ledger_data["items"]}:
                    raise ValueError("stale/invalid private item")
            except (ValueError,KeyError,TypeError,sqlite3.Error,OSError):
                self._json(503,{"status":"RECHECK_UNAVAILABLE",
                    "note":"No fresh research snapshot or invalid item"})
                return
            if not _RECHECK_MUTEX.acquire(blocking=False):
                self._json(429,{"status":"RECHECK_BUSY",
                    "note":"Another item is being checked; retry shortly"})
                return
            try:
                now=time.monotonic()
                if now-_RECHECK_LAST.get(key,-1e9)<RECHECK_COOLDOWN_SECONDS:
                    self._json(429,{"status":"RECHECK_COOLDOWN",
                        "note":"This item was checked recently; wait 20 seconds"})
                    return
                _RECHECK_LAST[key]=now
                if (not Path(helper).is_file() or Path(helper).is_symlink()
                    or not Path(python).is_file()):
                    self._json(503,{"status":"RECHECK_UNAVAILABLE",
                        "note":"Pinned one-item recheck helper is not installed"})
                    return
                run=subprocess.run(
                    [str(python),"-I",str(helper),key],
                    cwd=str(work),
                    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",
                             OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",
                             MKL_NUM_THREADS="1"),
                    text=True,capture_output=True,timeout=RECHECK_TIMEOUT_SECONDS,
                    check=False)
                if run.returncode or len(run.stdout)>12000:
                    self._json(503,{"status":"RECHECK_UNAVAILABLE",
                        "note":"Live one-item forecast could not be safely computed"})
                    return
                result=json.loads(run.stdout)
                if (result.get("item_key")!=key
                    or result.get("status")!="CURRENT_ITEM_RECHECK_RESEARCH_ONLY"
                    or result.get("private_ledger_written") is not False
                    or result.get("collector_written") is not False):
                    raise ValueError("invalid recheck result")
                self._json(200,result)
            except (subprocess.TimeoutExpired,ValueError,TypeError,KeyError,
                    OSError,json.JSONDecodeError):
                self._json(503,{"status":"RECHECK_UNAVAILABLE",
                    "note":"Timed out or invalid recheck; no travel recommendation"})
            finally:
                _RECHECK_MUTEX.release()

        def _json(self,code,data):
            content=json.dumps(data,separators=(",",":"),sort_keys=True).encode()
            self.send_response(code)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Content-Length",str(len(content)))
            self.send_header("Cache-Control","no-store, max-age=0")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Access-Control-Allow-Origin","http://127.0.0.1:8765")
            self.end_headers()
            self.wfile.write(content)

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
