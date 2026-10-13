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
<meta http-equiv="Cache-Control" content="no-store"><title>TORN-FREN · Travel Decisions</title>
<style>
:root{color-scheme:dark;font:15px system-ui,-apple-system,Segoe UI,sans-serif;background:#0d1520;color:#eef4fa}
*{box-sizing:border-box}body{max-width:1310px;margin:auto;padding:22px}
h1{font-size:2rem;letter-spacing:-.035em;margin:4px 0}h2{font-size:1.15rem;margin:0 0 12px}h3{font-size:1rem;margin:0}
p{line-height:1.5}button,input,select{font:inherit;color:inherit;background:#233347;border:1px solid #53677a;border-radius:8px;padding:11px}
button{cursor:pointer}button:disabled{opacity:.5;cursor:wait}button:focus,input:focus,select:focus,summary:focus{outline:2px solid #8ccdfc}
button.primary{background:#345d91;border-color:#6294c8;font-weight:700}
button.tiny{font-size:.85rem;padding:8px 12px}
.muted{color:#a8bbcd}.small{font-size:.86rem}.eyebrow{color:#83b8e7;font-size:.8rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
.head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
.head p{margin:0;color:#a8bbcd}.shell{background:#162333;border:1px solid #334d62;border-radius:14px;padding:20px;margin:15px 0}
.notice{padding:12px 14px;background:#1a2939;border-left:3px solid #7a99b9;border-radius:7px;margin:14px 0;font-size:.9rem}
.health{padding:10px 14px;border-radius:8px;background:#142d2c;border:1px solid #375b55;color:#b8ebda;margin:12px 0}
.health.bad{background:#3b2525;border-color:#a45c5c;color:#ffcece}
.health strong{margin-right:8px}.pill{display:inline-block;padding:4px 8px;border-radius:7px;background:#384e63;font-size:.78rem;font-weight:700}
.pill.watch{background:#2e554f;color:#b3edd4}.pill.review{background:#594527;color:#f7deab}.pill.none{background:#414953;color:#d7dfeb}
.hero{display:grid;grid-template-columns:minmax(230px,1fr) minmax(220px,1fr);gap:22px;align-items:center}
.big{font-size:2.2rem;line-height:1.2;font-weight:800;letter-spacing:-.03em;margin:8px 0}
.actiontime{font-size:1.6rem;line-height:1.2;font-weight:750;margin:6px 0}
.support{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:15px 0}
.support div{padding:12px;border:1px solid #375064;border-radius:9px}
.support b{display:block;font-size:1.1rem;margin:4px 0}
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.card{background:#182737;border:1px solid #354f62;padding:16px;border-radius:11px}
.card strong{display:block;font-size:1.08rem}.card .time{font-size:1.45rem;font-weight:750;font-variant-numeric:tabular-nums;margin:9px 0 3px}
.card .row{display:flex;justify-content:space-between;align-items:start;gap:12px}
.meta{color:#b7c7d4;font-size:.86rem;line-height:1.55;margin-top:7px}
.buttons{display:flex;align-items:end;flex-wrap:wrap;gap:12px}
.control{display:flex;flex-direction:column;gap:6px;font-size:.89rem}
.control select{min-width:240px;max-width:100%}
.checkresult{min-height:75px;padding:16px;background:#0f1c2a;border:1px solid #3b5164;border-radius:10px;margin-top:13px}
.checkresult .big{font-size:1.8rem}.checkresult.error{border-color:#8d5c5c}
.sep{height:1px;background:#304457;margin:17px 0}
details{margin:16px 0;padding:14px 18px;background:#152230;border:1px solid #33485b;border-radius:12px}
summary{cursor:pointer;font-weight:700;font-size:1.02rem}
.tablewrap{overflow:auto;margin-top:14px}table{width:100%;border-collapse:collapse;min-width:860px}
th,td{text-align:left;border-bottom:1px solid #304455;padding:10px;vertical-align:top}
th{color:#c3d8e9}.sub{font-size:.8rem;color:#9caebe}
footer{margin:23px 0;color:#9cafbf;font-size:.82rem;line-height:1.6}
@media(max-width:760px){body{padding:12px}.hero,.cards{grid-template-columns:1fr}.support{grid-template-columns:1fr 1fr}.big{font-size:1.8rem}}
</style></head><body>
<header class="head"><div>
<span class="eyebrow">TORN-FREN · 24-item private beta</span>
<h1>Where should I fly?</h1>
<p>Departure times first. Research details only if you want them.</p></div>
<button id="refresh" class="tiny">Refresh forecast</button></header>
<div class="notice"><strong>Provisional guidance.</strong> Our models estimate the earliest flight likely to arrive while stock is ≥30.
<strong>Actual live success rate: not yet established.</strong> A scenario percentage is not a verified chance of success.
All departure windows require a fresh check before you travel.</div>
<div id="health" class="health" role="status">Checking the latest five-minute predictions…</div>
<section class="shell" aria-label="Top next opportunity">
<span class="eyebrow">Earliest upcoming departure</span>
<div class="hero"><div><h2 id="heroItem" class="big">Loading…</h2>
<div id="heroState" class="pill review">Checking</div>
<p id="heroWhy" class="muted">Waiting for a complete V160 forecast.</p></div>
<div><div id="heroTime" class="actiontime">—</div><div id="heroArrival" class="muted">—</div>
<div id="heroFlight" class="meta">—</div>
<button id="heroCheck" type="button" class="primary" style="margin-top:13px">Check this item NOW</button>
</div></div>
</section>
<div class="support"><div><span class="small muted">Upcoming windows</span><b id="upcomingCount">—</b></div>
<div><span class="small muted">Previous leave-now signals</span><b id="recheckCount">—</b></div>
<div><span class="small muted">No supported window</span><b id="noneCount">—</b></div></div>
<section class="shell">
<h2>Next departure windows</h2>
<p class="muted small">Arranged by earliest time to leave—not by estimated profit or proven accuracy.</p>
<div class="cards" id="upcoming"><p class="muted">Loading…</p></div></section>
<section class="shell">
<h2>Want to check an item before flying?</h2>
<p class="muted small">Recalculate from the collector right now. This is a new research estimate, not a guaranteed stock prediction.</p>
<div class="buttons"><label class="control">Country / item
<select id="recheckItem"><option value="">Choose item</option></select></label>
<button class="primary" id="checkNow" type="button">Recalculate this item NOW</button></div>
<div id="recheckOutput" class="checkresult" aria-live="polite"><strong>Pick an item to get a fresh departure estimate.</strong>
<p class="muted small">You will see whether to leave now, leave later, or wait for a better forecast.</p></div>
</section>
<section class="shell">
<h2>Recently indicated “leave now”</h2>
<p class="muted small">The previous issue-time recommendation has passed. These are <strong>RECHECK NOW SIGNAL</strong> items—not permission to depart based on an old timestamp.</p>
<div class="cards" id="recheckCards"></div></section>
<details id="technical"><summary>Show all 24 items and technical model details</summary>
<p class="muted small">Independent and paired models may disagree. Scenario support is based on simulations, not observed forward hit rates. Terms: FUTURE_WATCH = estimated later departure; RECENT_ISSUED_NOW_RECHECK = an expired issue-time NOW forecast.</p>
<div class="tablewrap"><table><thead><tr><th>Item</th><th>Stock last seen</th><th>Independent</th><th>Paired</th><th>Next step</th></tr></thead>
<tbody id="rows"><tr><td colspan="5">Loading…</td></tr></tbody></table></div>
</details>
<footer>All times use your device timezone. Stock-history timestamps show last quantity CHANGE, not last successful POLL; unchanged zero remains meaningful. Current stock is NOT the stock guaranteed when you land. Flight times assume PI + pilot. All 24 items remain displayed in technical details; the original V2 graph, experimental dashboard and V160 recorder are unchanged.</footer>
<script>
"use strict";
let latest=null,selectedHero=null,lastCheck=null,lastCheckExpired=false;
const el=id=>document.getElementById(id);
const clock=t=>Number.isInteger(t)?new Date(t*1000).toLocaleTimeString([], {hour:"numeric",minute:"2-digit"}):"—";
const absolute=t=>Number.isInteger(t)?new Date(t*1000).toLocaleString():"—";
const elapsed=n=>{if(!Number.isFinite(n))return "—";let x=Math.max(0,Math.round(n));
 let h=Math.floor(x/3600),m=Math.floor(x%3600/60),s=x%60;
 return h?h+"h "+m+"m":m?m+"m "+s+"s":s+"s";};
function node(type,txt,cls){const x=document.createElement(type);x.textContent=txt;
 if(cls)x.className=cls;return x;}
function add(parent,type,txt,cls){const x=node(type,txt,cls);parent.append(x);return x;}
const currentTime=()=>Math.floor(Date.now()/1000);
// stock_history stores DELTAS (quantity changes), not each poll cycle.
// An unchanged zero for 13 minutes is ordinary and is not by itself stale.
// V160's separate global successful-poll heartbeat guards issue freshness;
// V88 validates arrival states using actual bracketing poll heartbeats.
function lastStockChangeAge(row,now){return Number.isInteger(row.source_last_epoch)?
 Math.max(0,now-row.source_last_epoch):null;}
function fresh(){return !!latest&&latest.healthy && currentTime()-latest.issued_epoch<=660;}
function variants(row){return Object.entries(row.models);}
function future(row,now){return variants(row).filter(([name,m])=>
 Number.isInteger(m.departure)&&m.departure>=now-30);}
function priority(row,now){return future(row,now).reduce((p,[name,m])=>Math.min(p,m.departure),Infinity);}
function signal(row,now){
 if(!fresh())return "STALE";
 if(future(row,now).length)return "WATCH";
 if(variants(row).some(([name,m])=>m.signal==="RECENT_ISSUED_NOW_RECHECK"||
   (m.issued_now && Number.isInteger(m.issued_departure)&&now-m.issued_departure>=0&&now-m.issued_departure<300)))
   return "RECHECK";
 return "NONE";
}
function diagnose(row,now){
 let futureModels=future(row,now);
 if(!futureModels.length)return null;
 futureModels.sort((a,b)=>a[1].departure-b[1].departure);
 const first=futureModels[0][1],other=futureModels.length>1?futureModels[1][1]:null;
 const disagree=!!other&&Math.abs(other.departure-first.departure)>300;
 const agreement=!!other&&!disagree;
 const label=disagree?"MODELS DISAGREE":
   agreement?"MODELS AGREE":"ONE MODEL ONLY";
 const lead=disagree?"TIMES CONFLICT · RECHECK":
   first.departure<=now+30?"DUE NOW":"LEAVE AT "+clock(first.departure);
 const age=lastStockChangeAge(row,now);
 const context=age===null?" No item state recorded.": 
   " Last quantity change "+elapsed(age)+" ago; unchanged values remain valid between successful polls.";
 const why=(disagree?"Two models suggest different times. Recheck before acting.":
   agreement?"Models agree within five minutes. Still unvalidated.":
   "Only one model offers this departure. Recheck before acting.")+context;
 return {first,lead,label,why,disagree,agreement,
   eta:first.arrival,when:first.departure,
   alternate:disagree?other.departure:null};
}
function chooseRecheck(key){
 const select=el("recheckItem");
 if(latest&&latest.items.some(r=>r.item_key===key))select.value=key;
 select.scrollIntoView({behavior:"smooth",block:"center"});
 recheckNow();
}
function render(){
 if(!latest)return;
 const now=currentTime(),rows=latest.items.slice(),ok=fresh();
 const windows=rows.filter(r=>signal(r,now)==="WATCH").sort((a,b)=>priority(a,now)-priority(b,now));
 const recent=rows.filter(r=>signal(r,now)==="RECHECK")
   .sort((a,b)=>a.flight_seconds-b.flight_seconds);
 el("upcomingCount").textContent=windows.length+" / 24";
 el("recheckCount").textContent=recent.length+" to check";
 el("noneCount").textContent=rows.length-windows.length-recent.length;
 el("health").className="health"+(ok?"":" bad");
 el("health").textContent=(ok?"Feed current":"Feed stale · no departure guidance")+
   " · updated "+clock(latest.issued_epoch)+
   " ("+elapsed(now-latest.issued_epoch)+" ago) · next issue expected in "+
   elapsed(Math.max(0,latest.issued_epoch+300-now));
 let chosen=windows[0];
 selectedHero=chosen?chosen.item_key:null;
 const head=chosen?diagnose(chosen,now):null;
 el("heroItem").textContent=chosen?chosen.country_name+" · "+chosen.item:
   (recent.length?"Nothing upcoming; recheck a recent NOW signal":"No upcoming departure");
 el("heroState").textContent=head?head.label:"NO VERIFIED DEPARTURE";
 el("heroState").className="pill "+(head&&!head.disagree?"watch":"review");
 el("heroTime").textContent=head?head.lead:"WAIT / RECHECK";
 el("heroArrival").textContent=head?"Estimated landing: "+clock(head.eta):
   "New forecast required before choosing a flight.";
 el("heroFlight").textContent=chosen?"Flight "+elapsed(chosen.flight_seconds)+
   " · stock last observed "+(chosen.source_quantity??"unknown")+
   " · target ≥30 on arrival":"Current verified accuracy: not available.";
 el("heroWhy").textContent=head?head.why+
   (head.alternate?" Alternative model: "+clock(head.alternate)+".":""):
   "A prediction is not an instruction to depart without a fresh check.";
 el("heroCheck").disabled=!chosen;
 el("upcoming").replaceChildren();
 for(const row of windows.slice(0,12)){
   const d=diagnose(row,now);if(!d)continue;
   const card=node("article","","card"),top=node("div","","row");
   add(top,"strong",row.country_name+" · "+row.item);
   add(top,"span",d.label,"pill "+(d.disagree?"review":"watch"));card.append(top);
   add(card,"div",d.lead,d.disagree?"time muted":"time");
   add(card,"div",d.when>now?"Leave in "+elapsed(d.when-now):"Departure due","muted");
   add(card,"p","Estimated arrival "+clock(d.eta)+" · "+elapsed(row.flight_seconds)+" flight","meta");
   add(card,"p",d.why+(d.alternate?" Other model: "+clock(d.alternate):""),"meta");
   const button=add(card,"button","Check now","tiny");
   button.addEventListener("click",()=>chooseRecheck(row.item_key));
   el("upcoming").append(card);
 }
 if(!windows.length){add(el("upcoming"),"p",
   ok?"No future windows this issue. Recheck a recent NOW signal below.":"Wait for a fresh V160 issue.","muted");}
 el("recheckCards").replaceChildren();
 for(const row of recent.slice(0,8)){
   const card=node("article","","card");
   add(card,"strong",row.country_name+" · "+row.item);
   add(card,"div","RECHECK NOW — prior signal expired","time");
   add(card,"div","Flight "+elapsed(row.flight_seconds)+
     " · stock last observed "+(row.source_quantity??"unknown"),"meta");
   const button=add(card,"button","Check now","tiny");
   button.addEventListener("click",()=>chooseRecheck(row.item_key));
   el("recheckCards").append(card);
 }
 if(!recent.length)add(el("recheckCards"),"p",
  "No recently issued NOW signals.","muted");
 const table=el("rows");table.replaceChildren();
 for(const row of rows.sort((a,b)=>signal(a,now).localeCompare(signal(b,now))||
                             a.item_key.localeCompare(b.item_key))){
  const tr=table.insertRow();
  const values=[row.country_name+" · "+row.item,row.source_quantity??"unknown"];
  for(const val of values)tr.append(node("td",String(val)));
  for(const kind of ["independent","paired_complete"]){
    const m=row.models[kind],value=m.signal==="FUTURE_WATCH"?
      "WATCH "+clock(m.departure):m.signal==="DUE_NOW"?"DUE NOW":
      m.signal==="RECENT_ISSUED_NOW_RECHECK"?"Recent NOW · expired":
      m.signal==="DEPARTURE_PASSED"?"Passed":
      m.signal==="NO_MODEL_CANDIDATE"?"Abstained":"Stale";
    const td=node("td",value);
    add(td,"div",(m.status||"Unknown").replaceAll("_"," ").toLowerCase(),"sub");
    tr.append(td);
  }
  tr.append(node("td",signal(row,now)==="WATCH"?"Recheck near departure":
                      signal(row,now)==="RECHECK"?"Recalculate now":"Wait for next issue"));
  table.append(tr);
 }
 if(lastCheck && !lastCheckExpired && currentTime()-lastCheck.issued_epoch>30){
   lastCheckExpired=true;
   renderCheck(lastCheck);
 }
}
function populate(items){
 const select=el("recheckItem"),preserve=select.value;
 select.replaceChildren();select.append(node("option","Choose item"));
 select.firstChild.value="";
 for(const r of items.slice().sort((a,b)=>
   (a.country_name+a.item).localeCompare(b.country_name+b.item))){
  const option=node("option",r.country_name+" · "+r.item);
  option.value=r.item_key;select.append(option);
 }
 if(items.some(r=>r.item_key===preserve))select.value=preserve;
}
function renderCheck(data){
 const output=el("recheckOutput");
 output.replaceChildren();
 if(!data)return;
 const age=currentTime()-data.issued_epoch;
 const names=["independent","paired_complete"];
 const m=names.map(key=>data.models[key]);
 const valid=m.filter(v=>Number.isInteger(v.departure_epoch)&&v.departure_epoch>=currentTime()-30)
   .sort((a,b)=>a.departure_epoch-b.departure_epoch);
 const mismatch=valid.length===2&&Math.abs(valid[0].departure_epoch-valid[1].departure_epoch)>300;
 const two=valid.length===2&&!mismatch;
 const timeline=data.restock_timeline;
 const hasRestockOutlook=timeline&&Array.isArray(timeline.restock_events)
   &&timeline.restock_events.length>0;
 const exp=age>30 || !valid.length;
 const lastChangeAge=Number.isInteger(data.source_last_epoch)?
    data.issued_epoch-data.source_last_epoch:null;
 let state,caption;
 if(lastChangeAge===null || lastChangeAge<0){
   state="STOCK HISTORY UNKNOWN";
   caption="No usable stock state timestamp for this item; treat any modeled departure as unconfirmed.";
 }else if(age>30){state="RECHECK — RESULT EXPIRED";caption="Calculation is over 30 seconds old. Run another check.";}
 else if(!valid.length && hasRestockOutlook){
   state="RESTOCKS FORECAST · ARRIVAL NOT VALIDATED";
   caption="The event model predicts replenishments, but neither V151 model supports a >=30-stock arrival. View all events below; do not treat the event estimate as a safe-to-fly signal.";
 }
 else if(!valid.length){state="NO SUPPORTED DEPARTURE";caption="Neither model currently supports an eligible flight.";}
 else if(mismatch){state="MODELS DISAGREE";caption="Both models produced different times; no single recommended departure.";}
 else if(valid[0].departure_epoch<=currentTime()+30){
    state=two?"LEAVE NOW · BOTH MODELS":"LEAVE NOW · ONE MODEL";
    caption="Provisional only. Confirm current stock context before spending energy or traveling.";}
 else {state="LEAVE AT "+clock(valid[0].departure_epoch);
    caption=two?"Both models agree within five minutes; reconfirm near departure.":
      "One model supports this window; reconfirm near departure.";}
 add(output,"div",data.item_key+" · checked "+clock(data.issued_epoch),"eyebrow");
 add(output,"div",state,"big");
 add(output,"p",caption,"muted");
 if(valid.length){
   add(output,"div","Projected arrival "+clock(valid[0].arrival_epoch)+
     " · flight "+elapsed(data.flight_seconds)+
     " · target ≥30 on arrival","meta");
   if(mismatch)add(output,"p","Other model departure "+clock(valid[1].departure_epoch),"meta");
 }else if(exp)add(output,"p","Wait for a fresher result.","meta");
 add(output,"div","Last known quantity "+(data.source_last_quantity??"unknown")+
   " · last quantity change "+(lastChangeAge===null?"unknown":elapsed(lastChangeAge))+
   " ago · global collector heartbeat "+elapsed(data.source_heartbeat_age_seconds)+
   " old when checked. Unchanged quantities are not stale merely because time passed.","meta");
 const section=add(output,"div","","");
 section.className="sep";
 add(output,"h3","Predicted restocks — next 8 hours");
 add(output,"p","Each restock is shown, even if your flight cannot reach it. Times are estimates, NOT 90%-verified.","muted small");
 if(timeline&&Array.isArray(timeline.restock_events)&&timeline.restock_events.length){
   const events=timeline.restock_events;
   for(const e of events){
     const card=add(output,"div","","card");
     const when=Number.isInteger(e.predicted_restock_epoch)?
       clock(e.predicted_restock_epoch):"unknown";
     add(card,"strong","Restock "+e.event_index+" · around "+when);
     const earliest=Number.isInteger(e.expected_departure_epoch)?
       e.expected_departure_epoch:null;
     const latest=Number.isInteger(e.expected_latest_departure_epoch)?
       e.expected_latest_departure_epoch:null;
     const tooLate=earliest!==null && currentTime()>latest;
     const summary=earliest===null?
       "UNREACHABLE for this flight — keep watching later restocks":
       tooLate?"DEPARTURE WINDOW PASSED — recheck now":
       "LEAVE "+(earliest<=currentTime()+30?"NOW":"AT "+clock(earliest))+
         " · latest estimated departure "+clock(latest);
     add(card,"div",summary,"meta");
     add(card,"div","Restock timing estimate "+clock(e.restock_early_epoch)+" to "+
       clock(e.restock_late_epoch)+" · expected stock until "+
       clock(e.predicted_stock_below_30_epoch),"sub");
   }

 }else{
   add(output,"p",timeline&&timeline.status?
     "No restock timeline this issue: "+timeline.status.replaceAll("_"," ").toLowerCase()+
      ". This does not mean there will be no restocks.":
     "Restock timeline not available; existing departure forecast remains provisional.","muted");
 }
 const technical=add(output,"details","","");
 add(technical,"summary","Show research scenario support (not accuracy)");
 for(const key of names){
  const v=data.models[key],score=Number.isFinite(v.scenario_stock_fraction)?
    Math.round(v.scenario_stock_fraction*100)+"% simulated support":"no qualifying forecast";
  add(technical,"p",key.replaceAll("_"," ")+": "+score+" · "+
    (v.status||"unknown").replaceAll("_"," ").toLowerCase(),"small");
 }
}
async function recheckNow(){
 const key=el("recheckItem").value;if(!key){el("recheckOutput").textContent="Choose an item first.";return;}
 const button=el("checkNow");button.disabled=true;lastCheck=null;lastCheckExpired=false;
 el("recheckOutput").textContent="Calculating a fresh departure time…";
 try{
  const response=await fetch("/api/recheck",{method:"POST",cache:"no-store",
    headers:{"Content-Type":"application/json","X-Torn-Fren-Action":"user-recheck"},
    body:JSON.stringify({item_key:key})});
  const result=await response.json();
  if(!response.ok||result.status!=="CURRENT_ITEM_RECHECK_RESEARCH_ONLY")
   throw Error(result.note||"Could not calculate a current flight.");
  lastCheck=result;renderCheck(result);
 }catch(err){
  el("recheckOutput").replaceChildren();
  add(el("recheckOutput"),"strong","NO NEW DEPARTURE");
  add(el("recheckOutput"),"p",err.message+" · Wait for a fresh issue or retry shortly.","muted");
 }finally{button.disabled=false;}
}
el("heroCheck").addEventListener("click",()=>{if(selectedHero)chooseRecheck(selectedHero);});
el("checkNow").addEventListener("click",recheckNow);
el("refresh").addEventListener("click",refresh);
async function refresh(){
 try{
  const response=await fetch("/api/live",{cache:"no-store"});
  const data=await response.json();
  if(!Array.isArray(data.items)||data.items.length!==24)throw Error("No complete 24-item issue.");
  latest=data;populate(data.items);render();
 }catch(err){
  latest=null;selectedHero=null;
  el("health").className="health bad";
  el("health").textContent="Forecast feed unavailable: "+err.message;
  el("upcoming").replaceChildren();el("recheckCards").replaceChildren();
  el("heroItem").textContent="WAIT FOR FRESH DATA";
  el("heroTime").textContent="NO DEPARTURE";
  el("heroCheck").disabled=true;
 }
}
setInterval(()=>{if(latest)render();},1000);
setInterval(refresh,30000);
refresh();
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
                if run.returncode or len(run.stdout)>125000:
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
