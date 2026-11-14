const assert=require('node:assert/strict');
const c=require('../web/first_release_assets/hotlist-core.js');
assert.equal(c.economics({foreign_price:100},200,18,1800).profit,1620);
assert.equal(c.economics({foreign_price:100},200,30,1800).profit,2700);
assert.equal(c.economics({foreign_price:100},200,18,1800,3600).cycleHourly,810);
assert.equal(c.economics({foreign_price:100},null,18,1800),null);
assert.equal(c.economics({foreign_price:195},200,18,1800).profit,-90);
assert.equal(c.economics({foreign_price:100},200,18,1800).unit,90);
assert.equal(c.category('Camel Plushie'),'plushies');assert.equal(c.category('Xanax'),'drugs');assert.equal(c.category('African Violet'),'flowers');assert.equal(c.category('Bearer Bond'),'other');
const row={item_key:'sou:Xanax',valid_until_epoch:1200,source_heartbeat_epoch:1000,decision:{player_flight_seconds:11820,estimated_departure_epoch:1100,estimated_departure_deadline_epoch:1150},forecast:{restock_events:[{index:1,predicted_restock_epoch:18000,predicted_stock_below_30_epoch:19000}]}};
const before=JSON.stringify(row);
assert.equal(c.plan(row,1,1000).arrival,12920);
assert.equal(c.plan(row,1,1300),null);
assert.equal(c.plan(row,0,1000).arrival,18000);
assert.equal(c.plan({...row,source_heartbeat_epoch:700},1,1000),null);
assert.equal(JSON.stringify(row),before,'flight selection must not mutate stock forecasts');
assert.equal(c.MIN_HOT_MARKET_VALUE,15000);
const validPlan={departure:1100,arrival:1300};
const positiveProfit={profit:100};
assert.equal(c.hotEligible('arg:Monkey Plushie',{market_price:14999},validPlan,positiveProfit),false);
assert.equal(c.hotEligible('arg:Monkey Plushie',{market_price:15000},validPlan,positiveProfit),true);
assert.equal(c.hotEligible('arg:Monkey Plushie',{market_price:20000},null,positiveProfit),false);
assert.equal(c.hotEligible('arg:Monkey Plushie',{market_price:20000,market_price_stale:true},validPlan,positiveProfit),false);
assert.equal(c.hotEligible('arg:Monkey Plushie',{market_price:20000},validPlan,{profit:-1}),false);
for(const k of ['uni:Xanax','mex:Jaguar Plushie','haw:Orchid','cay:Banana Orchid']){
 assert.equal(c.hotEligible(k,{market_price:50000},validPlan,positiveProfit),false,k);
}
console.log('PASS hotlist calculation and forecast-selection contracts');
