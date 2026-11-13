(function(root){
'use strict';
const flights={mex:[24,17,12,7],cay:[33,23,17,10],can:[39,27,19,12],haw:[127,89,63,38],uni:[151,106,75,45],arg:[158,111,79,47],swi:[166,116,83,50],jap:[213,149,107,64],chi:[229,160,114,69],uae:[257,180,128,77],sou:[282,197,141,85]};
const flowers=new Set(['Dahlia','Crocus','Orchid','Heather','Ceibo Flower','Edelweiss','Cherry Blossom','Peony','Tribulus Omanense','African Violet','Banana Orchid']);
function category(name){return /plushie/i.test(name)?'plushies':/^(xanax|cannabis|opium|ecstasy|ketamine|lsd|pcp|shrooms|speed|vicodin)$/i.test(name)?'drugs':flowers.has(name)?'flowers':'other';}
function plan(row,profile,at){
 const d=row.decision||{},country=row.item_key.split(':')[0],minutes=flights[country]?.[profile];
 const seconds=profile===1?d.player_flight_seconds:minutes*60;
 if(!Number.isFinite(seconds)||seconds<=0||!Number.isInteger(row.valid_until_epoch)||at>row.valid_until_epoch||!Number.isInteger(row.source_heartbeat_epoch)||at-row.source_heartbeat_epoch>180||at<row.source_heartbeat_epoch||String(d.status).startsWith('STALE'))return null;
 if(profile===1){if(!Number.isInteger(d.estimated_departure_epoch)||!Number.isInteger(d.estimated_departure_deadline_epoch)||at>d.estimated_departure_deadline_epoch)return null;return {departure:Math.max(at,d.estimated_departure_epoch),arrival:Math.max(at,d.estimated_departure_epoch)+seconds,seconds,index:d.selected_restock_event_index,preview:false};}
 // Same stock forecasts, earliest reachable batch. Different flights remain previews.
 const f=row.forecast||{},currentEnd=f.predicted_stock_below_30_epoch??f.current_stock_end_epoch;
 if(f.observed_current_quantity>30&&Number.isInteger(currentEnd)&&at+seconds+10<=currentEnd)return {departure:at,arrival:at+seconds,seconds,index:0,preview:true};
 const events=f.restock_events?.length?f.restock_events:d.forecast_events||[];
 for(const e of [...events].sort((a,b)=>a.predicted_restock_epoch-b.predicted_restock_epoch)){
  const start=e.predicted_restock_epoch,end=e.predicted_stock_below_30_epoch;
  if(!Number.isInteger(start)||!Number.isInteger(end)||end<=start)continue;
  const departure=Math.max(at,start-seconds),arrival=departure+seconds;
  if(arrival+10<=end)return {departure,arrival,seconds,index:e.event_index??e.index,preview:true};
 }
 return null;
}
function economics(item,sale,capacity,seconds,waitSeconds=0){
 const buy=item.foreign_price??item.price;
 if(!Number.isFinite(buy)||buy<=0||!Number.isFinite(sale)||sale<=0||!Number.isInteger(capacity)||capacity<1||!Number.isFinite(seconds)||seconds<=0)return null;
 // Torn market-value reference, net of the existing 5% Item Market selling fee.
 const netSale=sale*0.95;
 const profit=(netSale-buy)*capacity,round=seconds*2;
 return {profit,unit:netSale-buy,hourly:profit*3600/round,cycleHourly:profit*3600/(round+Math.max(0,waitSeconds))};
}
const api={flights,category,plan,economics};if(typeof module!=='undefined')module.exports=api;else root.TornHotList=api;
})(typeof window==='undefined'?globalThis:window);
