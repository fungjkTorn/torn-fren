(() => {
  'use strict';
  const UI_VERSION='travel-windows-v1';
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
  let data=null,selectedKey=null,dialog=null,returnFocus=null,graphKey=null,pageIndex=0,feedError=false;
  const pageSize=20;
  const filters={search:'',country:'',type:'',status:'',sort:'departure'};
  function state(r){
    const d=r.decision||{},dep=d.estimated_departure_epoch,end=d.estimated_departure_deadline_epoch;
    if(!data||now()>data.valid_until_epoch||!Number.isInteger(dep)||!Number.isInteger(end)||now()>end)return 'unavailable';
    return dep<=now()?'ready':'scheduled';
  }
  function leave(r){return state(r)==='ready'?'Leave now':state(r)==='scheduled'?clock(r.decision.estimated_departure_epoch):(!data||now()>data.valid_until_epoch||['STALE_DATA','STALE_COUNTRY_DATA'].includes(r.decision?.status)?'Stock data delayed':'Awaiting forecast');}
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
      byId('beta-health').textContent=now()>data.valid_until_epoch?'Stock updates delayed · advice paused':feedError?'Refresh delayed · showing the last valid forecast':`Updated ${clock(data.published_epoch)} · refreshes automatically`;
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
  function travelWindows(r){
    if(!r||state(r)==='unavailable')return null;
    const d=r.decision,start=Math.max(now(),d.estimated_departure_epoch),end=d.estimated_departure_deadline_epoch,flight=d.player_flight_seconds;
    if(!Number.isInteger(flight)||start>end)return null;
    return {departureStart:start,departureEnd:end,arrivalStart:start+flight,arrivalEnd:end+flight};
  }
  function windowText(w,kind){
    if(!w)return '—';
    if(kind==='departure')return `${w.departureStart<=now()?'Now':clock(w.departureStart)} – ${clock(w.departureEnd)}`;
    return `${clock(w.arrivalStart)} – ${clock(w.arrivalEnd)}`;
  }
  function graphChart(){return window.Chart?.getChart('stockChart');}
  function graphRow(){return data?.rows.find(r=>r.item_key===currentGraphKey());}
  function paintTravelGraph(){graphChart()?.draw();}
  let focusTravel=true,scrollPaintTimer=null,lastPaintFresh=null;
  function focusTravelWindows(allowZoom=true){
    const w=travelWindows(graphRow()),c=graphChart(),scroller=byId('chart-scroll');
    if(!w||!c||!scroller)return;
    focusTravel=true;
    const span=w.arrivalEnd-now()+1800;
    if(allowZoom){
      const active=document.querySelector('#timeframes button.active');
      if(active){
        const choices=[...document.querySelectorAll('#timeframes button[data-minutes]')].sort((a,b)=>Number(a.dataset.minutes)-Number(b.dataset.minutes));
        const choice=choices.find(b=>Number(b.dataset.minutes)*60>=span*1.12)||choices.at(-1);
        if(choice!==active){choice.click();requestAnimationFrame(()=>requestAnimationFrame(()=>focusTravelWindows(false)));return;}
      }
    }
    // Chart.js can defer its responsive resize until after a timeframe click.
    // Resolve the new canvas geometry before choosing a horizontal viewport.
    c.resize();c.update('none');
    const x=c.scales.x,left=x.getPixelForValue((now()-900)*1000),right=x.getPixelForValue((w.arrivalEnd+900)*1000),width=scroller.clientWidth;
    const desired=right-left<width-24?left-Math.max(0,width-(right-left))*.15:left;
    scroller.scrollLeft=Math.max(0,Math.min(scroller.scrollWidth-width,desired));
    paintTravelGraph();
  }
  function installTravelOverlay(){
    if(!window.Chart)return;
    // The legacy P1 marker treats calculation time as a new drop for current
    // stock. Suppress it only for the approved beta; retain other chart behavior.
    try{
      const legacy=window.Chart.registry.getPlugin('predictionOverlay'),old=legacy.beforeDatasetsDraw;
      legacy.beforeDatasetsDraw=function(c,...args){if(c.$prediction?.first_release)return;return old.call(this,c,...args);};
    }catch(e){}
    window.Chart.register({id:'firstReleaseTravelWindows',beforeDatasetsDraw(c){
      c.$travelWindows=null;
      const w=travelWindows(graphRow());if(!w)return;
      const {ctx,chartArea:a,scales:{x}}=c;if(!a||!x)return;
      c.$travelWindows={...w,estimated:true};
      const scroll=byId('chart-scroll'),visibleLeft=Math.max(a.left,(scroll?.scrollLeft||0)+8),visibleRight=Math.min(a.right,(scroll?.scrollLeft||0)+(scroll?.clientWidth||a.right)-8);
      ctx.save();ctx.beginPath();ctx.rect(a.left,a.top,a.right-a.left,a.bottom-a.top);ctx.clip();
      const bands=[{kind:'departure',start:w.departureStart,end:w.departureEnd,color:'#edc578',wash:'rgba(237,197,120,.065)',lane:'rgba(114,85,29,.60)',top:a.top+8,label:'Leave'},
        {kind:'arrival',start:w.arrivalStart,end:w.arrivalEnd,color:'#82dbc2',wash:'rgba(130,219,194,.065)',lane:'rgba(35,99,83,.60)',top:a.top+42,label:'Arrive'}];
      for(const band of bands){
        const left=x.getPixelForValue(band.start*1000),right=x.getPixelForValue(band.end*1000);
        if(right<a.left||left>a.right)continue;
        const l=Math.max(left,a.left),r=Math.min(right,a.right);
        ctx.fillStyle=band.wash;ctx.fillRect(l,a.top,Math.max(1,r-l),a.bottom-a.top);
        ctx.fillStyle=band.lane;ctx.fillRect(l,band.top,Math.max(1,r-l),26);
        ctx.strokeStyle=band.color;ctx.lineWidth=1;ctx.setLineDash([5,4]);
        for(const boundary of [left,right]){ctx.beginPath();ctx.moveTo(boundary,band.top);ctx.lineTo(boundary,a.bottom);ctx.stroke();}
        ctx.setLineDash([]);ctx.font='600 11px system-ui,sans-serif';ctx.textBaseline='middle';
        const label=`${band.label} · ${windowText(w,band.kind)} · estimated`,labelWidth=ctx.measureText(label).width;
        // Keep the complete range readable even when a short window is only
        // a narrow strip at the edge of a 24/72-hour history view.
        const labelX=visibleLeft+7;
        if(right>=visibleLeft&&left<=visibleRight){
          const labelRight=visibleRight-3;ctx.save();ctx.beginPath();ctx.rect(labelX-3,band.top,labelRight-labelX+3,26);ctx.clip();
          ctx.fillStyle='rgba(13,22,32,.92)';ctx.fillRect(labelX-3,band.top+2,Math.min(labelWidth+8,labelRight-labelX+3),22);
          ctx.fillStyle=band.color;ctx.fillText(label,labelX,band.top+13);ctx.restore();
        }
      }
      const nowX=x.getPixelForValue(now()*1000);
      if(nowX>=a.left&&nowX<=a.right){ctx.strokeStyle='#c6d0df';ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(nowX,a.top+78);ctx.lineTo(nowX,a.bottom);ctx.stroke();ctx.setLineDash([]);ctx.font='11px system-ui,sans-serif';ctx.fillStyle='#dce6f3';ctx.fillText('Now',nowX+5,a.bottom-12);}
      ctx.restore();
    }});
    if(typeof window.jumpToLatest==='function'){
      const old=window.jumpToLatest;
      window.jumpToLatest=function(){if(focusTravel&&travelWindows(graphRow())&&graphChart())focusTravelWindows(false);else old();};
    }
  }
  function setupGraph(){
    document.body.classList.add('beta-graph');
    const page=document.querySelector('main.page');if(!page)return;
    const nav=document.createElement('nav');nav.className='beta-graph-nav';nav.setAttribute('aria-label','Main navigation');nav.innerHTML='<a class="beta-brand" href="/experimental">TORN<span>FREN</span></a><a href="/experimental">Travel planner</a><span class="beta-label">LIVE BETA</span>';page.prepend(nav);
    const overview=document.createElement('section');overview.className='beta-graph-overview';overview.setAttribute('aria-label','Observed history and travel plan');page.insertBefore(overview,page.querySelector('.controls'));
    const history=byId('history-section');
    if(history){const details=document.createElement('details');details.className='beta-history';details.open=innerWidth>=900;details.innerHTML='<summary>Observed history</summary>';details.append(history);overview.append(details);}
    const panel=document.createElement('section');panel.id='first-release-panel';panel.className='beta-inline';panel.setAttribute('aria-label','Travel forecast');panel.textContent='Loading travel forecast…';overview.append(panel);
    const controls=page.querySelector('.right-controls'),show=document.createElement('button');show.id='beta-show-windows';show.type='button';show.textContent='Show travel windows';show.addEventListener('click',()=>focusTravelWindows(true));controls?.prepend(show);
    byId('latestButton')?.addEventListener('click',()=>{focusTravel=false;});
    for(const id of ['countrySelect','itemSelect'])byId(id)?.addEventListener('change',()=>{focusTravel=true;});
    byId('chart-scroll')?.addEventListener('scroll',()=>{clearTimeout(scrollPaintTimer);scrollPaintTimer=setTimeout(paintTravelGraph,100);},{passive:true});
    const legend=page.querySelector('.legend');
    if(legend){legend.querySelector('.prediction')?.remove();legend.insertAdjacentHTML('beforeend','<span class="beta-legend-departure">Estimated departure window</span><span class="beta-legend-arrival">Estimated arrival window</span>');}
    installTravelOverlay();
    window.addEventListener('resize',()=>{if(focusTravel)requestAnimationFrame(()=>focusTravelWindows(false));});
    requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
  }
  function renderGraph(){
    const panel=byId('first-release-panel');if(!panel||!data)return;
    const nextKey=currentGraphKey(),changed=nextKey!==graphKey;graphKey=nextKey;
    const r=graphRow();
    if(!r){panel.innerHTML='<div class="beta-inline-plan"><div><strong>Model under review</strong><span class="beta-sub">Observed stock history is available. Departure advice is not enabled for this item.</span></div><a href="/experimental">View travel planner ↗</a></div>';byId('beta-show-windows').disabled=true;paintTravelGraph();return;}
    const d=r.decision||{},w=travelWindows(r);byId('beta-show-windows').disabled=!w;
    panel.innerHTML=`<div class="beta-plan-heading"><div><span class="beta-sub">${d.selected_restock_event_index===0?'Current stock · already available':'Predicted buying window'} · ${duration(d.player_flight_seconds||0)} flight</span><strong data-leave-key="${esc(r.item_key)}" class="beta-leave">${esc(leave(r))}</strong><span class="beta-sub">${w?`Arrival if you leave then: <span data-arrival-key="${esc(r.item_key)}">${esc(clock(arrival(r)))}</span>`:esc(reason(r))}</span></div><button class="beta-text-button" type="button" data-details="${esc(r.item_key)}">Forecast details</button></div><div class="beta-travel-ranges"><div><span>Estimated departure window</span><strong data-window-key="${esc(r.item_key)}" data-window-kind="departure">${esc(windowText(w,'departure'))}</strong></div><div><span>Estimated arrival window</span><strong data-window-key="${esc(r.item_key)}" data-window-kind="arrival">${esc(windowText(w,'arrival'))}</strong></div></div><div class="beta-plan-results"><span class="beta-sub">Last 10 opportunities</span><span class="beta-rate">${esc(rate(r))}</span>${dots(r)}<a href="/experimental">All items ↗</a></div><p class="beta-window-note">${w?'These ranges shift by the flight duration. The estimated stock deadline bounds arrival; this is not a guaranteed stock window.':'Advice resumes when fresh data supports a buying window.'}</p>`;
    requestAnimationFrame(()=>{paintTravelGraph();if(changed&&focusTravel)focusTravelWindows(false);});
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
    if(graph){
      const r=graphRow(),w=travelWindows(r);
      for(const el of document.querySelectorAll('[data-window-key]'))if(el.dataset.windowKey===r?.item_key)el.textContent=windowText(w,el.dataset.windowKind);
      if(byId('beta-show-windows'))byId('beta-show-windows').disabled=!w;
      if(Boolean(w)!==lastPaintFresh||now()%15===0){paintTravelGraph();lastPaintFresh=Boolean(w);}
    }
    summary();
  }
  async function refresh(){
    try{
      const response=await fetch('/api/first-release',{cache:'no-store'});if(!response.ok)throw Error('feed unavailable');
      const next=await response.json();if(!Array.isArray(next.rows))throw Error('invalid feed');data=next;feedError=false;
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
      feedError=true;
      if(data){if(graph)renderGraph();else renderList();tick();}
      if(!graph&&!data)byId('beta-health').textContent='Forecast feed unavailable · departure advice paused';
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
