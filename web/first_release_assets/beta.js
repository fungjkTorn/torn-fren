(() => {
  'use strict';
  const countries={arg:'Argentina',can:'Canada',cay:'Cayman Islands',haw:'Hawaii',jap:'Japan',mex:'Mexico',swi:'Switzerland',uae:'UAE',uni:'United Kingdom'};
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clock=t=>Number.isInteger(t)?new Date(t*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'—';
  const duration=s=>`${Math.floor(Math.max(0,s)/3600)}h ${Math.floor(Math.max(0,s)%3600/60)}m`;
  let data=null;
  function card(r){
    const [country,name]=r.item_key.split(':'),d=r.decision||{},m=r.live||{},now=Math.floor(Date.now()/1000);
    const dep=d.estimated_departure_epoch,deadline=d.estimated_departure_deadline_epoch;
    const fresh=data&&now<=data.valid_until_epoch&&Number.isInteger(dep)&&now<=deadline;
    const title=fresh?(dep<=now?'Leave now':`Leave ${clock(dep)}`):(d.status==='STALE_DATA'?'Awaiting fresh data':'Forecast unavailable');
    const arrival=fresh?Math.max(now,dep)+d.player_flight_seconds:null;
    const trips=m.trips||[],dots=trips.map(t=>`<span class="beta-dot ${esc(t.outcome.status)}" title="${esc(t.outcome.status)} · arrival ${clock(t.arrival_epoch)}"></span>`).join('');
    const n=m.known||0,p=m.success_fraction;
    const rate=typeof p==='number'?`${(p*100).toFixed(0)}% · ${m.successes}/${n} known`:(n?`${m.successes}/${n} matched known · rate pending`:'Collecting live outcomes');
    const unmatched=m.unmatched_forecast_rows||{};
    const outstanding=Object.entries(unmatched).map(([k,v])=>`${v} ${k.toLowerCase()}`).join(', ');
    const target=d.selected_restock_event_index===0?'Current stock window':`Restock P${d.selected_restock_event_index||'—'}`;
    return `<article class="beta-card" data-item="${esc(r.item_key)}"><div class="beta-country">${esc(countries[country]||country)}</div><h2>${esc(name)}</h2><div class="beta-leave">${esc(title)}</div><div>${fresh?`Arrival ${clock(arrival)} · leave before ${clock(deadline)}`:esc((d.status||r.status||'Waiting for forecast').replaceAll('_',' ').toLowerCase())}</div><div class="beta-meta">${esc(target)} · ${duration(d.player_flight_seconds||0)} flight · ${esc((d.timing_model_generation||'').toUpperCase())} ${esc(d.timing_model_config||'')}</div><div class="beta-result"><strong>${esc(rate)}</strong><div class="beta-dots">${dots||'<span class="beta-meta">No completed opportunities yet</span>'}</div><div class="beta-meta">Last ${trips.length}/10 observed opportunities · ${m.unknown||0} unknown · ${m.pending||0} pending</div>${outstanding?`<div class="beta-meta">Unmatched forecast rows: ${esc(outstanding)}. Repeated rows are not trips.</div>`:''}<details><summary>Recent forecast trips</summary>${trips.map(t=>`<div class="beta-trip">${esc(t.outcome.status)} · leave ${clock(t.departure_epoch)} → arrival ${clock(t.arrival_epoch)} · stock ${t.outcome.pre_quantity??'?'}/${t.outcome.post_quantity??'?'} · opening ${clock(t.actual_opening.epoch)}</div>`).join('')||'<div class="beta-trip">The recorder is collecting observations.</div>'}</details></div><p><a href="/?country=${encodeURIComponent(country)}&item=${encodeURIComponent(name)}">Open stock graph ↗</a></p></article>`;
  }
  function render(){
    if(!data)return;
    const open=new Set([...document.querySelectorAll('.beta-card details[open]')].map(e=>e.closest('[data-item]')?.dataset.item));
    const grid=document.getElementById('beta-grid');
    if(grid)grid.innerHTML=data.rows.map(card).join('');
    const health=document.getElementById('beta-health');
    if(health)health.textContent=`${Date.now()/1000>data.valid_until_epoch?'Data needs refresh':'Live beta'} · updated ${clock(data.published_epoch)} · stock >30 · ${data.model_sha.slice(0,8)} · green success / red failure / amber unknown / blue pending`;
    if(!grid){
      let key;try{key=country+':'+item;}catch(e){const q=new URLSearchParams(location.search);key=q.get('country')+':'+q.get('item');}
      const row=data.rows.find(r=>r.item_key===key);
      let panel=document.getElementById('first-release-panel');
      if(!panel){panel=document.createElement('section');panel.id='first-release-panel';panel.className='beta-inline';document.body.prepend(panel);}
      panel.innerHTML=row?card(row):'<div class="beta-card">This item is under review. Live departure advice is enabled for the first ten items. <a href="/experimental">View live beta</a></div>';
    }
    document.querySelectorAll('.beta-card details').forEach(e=>{if(open.has(e.closest('[data-item]')?.dataset.item))e.open=true;});
  }
  async function refresh(){try{const r=await fetch('/api/first-release',{cache:'no-store'});if(!r.ok)throw Error();data=await r.json();render();}catch(e){const el=document.getElementById('beta-health');if(el)el.textContent='Forecast feed unavailable. Departure advice is paused until a fresh snapshot arrives.';if(data){data.valid_until_epoch=0;render();}}}
  // The older chart must use server-selected departure geometry. It must not
  // roll to a later restock or recalculate a different "safe" flight window.
  if(typeof window.departureWindowForPrediction==='function'){
    const old=window.departureWindowForPrediction;
    window.departureWindowForPrediction=function(p,f){if(p?.first_release){if(Date.now()/1000>p.valid_until_epoch)return null;return{earliestArrival:p.departure_epoch+p.flight_seconds,latestArrival:p.departure_deadline_epoch+p.flight_seconds,earliestLeave:p.departure_epoch,latestLeave:p.departure_deadline_epoch};}return old(p,f);};
  }
  if(typeof window.rollPredictionTargetClientSide==='function'){
    const old=window.rollPredictionTargetClientSide;
    window.rollPredictionTargetClientSide=function(){try{if(currentAnalysis?.first_release)return false;}catch(e){}return old();};
  }
  if(typeof window.updateInsights==='function'){
    const old=window.updateInsights;
    window.updateInsights=function(a){old(a);if(a?.first_release){const m=a.first_release.live||{};const el=document.getElementById('predictionLifetimeSuccess');if(el)el.textContent='New live beta';const note=document.getElementById('predictionNote');if(note)note.textContent='Earliest reachable opportunity · stock >30 at calculated landing · historical rates excluded.';render();}};
  }
  if(location.pathname==='/travel-decisions'){const title=document.getElementById('beta-title');if(title)title.textContent='Your next departure.';}
  refresh();setInterval(refresh,30000);setInterval(render,1000);
})();
