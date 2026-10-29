// Browser regression for the compact planner and the actual audited VM graph.
// Fixtures are captured public JSON/HTML, never credentials or a collector DB.
// FIRST_TEN_UI_FIXTURES points to a directory with feed.json, history.json,
// catalog.json, chart-live.html and the two existing Chart.js CDN files.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('playwright');
const fixture=process.env.FIRST_TEN_UI_FIXTURES;
if(!fixture)throw Error('FIRST_TEN_UI_FIXTURES required');
const asset=path.resolve('web/first_release_assets');
const output=process.env.FIRST_TEN_UI_OUTPUT||'/tmp/torn-ui-browser-output';
fs.mkdirSync(output,{recursive:true});
(async()=>{
 const args=JSON.parse(process.env.FIRST_TEN_CHROMIUM_ARGS||'["--no-sandbox"]');
 const browser=await chromium.launch({executablePath:process.env.FIRST_TEN_CHROMIUM||undefined,args,headless:true});
 const original=JSON.parse(fs.readFileSync(path.join(fixture,'feed.json'))),delta=Math.floor(Date.now()/1000)-original.published_epoch;
 function shifted(v){if(typeof v==='number'&&v>1700000000&&v<2000000000)return v+delta;if(Array.isArray(v))return v.map(shifted);if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,shifted(x)]));return v;}
 const base=shifted(original);base.valid_until_epoch=Math.floor(Date.now()/1000)+300;
 let feed=structuredClone(base),failFeed=false;
 const history=shifted(JSON.parse(fs.readFileSync(path.join(fixture,'history.json'))));
 let errors=[];
 const context=await browser.newContext({viewport:{width:1440,height:1000},timezoneId:'America/New_York'});
 await context.route('**/*',async route=>{
  const url=new URL(route.request().url()),name=url.pathname.split('/').pop();
  if(url.pathname==='/api/first-release')return route.fulfill({status:failFeed?503:200,contentType:'application/json',body:JSON.stringify(feed)});
  if(url.pathname==='/api/history')return route.fulfill({contentType:'application/json',body:JSON.stringify(history)});
  if(url.pathname==='/api/catalog')return route.fulfill({contentType:'application/json',body:fs.readFileSync(path.join(fixture,'catalog.json'),'utf8')});
  if(url.pathname.startsWith('/first-release-assets/'))return route.fulfill({path:path.join(asset,name)});
  if(url.hostname==='cdn.jsdelivr.net')return route.fulfill({path:path.join(fixture,name),contentType:'text/javascript'});
  if(url.pathname==='/experimental'||url.pathname==='/travel-decisions')return route.fulfill({path:path.join(asset,'board.html'),contentType:'text/html'});
  if(url.pathname==='/')return route.fulfill({path:path.join(fixture,'chart-live.html'),contentType:'text/html'});
  return route.fulfill({status:404,body:'Not found'});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.clock.install();
 await page.goto('http://torn-ui.test/experimental');await page.waitForSelector('#beta-rows tr');
 assert.equal(await page.locator('#beta-rows tr').count(),10);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:path.join(output,'planner-desktop.png'),fullPage:true});
 await page.locator('#beta-search').fill('crocus');assert.equal(await page.locator('#beta-rows tr').count(),1);
 const details=page.getByRole('button',{name:'Details for Crocus'});await details.click();
 assert.equal(await page.locator('dialog[open]').count(),1);
 await page.locator('dialog summary').click();await page.waitForTimeout(1200);
 assert.equal(await page.locator('dialog details').getAttribute('open'),'');
 await page.keyboard.press('Escape');assert.equal(await page.locator('dialog[open]').count(),0);
 assert.equal(await page.evaluate(()=>document.activeElement?.dataset.details),'can:Crocus');
 await page.locator('#beta-search').fill('');await page.locator('#beta-country').selectOption('mex');assert.equal(await page.locator('#beta-rows tr').count(),2);
 await page.locator('#beta-country').selectOption('');await page.locator('#beta-type').selectOption('plushie');assert.equal(await page.locator('#beta-rows tr').count(),1);
 await page.locator('#beta-type').selectOption('');await page.locator('#beta-sort').selectOption('item');assert((await page.locator('.beta-item-name').first().textContent()).startsWith('Banana'));
 await page.locator('#beta-search').fill('not-an-item');assert(await page.locator('#beta-empty').isVisible());await page.locator('#beta-search').fill('');
 // A transient refresh failure keeps still-valid advice visible. Recalculation
 // and a network hiccup must not turn every existing forecast into a blank.
 const validAdvice=await page.locator('[data-arrival-key]').allTextContents();
 failFeed=true;await page.clock.fastForward(31000);
 await page.waitForFunction(()=>document.querySelector('#beta-health').textContent.includes('Refresh delayed'));
 const retainedAdvice=await page.locator('[data-arrival-key]').allTextContents();
 assert.equal(retainedAdvice.filter(t=>t!=='—').length,validAdvice.filter(t=>t!=='—').length);
 failFeed=false;
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'planner-mobile.png'),fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 // Fifty rows use the same list, filters and detail interaction.
 feed={...base,rows:Array.from({length:50},(_,i)=>{const r=structuredClone(base.rows[i%10]);if(i>=10)r.item_key+=' '+i;return r;})};
 await page.reload();await page.waitForSelector('#beta-rows tr');assert.equal(await page.locator('#beta-rows tr').count(),20);assert.equal(await page.locator('#beta-total').textContent(),'50');
 await page.locator('#beta-next').click();assert.equal(await page.locator('#beta-page-number').textContent(),'Page 2 of 3');
 await page.locator('#beta-next').click();assert.equal(await page.locator('#beta-rows tr').count(),10);assert(await page.locator('#beta-next').isDisabled());
 await page.locator('#beta-prev').click();assert.equal(await page.locator('#beta-rows tr').count(),20);
 await page.locator('#beta-search').fill('49');assert.equal(await page.locator('#beta-rows tr').count(),1);await page.locator('#beta-search').fill('');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:path.join(output,'planner-50-items.png')});
 // Genuine expiry removes advice even if the last forecast was cached.
 await page.clock.fastForward(301000);
 assert((await page.locator('[data-arrival-key]').allTextContents()).every(t=>t==='—'));
 assert((await page.locator('[data-leave-key]').allTextContents()).every(t=>t==='Stock data delayed'));
 // A failed initial fetch has no cached advice to display.
 failFeed=true;await page.reload();await page.waitForFunction(()=>document.querySelector('#beta-health').textContent.includes('unavailable'));
 assert.equal(await page.locator('[data-arrival-key]').count(),0);failFeed=false;feed=structuredClone(base);
 const chartPage=await context.newPage();chartPage.on('pageerror',e=>errors.push(e.message));
 await chartPage.setViewportSize({width:1894,height:958});await chartPage.goto('http://torn-ui.test/?country=can&item=Crocus');
 await chartPage.waitForFunction(()=>document.getElementById('currentStock').textContent!=='—');
 await chartPage.waitForFunction(()=>typeof Chart!=='undefined'&&Chart.getChart('stockChart'));
 assert.equal(await chartPage.locator('#first-release-panel').count(),1);
 assert.equal(await chartPage.locator('#insights-panel').isVisible(),false);
 assert(await chartPage.evaluate(()=>getComputedStyle(document.body).overflowY==='auto'));
 assert(await chartPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.equal(await chartPage.locator('.beta-history').getAttribute('open'),null);
 const canvas=await chartPage.locator('#stockChart').boundingBox();assert(canvas.height>=320);
 await chartPage.screenshot({path:path.join(output,'graph-desktop.png'),fullPage:true});
 await chartPage.locator('#chart-scroll').scrollIntoViewIfNeeded();
 assert(await chartPage.locator('#chart-scroll').evaluate(e=>e.getBoundingClientRect().bottom<=innerHeight+1));
 await chartPage.locator('#first-release-panel [data-details]').click();assert(await chartPage.locator('dialog[open]').isVisible());await chartPage.keyboard.press('Escape');
 await chartPage.setViewportSize({width:390,height:844});await chartPage.screenshot({path:path.join(output,'graph-mobile.png'),fullPage:true});assert(await chartPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 // Switching the existing item picker updates the compact banner.
 await chartPage.locator('#countrySelect').selectOption('mex');await chartPage.waitForTimeout(1200);
 assert((await chartPage.locator('#first-release-panel').textContent()).includes('Model under review'));
 await chartPage.locator('#itemSelect').selectOption('Dahlia');await chartPage.waitForTimeout(1200);
 assert((await chartPage.locator('#first-release-panel').innerHTML()).includes('mex:'));
 assert.deepEqual(errors,[]);
 await browser.close();console.log('PASS: desktop/mobile, 10/50 items, filters, sorting, details/Escape/focus, feed failure, actual chart render and scrolling, item switching.');
})().catch(e=>{console.error(e);process.exit(1);});
