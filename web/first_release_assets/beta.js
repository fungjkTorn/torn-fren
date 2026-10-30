(() => {
  'use strict';
  const UI_VERSION='planner-simulated-trips-v5';
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
  const filters={search:'',country:'',type:'',status:'',sort:'departure'};
  let catalogRows=new Map(),priceStatus='loading',pageSize=10;
  const money=v=>Number.isFinite(v)?new Intl.NumberFormat([],{style:'currency',currency:'USD',maximumFractionDigits:0}).format(v):'—';
  function pricesFor(r){
    const found=catalogRows.get(r.item_key);if(found)return found;
    if(graph){try{if(currentGraphKey()===r.item_key&&currentAnalysis?.profitability)return currentAnalysis.profitability;}catch(e){}}
    return {};
  }
  function economicsHtml(r){
    const p=pricesFor(r);
    return `<h3>Prices and profit</h3><dl class="beta-money-grid"><div><dt>Foreign buy price</dt><dd>${esc(money(p.foreign_price))}</dd></div><div><dt>Torn market value</dt><dd>${esc(money(p.market_price))}</dd></div><div><dt>Net profit / item</dt><dd>${esc(money(p.net_profit_per_item))}</dd></div><div><dt>Profit / slot / hour</dt><dd>${esc(money(p.profit_per_slot_per_hour))}</dd></div><div><dt>ROI</dt><dd>${Number.isFinite(p.roi_percent)?esc(p.roi_percent.toFixed(1))+'%':'—'}</dd></div><div><dt>Round trip</dt><dd>${Number.isFinite(p.round_trip_minutes)?esc(duration(p.round_trip_minutes*60)):'—'}</dd></div></dl><p>Net profit includes the 5% Item Market fee. Hourly profit uses one slot and a PI + pilot round trip. Market value is a reference, not a guaranteed sale price.${p.market_price_stale?' Market quote is stale.':''}</p>`;
  }
  async function refreshPrices(){
    try{
      const response=await fetch('/api/catalog',{cache:'no-store'});if(!response.ok)throw Error();
      const catalog=await response.json(),next=new Map();
      for(const country of catalog.countries||[])for(const item of country.items||[])next.set(country.country+':'+item.item_name,item);
      catalogRows=next;priceStatus=catalog.catalog_cache?.status==='overdue'?'delayed':'available';
    }catch(e){priceStatus='delayed';}
    if(data)renderList();
    if(dialog?.open&&selectedKey){const row=data?.rows.find(r=>r.item_key===selectedKey);if(row&&dialog.querySelector('.beta-economics'))dialog.querySelector('.beta-economics').innerHTML=economicsHtml(row);}
  }
  let fittingPlanner=false;
  function fitPlannerPage(){
    if(graph||fittingPlanner||!data)return;
    fittingPlanner=true;
    const rows=[...byId('beta-rows').rows];
    const rowHeight=Math.max(1,...rows.map(r=>r.getBoundingClientRect().height));
    const top=byId('beta-rows').getBoundingClientRect().top+scrollY;
    const capacity=innerWidth<=760?5:Math.max(5,Math.min(20,Math.floor((innerHeight-top-84)/rowHeight)));
    if(capacity!==pageSize){pageSize=capacity;renderList();}
    fittingPlanner=false;
  }
  let fittingGraph=false;
  function fitGraphHeight(){
    if(!graph||fittingGraph||innerWidth<1100)return;
    const stage=byId('chart-stage'),scroll=byId('chart-scroll');if(!stage||!scroll)return;
    const page=document.querySelector('main.page');
    const footer=[...page.children].filter(e=>['legend'].includes(e.className)||['status','hint'].includes(e.id)).reduce((h,e)=>{const s=getComputedStyle(e);return h+e.getBoundingClientRect().height+parseFloat(s.marginTop||0)+parseFloat(s.marginBottom||0);},0);
    const available=Math.floor(innerHeight-(scroll.getBoundingClientRect().top+scrollY)-footer-18);
    // Keep a legible chart on short screens; allow normal page scrolling there.
    const height=Math.max(300,available);
    if(Math.abs(stage.getBoundingClientRect().height-height)>2){fittingGraph=true;stage.style.setProperty('height',height+'px','important');graphChart()?.resize();fittingGraph=false;}
  }
  const historySummaries=new Map();
  function applyHistorySummary(key){
    if(key!==currentGraphKey())return;
    const entry=historySummaries.get(key),stats=entry?.value;
    const note=byId('beta-history-note');if(!stats)return;
    if(stats.status!=='AVAILABLE'){if(note)note.textContent=stats.reason||'Historical sample is unavailable.';return;}
    const set=(id,value)=>{if(byId(id))byId(id).textContent=value??'—';};
    set('lastRestock',clock(stats.last_restock_timestamp));set('lastDepletion',clock(stats.last_depletion_timestamp));
    set('lastPeak',Number.isFinite(stats.last_peak_quantity)?stats.last_peak_quantity.toLocaleString():'—');
    for(const [id,field] of [['avgLifetime','avg_stocked_seconds'],['medianLifetime','median_stocked_seconds'],['avgZeroWait','avg_unstocked_seconds'],['medianZeroWait','median_unstocked_seconds']])set(id,Number.isFinite(stats[field])?duration(stats[field]):'—');
    set('validCycles',stats.completed_stock_windows);set('excludedCycles',stats.uncertain_boundaries);
    if(note)note.textContent=`Observed sample: ${Math.max(1,Math.round((stats.sample_end_epoch-stats.sample_start_epoch)/86400))} days · ${stats.sample_rows.toLocaleString()} changes · as of ${clock(stats.source_heartbeat_epoch)} · profit after 5% fee`;
    fitGraphHeight();
  }
  async function refreshHistorySummary(){
    const key=currentGraphKey(),cached=historySummaries.get(key);
    if(cached?.value)applyHistorySummary(key);
    if(cached&&(cached.loading||now()-cached.at<300))return;
    historySummaries.set(key,{...cached,loading:true,at:now()});
    const [country,item]=key.split(':');
    try{
      const response=await fetch('/api/first-release/history-summary?country='+encodeURIComponent(country)+'&item='+encodeURIComponent(item),{cache:'no-store'});
      if(!response.ok)throw Error();
      historySummaries.set(key,{value:await response.json(),at:now(),loading:false});
    }catch(e){historySummaries.set(key,{value:cached?.value||{status:'UNAVAILABLE',reason:'Historical statistics are temporarily unavailable.'},at:now(),loading:false});}
    applyHistorySummary(key);
  }
  function state(r){
    const d=r.decision||{},dep=d.estimated_departure_epoch,end=d.estimated_departure_deadline_epoch;
    if(!data||now()>data.valid_until_epoch||!Number.isInteger(dep)||!Number.isInteger(end)||now()>end)return 'unavailable';
    return dep<=now()?'ready':'scheduled';
  }
  function leave(r){return state(r)==='ready'?'Leave now':state(r)==='scheduled'?clock(r.decision.estimated_departure_epoch):(!data||now()>data.valid_until_epoch||['STALE_DATA','STALE_COUNTRY_DATA'].includes(r.decision?.status)?'Stock data delayed':'Awaiting forecast');}
  function arrival(r){return state(r)==='unavailable'?null:Math.max(now(),r.decision.estimated_departure_epoch)+r.decision.player_flight_seconds;}
  function rate(r){
    const m=r.live||{};
    if(m.target_identity_audit?.duplicate_target_groups)return 'Results under review · duplicate targets';
    if(typeof m.success_fraction==='number')return `${Math.round(m.success_fraction*100)}% · ${m.successes}/${m.known} known${m.unknown?' · '+m.unknown+' unknown':''}${m.pending?' · '+m.pending+' pending':''}`;
    if(m.known)return `${m.successes}/${m.known} known · rate withheld`;
    if(m.unknown)return `${m.unknown} unknown · no known results`;
    if(m.pending)return `${m.pending} awaiting arrival results`;
    if(m.unmatched_revision_total||Object.keys(m.unmatched_forecast_rows||{}).length)return 'Recorded · awaiting window match';
    if(m.active_recommendation)return 'Recommended departure pending';
    return 'No frozen simulated trips yet';
  }
  function dots(r,full=false){
    const trips=(r.live?.trips||[]).slice(0,10);
    const symbols={SUCCESS:'Success',FAILURE:'Miss',UNKNOWN:'Unknown',PENDING:'Pending'};
    return `<span class="beta-dots" aria-label="${esc(trips.map(t=>symbols[t.outcome.status]||'Unknown').join(', ')||'No frozen simulated trips yet')}">${trips.map(t=>`<i class="beta-dot ${Object.hasOwn(symbols,t.outcome.status)?t.outcome.status:'UNKNOWN'}" title="${esc(symbols[t.outcome.status]||'Unknown')} · arrival ${esc(clock(t.arrival_epoch))}"></i>`).join('')}${Array.from({length:10-trips.length},()=>'<i class="beta-dot empty" aria-hidden="true"></i>').join('')}</span>${full?`<span class="beta-sub">${trips.length}/10 simulated trips · ${r.live?.unknown||0} unknown · ${r.live?.pending||0} pending</span>`:''}`;
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
    const [c,name]=r.item_key.split(':'),d=r.decision||{},s=state(r),q=r.forecast?.observed_current_quantity,p=pricesFor(r);
    return `<tr data-item="${esc(r.item_key)}"><td><span class="beta-item-name">${esc(name)}</span><span class="beta-sub">${esc(countries[c]||c)} · ${Number.isFinite(q)?q.toLocaleString():'—'} stock</span></td><td data-label="Buy / market value" class="beta-prices"><strong>${esc(money(p.foreign_price))} <small>buy</small></strong><span class="beta-sub">${esc(money(p.market_price))} market${p.market_price_stale?' · stale':''}</span></td><td data-label="Profit" class="beta-profit"><strong>${esc(money(p.net_profit_per_item))} <small>/ item</small></strong><span class="beta-sub">${esc(money(p.profit_per_slot_per_hour))}/slot/hr${Number.isFinite(p.roi_percent)?' · '+esc(p.roi_percent.toFixed(1))+'% ROI':''}</span></td><td data-label="Departure"><span data-leave-key="${esc(r.item_key)}" class="beta-leave ${s==='unavailable'?'beta-waiting':''}">${esc(leave(r))}</span><span class="beta-sub">${duration(d.player_flight_seconds||r.forecast?.flight_seconds||0)} flight · by <span data-deadline-key="${esc(r.item_key)}">${s==='unavailable'?'—':esc(clock(d.estimated_departure_deadline_epoch))}</span></span></td><td data-label="Arrival"><span data-arrival-key="${esc(r.item_key)}">${esc(clock(arrival(r)))}</span></td><td data-label="Last 10 simulated trips"><span class="beta-rate">${esc(rate(r))}</span>${dots(r)}</td><td><div class="beta-actions"><button type="button" class="beta-text-button" data-details="${esc(r.item_key)}" aria-label="Details for ${esc(name)}">Details</button><a href="${graphUrl(r)}" aria-label="Stock graph for ${esc(name)}">Graph ↗</a></div></td></tr>`;
  }
  function filteredRows(){
    return data.rows.filter(r=>{
      const [c,name]=r.item_key.split(':'),type=/xanax/i.test(name)?'xanax':/plushie/i.test(name)?'plushie':'flower';
      return (!filters.search||`${name} ${countries[c]||c}`.toLowerCase().includes(filters.search.toLowerCase()))&&(!filters.country||c===filters.country)&&(!filters.type||type===filters.type)&&(!filters.status||state(r)===filters.status);
    }).sort((a,b)=>{
      if(filters.sort==='country')return (countries[a.item_key.split(':')[0]]||a.item_key).localeCompare(countries[b.item_key.split(':')[0]]||b.item_key)||a.item_key.localeCompare(b.item_key);
      if(filters.sort==='profit'||filters.sort==='hourly'){const field=filters.sort==='profit'?'net_profit_per_item':'profit_per_slot_per_hour';return (pricesFor(b)[field]??-Infinity)-(pricesFor(a)[field]??-Infinity)||a.item_key.localeCompare(b.item_key);}
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
    byId('beta-prices-status').textContent=priceStatus==='loading'?'Loading prices…':priceStatus==='delayed'?'Price refresh delayed · estimates shown where available':'Net profit after 5% fee · PI + pilot · market reference values';
    requestAnimationFrame(fitPlannerPage);
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
    return `<div class="beta-dialog-head"><div><span class="beta-sub">${esc(countries[c]||c)} · ${duration(d.player_flight_seconds||r.forecast?.flight_seconds||0)} flight</span><h2 id="beta-detail-title">${esc(name)}</h2></div><button type="button" class="beta-dialog-close" data-close aria-label="Close item details">Close</button></div><div class="beta-dialog-body"><div class="beta-plan-grid"><div><span>Departure</span><strong class="beta-leave" data-leave-key="${esc(r.item_key)}">${esc(leave(r))}</strong></div><div><span>Arrival</span><strong data-arrival-key="${esc(r.item_key)}">${esc(clock(arrival(r)))}</strong></div><div><span>Leave before</span><strong data-deadline-key="${esc(r.item_key)}">${state(r)==='unavailable'?'—':esc(clock(d.estimated_departure_deadline_epoch))}</strong></div></div><p>${state(r)==='unavailable'?esc(reason(r)):`${d.selected_restock_event_index===0?'Current stock window':'Earliest reachable restock'} · current stock ${Number.isFinite(q)?q.toLocaleString():'unknown'}. Departure and arrival times are estimates.`}</p><section class="beta-economics">${economicsHtml(r)}</section><h3>Last 10 simulated trips</h3><strong>${esc(rate(r))}</strong>${dots(r,true)}<p>Success means stock &gt;30 at calculated landing. Each test freezes at its recommended departure time. Revisions before departure are recorded; later forecasts cannot move its arrival. Restock identification is tracked separately and does not block an observable arrival result. Actual trips are not required.</p>${m.percentage_withheld_for_unmatched_misses?'<p>Rate withheld: recorded failed or unknown forecast revisions still need an observed-window match. This is an evidence-matching issue, not a wait for more arrivals.</p>':''}<div>${trips.map(t=>`<div class="beta-trip"><strong>${esc(t.outcome.status)} · arrival ${esc(clock(t.arrival_epoch))}</strong><span class="beta-sub">Departure ${esc(clock(t.departure_epoch))} · ${esc(t.outcome.reason||'')} · stock before / after arrival ${esc(t.outcome.pre_quantity??'?')} / ${esc(t.outcome.post_quantity??'?')}</span></div>`).join('')||'<p>No simulated trips have frozen yet. Scheduled recommendations remain visible above.</p>'}</div><details><summary>Forecast diagnostics</summary><dl><dt>Timing model</dt><dd>${esc((d.timing_model_generation||'').toUpperCase())} ${esc(d.timing_model_config||'')}</dd><dt>Forecast issued</dt><dd>${esc(clock(r.forecast?.asof_epoch||data.asof_epoch))}</dd><dt>Model revision</dt><dd>${esc(data.model_sha||'')}</dd><dt>Provider clock</dt><dd>${esc(r.country_clock?.clock_status||'Not reported')}</dd><dt>Qualified restocks since tracking began</dt><dd>${esc(m.observed_restocks_since_start??'Unknown')}</dd><dt>Recorded forecast revisions</dt><dd>${esc(m.recorded_forecast_revisions??Object.values(m.raw_forecast_row_outcomes||{}).reduce((a,b)=>a+b,0))}</dd><dt>Evidence policy</dt><dd>${esc(m.evidence_policy||'Legacy matcher')}</dd><dt>Duplicate target groups</dt><dd>${esc(m.target_identity_audit?.duplicate_target_groups??'Not audited')}</dd><dt>Frozen simulated trips</dt><dd>${esc(m.simulated_trips_total??'Unknown')}</dd><dt>Restock signature</dt><dd>${esc(m.restock_profile?.status==='LEARNED'?m.restock_profile.normal_min+'–'+m.restock_profile.normal_max+' units; '+(m.restock_profile.reset_base?'reset to '+m.restock_profile.reset_base:'no confirmed reset pattern'):'Insufficient pre-tracking history')}</dd><dt>Recommendation changes</dt><dd>${esc(Object.entries(m.revision_counts||{}).map(([k,v])=>v+' '+k.toLowerCase().replaceAll('_',' ')).join(', ')||'None')}</dd>${m.evidence_policy?'':`<dt>Legacy unmatched forecast revisions</dt><dd>${esc(Object.entries(unmatched).map(([k,v])=>`${v} ${k.toLowerCase()}`).join(', ')||'None')}</dd>`}</dl><p>Forecast revisions are not extra trips. The percentage uses known results among the last ten frozen trips; unknown and pending results are listed separately.</p></details><a class="beta-detail-link" href="${graphUrl(r)}">Open stock graph ↗</a></div>`;
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
    window.Chart.register({id:'firstReleaseTravelWindows',resize(){
      if(focusTravel)requestAnimationFrame(()=>requestAnimationFrame(()=>focusTravelWindows(false)));
    },beforeDatasetsDraw(c){
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
    if(history){const details=document.createElement('details');details.className='beta-history';details.open=innerWidth>=900;details.innerHTML='<summary>Observed history</summary>';details.append(history);const note=document.createElement('p');note.id='beta-history-note';note.className='beta-history-note';note.textContent='Loading observed statistics…';details.append(note);overview.append(details);
      for(const [id,label] of [['lastRestock','Last >30 opening'],['lastDepletion','Last depletion (=0)'],['lastPeak','Peak (sample)'],['avgLifetime','Avg stocked (>30)'],['medianLifetime','Median stocked (>30)'],['avgZeroWait','Avg ≤30 → >30'],['medianZeroWait','Median ≤30 → >30'],['validCycles','Completed stock windows'],['excludedCycles','Uncertain boundaries']]){const value=byId(id),text=value?.closest('.metric')?.querySelector('.metric-label');if(text)text.textContent=label;}
    }
    const panel=document.createElement('section');panel.id='first-release-panel';panel.className='beta-inline';panel.setAttribute('aria-label','Travel forecast');panel.textContent='Loading travel forecast…';overview.append(panel);
    const controls=page.querySelector('.right-controls'),show=document.createElement('button');show.id='beta-show-windows';show.type='button';show.textContent='Travel windows';show.addEventListener('click',()=>focusTravelWindows(true));controls?.prepend(show);
    byId('latestButton')?.addEventListener('click',()=>{focusTravel=false;});
    for(const id of ['countrySelect','itemSelect'])byId(id)?.addEventListener('change',()=>{focusTravel=true;});
    byId('chart-scroll')?.addEventListener('scroll',()=>{clearTimeout(scrollPaintTimer);scrollPaintTimer=setTimeout(paintTravelGraph,100);},{passive:true});
    for(const event of ['pointerdown','wheel'])byId('chart-scroll')?.addEventListener(event,()=>{focusTravel=false;},{passive:true});
    const legend=page.querySelector('.legend');
    if(legend){legend.querySelector('.prediction')?.remove();legend.insertAdjacentHTML('beforeend','<span class="beta-legend-departure">Estimated departure window</span><span class="beta-legend-arrival">Estimated arrival window</span>');}
    const watcher=new ResizeObserver(()=>requestAnimationFrame(fitGraphHeight));watcher.observe(overview);if(page.querySelector('.controls'))watcher.observe(page.querySelector('.controls'));
    installTravelOverlay();
    window.addEventListener('resize',()=>{fitGraphHeight();if(focusTravel)requestAnimationFrame(()=>focusTravelWindows(false));});
    requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
  }
  function renderGraph(){
    const panel=byId('first-release-panel');if(!panel||!data)return;
    const nextKey=currentGraphKey(),changed=nextKey!==graphKey;graphKey=nextKey;refreshHistorySummary();
    const r=graphRow();
    if(!r){panel.innerHTML='<div class="beta-inline-plan"><div><strong>Model under review</strong><span class="beta-sub">Observed stock history is available. Departure advice is not enabled for this item.</span></div><a href="/experimental">View travel planner ↗</a></div>';byId('beta-show-windows').disabled=true;paintTravelGraph();return;}
    const d=r.decision||{},w=travelWindows(r);byId('beta-show-windows').disabled=!w;
    panel.innerHTML=`<div class="beta-plan-heading"><div><span class="beta-sub">${d.selected_restock_event_index===0?'Current stock · already available':'Predicted buying window'} · ${duration(d.player_flight_seconds||0)} flight</span><strong data-leave-key="${esc(r.item_key)}" class="beta-leave">${esc(leave(r))}</strong><span class="beta-sub">${w?`Arrival if you leave then: <span data-arrival-key="${esc(r.item_key)}">${esc(clock(arrival(r)))}</span>`:esc(reason(r))}</span></div><button class="beta-text-button" type="button" data-details="${esc(r.item_key)}">Forecast details</button></div><div class="beta-travel-ranges"><div><span>Estimated departure window</span><strong data-window-key="${esc(r.item_key)}" data-window-kind="departure">${esc(windowText(w,'departure'))}</strong></div><div><span>Estimated arrival window</span><strong data-window-key="${esc(r.item_key)}" data-window-kind="arrival">${esc(windowText(w,'arrival'))}</strong></div></div><div class="beta-plan-results"><span class="beta-sub">Last 10 simulated trips</span><span class="beta-rate">${esc(rate(r))}</span>${dots(r)}<a href="/experimental">All items ↗</a></div><p class="beta-window-note">${w?'These ranges shift by the flight duration. The estimated stock deadline bounds arrival; this is not a guaranteed stock window.':'Advice resumes when fresh data supports a buying window.'}</p>`;
    requestAnimationFrame(()=>{fitGraphHeight();paintTravelGraph();if(focusTravel)requestAnimationFrame(()=>focusTravelWindows(false));});
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
      window.updateInsights=function(a){old(a);for(const metric of document.querySelectorAll('#history-section .metric')){const sub=metric.querySelector('.metric-subvalue');if(sub)metric.title=sub.textContent;}applyHistorySummary(currentGraphKey());if(data)renderGraph();};
    }
  }else{
    for(const [field,id] of [['search','beta-search'],['country','beta-country'],['type','beta-type'],['status','beta-status'],['sort','beta-sort']])byId(id).addEventListener(field==='search'?'input':'change',e=>{filters[field]=e.target.value;pageIndex=0;renderList();});
    for(const [id,step] of [['beta-prev',-1],['beta-next',1]])byId(id).addEventListener('click',()=>{pageIndex+=step;renderList();document.querySelector('.beta-list').scrollIntoView({block:'start'});});
    if(location.pathname==='/travel-decisions')document.querySelector('nav a[href="/experimental"]').setAttribute('aria-current','page');
  }
  if(!graph){refreshPrices();setInterval(refreshPrices,120000);window.addEventListener('resize',()=>requestAnimationFrame(fitPlannerPage));}
  refresh();setInterval(refresh,30000);setInterval(tick,1000);
})();
