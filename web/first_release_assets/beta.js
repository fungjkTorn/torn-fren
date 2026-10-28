(() => {
  'use strict';
  const UI_VERSION='compact-planner-v1';
  document.documentElement.dataset.betaUi=UI_VERSION;
  const countries={arg:'Argentina',can:'Canada',cay:'Cayman Islands',haw:'Hawaii',jap:'Japan',mex:'Mexico',swi:'Switzerland',uae:'UAE',uni:'United Kingdom',chi:'China',sou:'South Africa'};
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const now=()=>Math.floor(Date.now()/1000);
  const clock=t=>{
    if(!Number.isInteger(t))return '—';
    const date=new Date(t*1000),today=new Date();
    return date.toLocaleString([],{...(date.toDateString()!==today.toDateString()?{month:'short',day:'numeric'}:{}),hour:'2-digit',minute:'2-digit'});
  };
  const duration=s=>{const m=Math.floor(Math.max(0,s)/60);return m>=60?`${Math.floor(m/60)}h ${m%60}m`:`${m}m`;};
  const byId=id=>document.getElementById(id);
  const graph=!byId('beta-rows');
  let data=null,selectedKey=null,dialog=null,returnFocus=null,graphKey=null,pageIndex=0;
  const pageSize=20;
  const filters={search:'',country:'',type:'',status:'',sort:'departure'};
  function state(r){
    const d=r.decision||{},dep=d.estimated_departure_epoch,end=d.estimated_departure_deadline_epoch;
    if(!data||now()>data.valid_until_epoch||!Number.isInteger(dep)||!Number.isInteger(end)||now()>end)return 'unavailable';
    return dep<=now()?'ready':'scheduled';
  }
  function leave(r){return state(r)==='ready'?'Leave now':state(r)==='scheduled'?clock(r.decision.estimated_departure_epoch):'Awaiting forecast';}
  function arrival(r){return state(r)==='unavailable'?null:Math.max(now(),r.decision.estimated_departure_epoch)+r.decision.player_flight_seconds;}
  function rate(r){const m=r.live||{};return typeof m.success_fraction==='number'?`${Math.round(m.success_fraction*100)}% · ${m.successes}/${m.known}`:m.known?`${m.successes}/${m.known} matched · rate pending`:'Collecting results';}
  function dots(r,full=false){
    const trips=(r.live?.trips||[]).slice(0,10);
    const symbols={SUCCESS:'Success',FAILURE:'Miss',UNKNOWN:'Unknown',PENDING:'Pending'};
    return `<span class="beta-dots" aria-label="${esc(trips.map(t=>symbols[t.outcome.status]||'Unknown').join(', ')||'No observed opportunities yet')}">${trips.map(t=>`<i class="beta-dot ${Object.hasOwn(symbols,t.outcome.status)?t.outcome.status:'UNKNOWN'}" title="${esc(symbols[t.outcome.status]||'Unknown')} · arrival ${esc(clock(t.arrival_epoch))}"></i>`).join('')}${Array.from({length:10-trips.length},()=>'<i class="beta-dot empty" aria-hidden="true"></i>').join('')}</span>${full?`<span class="beta-sub">${trips.length}/10 opportunities · ${r.live?.unknown||0} unknown · ${r.live?.pending||0} pending</span>`:''}`;
  }
  function reason(r){
    const d=r.decision||{};
    if(!data||now()>data.valid_until_epoch||d.status==='STALE_DATA')return 'Waiting for a fresh stock update.';
    if(d.status==='STALE_COUNTRY_DATA')return 'The latest country stock report is stale.';
    const code=d.reason||r.forecast?.status||d.status;
    if(code==='CURRENT_PHASE_UNKNOWN')return 'The start of the current stock window is unknown.';
    if(code==='CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS')return 'The current stock phase is longer than the available history supports.';
    if(code==='NO_REACHABLE_PREDICTED_WINDOW')return 'No reachable buying window is currently available.';
    return 'A supported departure estimate is not available yet.';
  }
  function graphUrl(r){const [c,...name]=r.item_key.split(':');return `/?country=${encodeURIComponent(c)}&item=${encodeURIComponent(name.join(':'))}`;}
  function rowHtml(r){
    const [c,name]=r.item_key.split(':'),d=r.decision||{},s=state(r),q=r.forecast?.observed_current_quantity;
    return `<tr data-item="${esc(r.item_key)}"><td><span class="beta-item-name">${esc(name)}</span><span class="beta-sub">${esc(countries[c]||c)}</span></td><td data-label="Current stock">${Number.isFinite(q)?q.toLocaleString():'—'}</td><td data-label="Departure"><span data-leave-key="${esc(r.item_key)}" class="beta-leave ${s==='unavailable'?'beta-waiting':''}">${esc(leave(r))}</span><span class="beta-sub">${duration(d.player_flight_seconds||r.forecast?.flight_seconds||0)} flight</span></td><td data-label="Arrival"><span data-arrival-key="${esc(r.item_key)}">${esc(clock(arrival(r)))}</span></td><td data-label="Leave before"><span data-deadline-key="${esc(r.item_key)}">${s==='unavailable'?'—':esc(clock(d.estimated_departure_deadline_epoch))}</span></td><td data-label="Last 10 opportunities"><span class="beta-rate">${esc(rate(r))}</span>${dots(r)}</td><td><div class="beta-actions"><button type="button" class="beta-text-button" data-details="${esc(r.item_key)}" aria-label="Details for ${esc(name)}">Details</button><a href="${graphUrl(r)}" aria-label="Stock graph for ${esc(name)}">Graph ↗</a></div></td></tr>`;
  }
  function filteredRows(){
    return data.rows.filter(r=>{
      const [c,name]=r.item_key.split(':'),type=/xanax/i.test(name)?'xanax':/plushie/i.test(name)?'plushie':'flower';
      return (!filters.search||`${name} ${countries[c]||c}`.toLowerCase().includes(filters.search.toLowerCase()))&&(!filters.country||c===filters.country)&&(!filters.type||type===filters.type)&&(!filters.status||state(r)===filters.status);
    }).sort((a,b)=>{
      if(filters.sort==='country')return (countries[a.item_key.split(':')[0]]||a.item_key).localeCompare(countries[b.item_key.split(':')[0]]||b.item_key)||a.item_key.localeCompare(b.item_key);
      if(filters.sort==='item')return a.item_key.split(':')[1].localeCompare(b.item_key.split(':')[1]);
      const depart=r=>state(r)==='unavailable'?Infinity:Math.max(now(),r.decision.estimated_departure_epoch);
      return (depart(a)-depart(b))||a.item_key.split(':')[1].localeCompare(b.item_key.split(':')[1]);
    });
  }
  function renderList(){
    if(!data)return;
    const rows=filteredRows(),pages=Math.max(1,Math.ceil(rows.length/pageSize));
    pageIndex=Math.min(pageIndex,pages-1);
    const start=pageIndex*pageSize,visible=rows.slice(start,start+pageSize);
    byId('beta-rows').innerHTML=visible.map(rowHtml).join('');
    byId('beta-count').textContent=rows.length>pageSize?`${start+1}–${start+visible.length} of ${rows.length} matching items`:`${rows.length} of ${data.rows.length} items`;
    byId('beta-pagination').hidden=pages<=1;
    byId('beta-page-number').textContent=`Page ${pageIndex+1} of ${pages}`;
    byId('beta-prev').disabled=pageIndex===0;byId('beta-next').disabled=pageIndex===pages-1;
    byId('beta-empty').hidden=rows.length>0;
    const select=byId('beta-country'),codes=[...new Set(data.rows.map(r=>r.item_key.split(':')[0]))].sort((a,b)=>(countries[a]||a).localeCompare(countries[b]||b));
    if(select.dataset.codes!==codes.join(',')){
      select.innerHTML='<option value="">All countries</option>'+codes.map(c=>`<option value="${esc(c)}">${esc(countries[c]||c)}</option>`).join('');select.value=filters.country;select.dataset.codes=codes.join(',');
    }
  }
  function summary(){
    if(!data)return;
    if(!graph){
      for(const [id,value] of [['total',data.rows.length],['ready',data.rows.filter(r=>state(r)==='ready').length],['scheduled',data.rows.filter(r=>state(r)==='scheduled').length],['unavailable',data.rows.filter(r=>state(r)==='unavailable').length]])byId('beta-'+id).textContent=value;
      byId('beta-health').textContent=now()>data.valid_until_epoch?'Stock feed needs refresh · advice paused':`Updated ${clock(data.published_epoch)} · refreshes automatically`;
    }
  }
  function ensureDialog(){
    if(dialog)return;
    dialog=document.createElement('dialog');dialog.className='beta-dialog';dialog.setAttribute('aria-labelledby','beta-detail-title');document.body.append(dialog);
    dialog.addEventListener('close',()=>{selectedKey=null;returnFocus?.focus();});
    dialog.addEventListener('click',e=>{if(e.target.closest('[data-close]'))dialog.close();else if(e.target===dialog){const b=dialog.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)dialog.close();}});
  }
  function detailHtml(r){
    const [c,name]=r.item_key.split(':'),d=r.decision||{},m=r.live||{},trips=m.trips||[],unmatched=m.unmatched_forecast_rows||{},q=r.forecast?.observed_current_quantity;
    return `<div class="beta-dialog-head"><div><span class="beta-sub">${esc(countries[c]||c)} · ${duration(d.player_flight_seconds||r.forecast?.flight_seconds||0)} flight</span><h2 id="beta-detail-title">${esc(name)}</h2></div><button type="button" class="beta-dialog-close" data-close aria-label="Close item details">Close</button></div><div class="beta-dialog-body"><div class="beta-plan-grid"><div><span>Departure</span><strong class="beta-leave" data-leave-key="${esc(r.item_key)}">${esc(leave(r))}</strong></div><div><span>Arrival</span><strong data-arrival-key="${esc(r.item_key)}">${esc(clock(arrival(r)))}</strong></div><div><span>Leave before</span><strong data-deadline-key="${esc(r.item_key)}">${state(r)==='unavailable'?'—':esc(clock(d.estimated_departure_deadline_epoch))}</strong></div></div><p>${state(r)==='unavailable'?esc(reason(r)):`${d.selected_restock_event_index===0?'Current stock window':'Earliest reachable restock'} · current stock ${Number.isFinite(q)?q.toLocaleString():'unknown'}. Departure and arrival times are estimates.`}</p><h3>Last 10 forecast opportunities</h3><strong>${esc(rate(r))}</strong>${dots(r,true)}<p>Success means stock &gt;30 at calculated landing. Repeated forecasts are counted once per observed opportunity. Actual trips are not required.</p>${m.percentage_withheld_for_unmatched_misses?'<p>A rate is withheld while failed or unknown forecasts remain unmatched to an observed opportunity.</p>':''}<div>${trips.map(t=>`<div class="beta-trip"><strong>${esc(t.outcome.status)} · arrival ${esc(clock(t.arrival_epoch))}</strong><span class="beta-sub">Departure ${esc(clock(t.departure_epoch))} · stock before / after arrival ${esc(t.outcome.pre_quantity??'?')} / ${esc(t.outcome.post_quantity??'?')}</span></div>`).join('')||'<p>No matched opportunities have completed yet. Forecasts are being recorded.</p>'}</div><details><summary>Forecast diagnostics</summary><dl><dt>Timing model</dt><dd>${esc((d.timing_model_generation||'').toUpperCase())} ${esc(d.timing_model_config||'')}</dd><dt>Forecast issued</dt><dd>${esc(clock(r.forecast?.asof_epoch||data.asof_epoch))}</dd><dt>Model revision</dt><dd>${esc(data.model_sha||'')}</dd><dt>Provider clock</dt><dd>${esc(r.country_clock?.clock_status||'Not reported')}</dd><dt>Unmatched forecast rows</dt><dd>${esc(Object.entries(unmatched).map(([k,v])=>`${v} ${k.toLowerCase()}`).join(', ')||'None')}</dd></dl><p>These are forecast revisions, not extra trips. Unmatched outcomes remain visible here and cannot improve the displayed rate.</p></details><a class="beta-detail-link" href="${graphUrl(r)}">Open stock graph ↗</a></div>`;
  }
  function openDetails(key,trigger){
    const r=data?.rows.find(r=>r.item_key===key);if(!r)return;
    ensureDialog();selectedKey=key;returnFocus=trigger;dialog.innerHTML=detailHtml(r);dialog.showModal();
  }
  function currentGraphKey(){try{return country+':'+item;}catch(e){const q=new URLSearchParams(location.search);return (q.get('country')||'uni')+':'+(q.get('item')||'');}}
  function setupGraph(){
    document.body.classList.add('beta-graph');
    const page=document.querySelector('main.page');if(!page)return;
    const nav=document.createElement('nav');nav.className='beta-graph-nav';nav.setAttribute('aria-label','Main navigation');nav.innerHTML='<a class="beta-brand" href="/experimental">TORN<span>FREN</span></a><a href="/experimental">Travel planner</a><span class="beta-label">LIVE BETA</span>';page.prepend(nav);
    const panel=document.createElement('section');panel.id='first-release-panel';panel.className='beta-inline';panel.setAttribute('aria-label','Travel forecast');panel.textContent='Loading travel forecast…';page.insertBefore(panel,page.querySelector('.controls'));
    const history=byId('history-section');
    if(history){const details=document.createElement('details');details.className='beta-history';details.innerHTML='<summary>Stock and price statistics</summary>';details.append(history);page.append(details);}
    // The chart already exposes its own redraw/resize hook. Recalculate after
    // removing the old fixed-height dashboard panels from the page flow.
    requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
  }
  function renderGraph(){
    const panel=byId('first-release-panel');if(!panel||!data)return;
    graphKey=currentGraphKey();const r=data.rows.find(r=>r.item_key===graphKey);
    if(!r){panel.innerHTML='<div class="beta-inline-plan"><div><strong>Model under review</strong><span class="beta-sub">Stock history is available; departure advice is not enabled for this item.</span></div><a href="/experimental">View travel planner ↗</a></div>';return;}
    const d=r.decision||{};
    panel.innerHTML=`<div class="beta-inline-plan"><div><span class="beta-sub">${d.selected_restock_event_index===0?'Current stock window':'Next buying opportunity'}</span><strong data-leave-key="${esc(r.item_key)}" class="beta-leave">${esc(leave(r))}</strong></div><div><span class="beta-sub">Arrival · ${duration(d.player_flight_seconds||0)} flight</span><strong data-arrival-key="${esc(r.item_key)}">${esc(clock(arrival(r)))}</strong></div><div><span class="beta-sub">Leave before</span><strong data-deadline-key="${esc(r.item_key)}">${state(r)==='unavailable'?'—':esc(clock(d.estimated_departure_deadline_epoch))}</strong></div><div><span class="beta-sub">Last 10 opportunities</span><span class="beta-rate">${esc(rate(r))}</span>${dots(r)}</div><div class="beta-actions"><button class="beta-text-button" type="button" data-details="${esc(r.item_key)}">Forecast details</button><a href="/experimental">All items ↗</a></div></div>${state(r)==='unavailable'?`<p class="beta-health-inline">${esc(reason(r))}</p>`:''}`;
  }
  function tick(){
    if(!data)return;
    const states=data.rows.map(r=>state(r)).join(',');
    if(!graph&&byId('beta-rows').dataset.states!==states){renderList();byId('beta-rows').dataset.states=states;}
    if(graph&&currentGraphKey()!==graphKey)renderGraph();
    for(const r of data.rows){
      const fresh=state(r)!=='unavailable';
      for(const e of document.querySelectorAll('[data-leave-key]'))if(e.dataset.leaveKey===r.item_key){e.textContent=leave(r);e.classList.toggle('beta-waiting',!fresh);}
      for(const e of document.querySelectorAll('[data-arrival-key]'))if(e.dataset.arrivalKey===r.item_key)e.textContent=clock(arrival(r));
      for(const e of document.querySelectorAll('[data-deadline-key]'))if(e.dataset.deadlineKey===r.item_key)e.textContent=fresh?clock(r.decision.estimated_departure_deadline_epoch):'—';
    }
    summary();
  }
  async function refresh(){
    try{
      const response=await fetch('/api/first-release',{cache:'no-store'});if(!response.ok)throw Error('feed unavailable');
      const next=await response.json();if(!Array.isArray(next.rows))throw Error('invalid feed');data=next;
      if(graph)renderGraph();else renderList();
      if(dialog?.open&&selectedKey){
        const row=data.rows.find(r=>r.item_key===selectedKey);
        if(row){
          const expanded=dialog.querySelector('details')?.open;
          const focused=document.activeElement?.closest('[data-close]')?'[data-close]':document.activeElement?.tagName==='SUMMARY'?'summary':null;
          dialog.innerHTML=detailHtml(row);
          if(expanded)dialog.querySelector('details').open=true;
          if(focused)dialog.querySelector(focused)?.focus();
        }else dialog.close();
      }
      tick();
    }catch(e){
      if(data){data.valid_until_epoch=0;if(graph)renderGraph();else renderList();tick();}
      if(!graph)byId('beta-health').textContent='Forecast feed unavailable · departure advice paused';
      else if(!data)byId('first-release-panel').textContent='Forecast feed unavailable. Stock history remains available.';
    }
  }
  document.addEventListener('click',e=>{const button=e.target.closest('[data-details]');if(button)openDetails(button.dataset.details,button);});
  if(graph){
    setupGraph();
    // Retain server-selected scheduling geometry; do not roll to later events.
    if(typeof window.departureWindowForPrediction==='function'){
      const old=window.departureWindowForPrediction;
      window.departureWindowForPrediction=function(p,f){if(p?.first_release){if(now()>p.valid_until_epoch)return null;return{earliestArrival:p.departure_epoch+p.flight_seconds,latestArrival:p.departure_deadline_epoch+p.flight_seconds,earliestLeave:p.departure_epoch,latestLeave:p.departure_deadline_epoch};}return old(p,f);};
    }
    if(typeof window.rollPredictionTargetClientSide==='function'){
      const old=window.rollPredictionTargetClientSide;
      window.rollPredictionTargetClientSide=function(){try{if(currentAnalysis?.first_release)return false;}catch(e){}return old();};
    }
    if(typeof window.updateInsights==='function'){
      const old=window.updateInsights;
      window.updateInsights=function(a){old(a);if(data)renderGraph();};
    }
  }else{
    for(const [field,id] of [['search','beta-search'],['country','beta-country'],['type','beta-type'],['status','beta-status'],['sort','beta-sort']])byId(id).addEventListener(field==='search'?'input':'change',e=>{filters[field]=e.target.value;pageIndex=0;renderList();});
    for(const [id,step] of [['beta-prev',-1],['beta-next',1]])byId(id).addEventListener('click',()=>{pageIndex+=step;renderList();document.querySelector('.beta-list').scrollIntoView({block:'start'});});
    if(location.pathname==='/travel-decisions')document.querySelector('nav a[href="/experimental"]').setAttribute('aria-current','page');
  }
  refresh();setInterval(refresh,30000);setInterval(tick,1000);
})();
