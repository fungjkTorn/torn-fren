(()=>{'use strict';
const $=id=>document.getElementById(id),core=TornHotList,esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const countries={arg:'Argentina',can:'Canada',cay:'Cayman Islands',haw:'Hawaii',jap:'Japan',mex:'Mexico',swi:'Switzerland',uae:'UAE',uni:'United Kingdom',chi:'China',sou:'South Africa'};
const money=x=>Number.isFinite(x)?'$'+Math.round(x).toLocaleString():'—',time=x=>Number.isFinite(x)?new Date(x*1000).toLocaleString([],{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}):'—';
let board=[],catalog=new Map(),roster=[],rosterError=false,view='hot',category='',page=0,refreshError=false,priceError=false;
function rows(){
 const map=new Map(roster.map(key=>[key,{item_key:key,decision:{}}]));
 for(const [key] of catalog)if(!map.has(key))map.set(key,{item_key:key,decision:{}});
 for(const r of board)if(r&&typeof r.item_key==='string')map.set(r.item_key,r);
 return [...map.values()];
}
function stockQuantity(r){
 const now=Math.floor(Date.now()/1000),ts=r.source_heartbeat_epoch,q=r.forecast?.observed_current_quantity;
 return Number.isInteger(ts)&&ts<=now&&now-ts<=180&&Number.isFinite(q)&&q>=0?q:null;
}
function adviceLabel(r,p){
 if(p)return 'Predicted arrival opportunity · not guaranteed';
 if(!Number.isInteger(r.valid_until_epoch))return 'No public departure forecast';
 if(r.valid_until_epoch<Math.floor(Date.now()/1000))return 'Forecast expired';
 return 'No executable departure currently published';
}
function info(r){const at=Math.floor(Date.now()/1000),item=catalog.get(r.item_key)||{},p=core.plan(r,Number($('flight').value),at),seconds=core.flights[r.item_key.split(':')[0]]?.[Number($('flight').value)]*60;
const capacity=Number($('capacity').value),marketValue=item.market_price_stale||priceError?null:item.market_price,economics=core.economics(item,marketValue,capacity,p?.seconds??seconds,p?Math.max(0,p.departure-at):0);
return {item,p,economics};}
function render(){let list=rows().filter(r=>{const name=r.item_key.split(':')[1],c=r.item_key.split(':')[0],i=info(r);return (!category||core.category(name)===category)&&(!view||view==='all'||core.hotEligible(r.item_key,i.item,i.p,i.economics))&&(!$('available').checked||stockQuantity(r)>30)&&(`${name} ${countries[c]||c}`.toLowerCase().includes($('search').value.toLowerCase()));});
const metric=r=>{const i=info(r);return $('sort').value==='departure'?(i.p?-i.p.departure:-Infinity):$('sort').value==='profit'?i.economics?.profit??-Infinity:$('sort').value==='hourly'?i.economics?.hourly??-Infinity:i.p?i.economics?.cycleHourly??-Infinity:-Infinity;};
list.sort((a,b)=>{const av=metric(a),bv=metric(b);return av===bv?a.item_key.localeCompare(b.item_key):av>bv?-1:1;});const pages=Math.max(1,Math.ceil(list.length/10));page=Math.min(page,pages-1);
$('rows').innerHTML=list.slice(page*10,page*10+10).map(r=>{const [c,name]=r.item_key.split(':'),{item,p,economics:e}=info(r),q=stockQuantity(r),id=Number(item.item_id??item.id);return `<tr><td data-label=""><a class="hot-row-link" href="/?country=${encodeURIComponent(c)}&item=${encodeURIComponent(name)}">${Number.isInteger(id)&&id>0?`<img class="hot-thumb" loading="lazy" src="https://www.torn.com/images/items/${id}/large.png" alt="" data-fallback>`:'<span class="hot-thumb hot-fallback" aria-hidden="true">◈</span>'}<strong>${esc(name)}</strong></a><span class="beta-sub">${esc(countries[c]||c)}</span></td><td data-label="Availability"><strong>${q!==null?q.toLocaleString()+' stock':'Stock unverified'}</strong><span class="beta-sub">${esc(adviceLabel(r,p))}</span></td><td data-label="Profit / inventory"><strong class="hot-value">${money(e?.profit)}</strong><span class="beta-sub">${e?'Item Market estimate · 5% fee':'Price unavailable'}</span></td><td data-label="Profit / hour"><strong class="hot-value">${money(p?e?.cycleHourly:null)}</strong><span class="beta-sub">${money(e?.hourly)} theoretical / hr</span></td><td data-label="Departure"><strong>${p?p.departure<=Date.now()/1000?'Leave now':esc(time(p.departure)):'Awaiting forecast'}</strong><span class="beta-sub">${p?'Arrive '+esc(time(p.arrival))+(p.preview?' · flight preview':''):''}</span></td><td data-label=""><button type="button" class="beta-text-button" data-details="${esc(r.item_key)}">Pricing & details</button></td></tr>`;}).join('');
$('page').textContent=`Page ${page+1} of ${pages} · ${list.length} items`;$('prev').disabled=page===0;$('next').disabled=page>=pages-1;$('empty').hidden=list.length>0;
$('health').textContent=rosterError?'Reference roster unavailable · All Items incomplete':refreshError?'Forecast refresh failed · stale advice is paused':priceError?'Price refresh failed · market values may be unavailable':`${roster.length||catalog.size} reference items · ${board.length} public forecast entries · updated every 30s`;}
function details(key){const r=rows().find(r=>r.item_key===key);if(!r)return;const i=info(r),[c,name]=key.split(':');$('detail-body').innerHTML=`<h2>${esc(name)} · ${esc(countries[c]||c)}</h2><p>Current stock: <b>${stockQuantity(r)===null?'Unverified':stockQuantity(r).toLocaleString()}</b><br>Stock evidence: <b>${Number.isInteger(r.source_heartbeat_epoch)?'Publisher observation '+esc(time(r.source_heartbeat_epoch)):'No published live observation'}</b><br>Departure status: <b>${esc(adviceLabel(r,i.p))}</b></p><p>Foreign purchase price: <b>${money(i.item.foreign_price??i.item.price)}</b><br>Torn market-value reference: <b>${money(i.item.market_price)}</b>${i.item.market_price_stale?' · stale':''}<br>Net sale value after 5% Item Market fee: <b>${i.economics?money(i.item.market_price*0.95):'—'}</b><br>Estimated profit per item: <b>${money(i.economics?.unit)}</b><br>Estimated full-inventory profit: <b>${money(i.economics?.profit)}</b></p><p>Prices come automatically from the existing Torn-FREN catalog. The market value is not a guaranteed selling price. Hourly return uses a round trip, and the main figure also includes waiting until departure. Selling time, demand, missed purchases and other costs are not included.${i.item.market_price_stale||priceError?' Price data is stale or unavailable; profitability is withheld.':''}</p><a class="beta-detail-link" href="/?country=${encodeURIComponent(c)}&item=${encodeURIComponent(name)}">Forecast, evidence & stock graph ↗</a>`;if(!$('details').open)$('details').showModal();}
document.addEventListener('error',e=>{if(e.target.matches?.('[data-fallback]')){const f=document.createElement('span');f.className='hot-thumb hot-fallback';f.textContent='◈';f.setAttribute('aria-hidden','true');e.target.replaceWith(f);}},true);
document.addEventListener('click',e=>{const tab=e.target.closest('[data-view],[data-category]'),detail=e.target.closest('[data-details]');if(tab){const field=tab.hasAttribute('data-view')?'view':'category';if(field==='view')view=tab.dataset.view;else category=tab.dataset.category;for(const b of document.querySelectorAll(`[data-${field}]`))b.setAttribute('aria-pressed',String(b===tab));page=0;render();}if(detail)details(detail.dataset.details);});
for(const id of ['capacity','flight','sort','available','search'])$(id).addEventListener(id==='search'?'input':'change',()=>{const n=Number($('capacity').value);if(!Number.isInteger(n)||n<1||n>100){$('capacity').setCustomValidity('Enter 1 to 100 slots.');$('capacity').reportValidity();return;}$('capacity').setCustomValidity('');page=0;render();});
$('prev').onclick=()=>{page--;render();};$('next').onclick=()=>{page++;render();};
async function forecasts(){try{const res=await fetch('/api/first-release',{cache:'no-store'});if(!res.ok)throw Error();const d=await res.json();if(!Array.isArray(d.rows))throw Error();board=d.rows;refreshError=false;}catch(e){refreshError=true;}render();}
async function prices(){try{const res=await fetch('/api/catalog',{cache:'no-store'});if(!res.ok)throw Error();const d=await res.json(),map=new Map();for(const c of d.countries||[])for(const item of c.items||[])map.set(c.country+':'+item.item_name,item);catalog=map;priceError=false;}catch(e){priceError=true;}render();}
async function reference(){
 try{
  const res=await fetch('/first-release-assets/abroad-roster.json',{cache:'no-store'});if(!res.ok)throw Error();
  const d=await res.json();
  if(d.schema!=='torn-fren-foreign-catalog-reference-v1'||!Array.isArray(d.items)||d.items.length!==236||new Set(d.items).size!==236||!['haw:Orchid','jap:Xanax','sou:Xanax','uni:Xanax'].every(x=>d.items.includes(x)))throw Error('Invalid reference roster');
  roster=d.items;rosterError=false;
 }catch(e){roster=[];rosterError=true;}
 render();
}
reference();forecasts();prices();setInterval(forecasts,30000);setInterval(prices,300000);
})();
