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
function economics(item,sale,capacity,seconds,waitSeconds=0,feeRate=0.05){
 const buy=item.foreign_price??item.price;
 if(!Number.isFinite(buy)||buy<=0||!Number.isFinite(sale)||sale<=0||!Number.isInteger(capacity)||capacity<1||!Number.isFinite(seconds)||seconds<=0||!Number.isFinite(feeRate)||feeRate<0||feeRate>=1)return null;
 const netSale=sale*(1-feeRate);
 const profit=(netSale-buy)*capacity,round=seconds*2;
 return {profit,unit:netSale-buy,hourly:profit*3600/round,cycleHourly:profit*3600/(round+Math.max(0,waitSeconds)),netSale,feeRate,upfront:buy*capacity};
}
const NIKEH_PAYOUTS=Object.freeze({
 'can:Bear Gall':35000,
 'chi:Pangolin Scales':205000,
 'haw:Shark Fin':66000,
 'chi:Tiger Bone Powder':70000,
 'jap:Whale Meat':40000
});
function saleQuote(key,item){
 if(item?.market_price_stale===true)return null;
 if(Object.hasOwn(NIKEH_PAYOUTS,key)){
  return {price:NIKEH_PAYOUTS[key],feeRate:0,source:'Nikeh NPC',requiresEducation:true};
 }
 if(!Number.isFinite(item?.market_price)||item.market_price<=0)return null;
 return {price:item.market_price,feeRate:0.05,source:'Item Market',requiresEducation:false};
}
const MIN_HOT_MARKET_VALUE=15000;
// Deliberate shortlist, NOT the full catalog: no public model is promoted by listing an item.
// These 25 already tracked items plus five Nikeh NPC redemption opportunities are
// the starter profitability pool; All Items remains an unrestricted live/catalog union.
const HOT_CANDIDATES=new Set([
 'arg:Ceibo Flower','arg:Monkey Plushie','can:Crocus','can:Wolverine Plushie',
 'can:Xanax','cay:Banana Orchid','cay:Stingray Plushie',
 'chi:Panda Plushie','chi:Peony','haw:Orchid','jap:Cherry Blossom','jap:Xanax',
 'mex:Dahlia','mex:Jaguar Plushie','sou:African Violet','sou:Lion Plushie','sou:Xanax',
 'swi:Chamois Plushie','swi:Edelweiss','uae:Camel Plushie','uae:Tribulus Omanense',
 'uni:Heather','uni:Nessie Plushie','uni:Red Fox Plushie','uni:Xanax',
 ...Object.keys(NIKEH_PAYOUTS)
]);
const HOT_EXCLUSIONS=new Set(['uni:Xanax','mex:Jaguar Plushie','haw:Orchid','cay:Banana Orchid']);
function hotEligible(key,item,p,e){
 return HOT_CANDIDATES.has(key)
   && !HOT_EXCLUSIONS.has(key)
   && Number.isFinite(item?.market_price)
   && item.market_price>=MIN_HOT_MARKET_VALUE
   && item.market_price_stale!==true
   && Number.isFinite(e?.profit)&&e.profit>0;
}
// The forecast argument is intentionally optional for profitability-only items.
// It must NEVER be treated as permission to recommend an unverified departure.
const api={flights,category,plan,economics,saleQuote,NIKEH_PAYOUTS,HOT_CANDIDATES,MIN_HOT_MARKET_VALUE,HOT_EXCLUSIONS,hotEligible};if(typeof module!=='undefined')module.exports=api;else root.TornHotList=api;
})(typeof window==='undefined'?globalThis:window);
