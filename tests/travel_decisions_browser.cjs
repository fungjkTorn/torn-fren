// Synthetic data only. Check the real page's interactions and mobile layout.
const {chromium}=require('playwright');
const fs=require('fs'),cp=require('child_process'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 let failApi=false;
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://travel-preview.test/**',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/api/travel-decisions'){
   if(failApi)return route.fulfill({status:503,contentType:'application/json',body:'{}'});
   const args=['tests/travel_decisions_fixture.py'];
   if(u.searchParams.has('country'))args.push(u.searchParams.get('country'),u.searchParams.get('flight_seconds'));
   const body=cp.execFileSync('python',args,{env:{...process.env,PYTHONPATH:process.cwd()}}).toString();
   return route.fulfill({contentType:'application/json',body});
  }
  const html=fs.readFileSync('web/travel_decisions.html','utf8').replace('Research preview','Synthetic test preview · not live stock');
  return route.fulfill({contentType:'text/html',body:html});
 });
 await page.goto('http://travel-preview.test/travel-decisions');
 await page.waitForSelector('.item');
 assert.equal(await page.locator('.item').count(),6);
 assert.equal(await page.locator('#more').isVisible(),false);
 await page.getByRole('button',{name:'Watch Jaguar Plushie',exact:true}).click();
 await page.getByRole('button',{name:'Watchlist',exact:true}).click();
 assert.equal(await page.locator('.item').count(),1);
 await page.reload();await page.waitForSelector('.item');
 assert.equal(await page.locator('.star.saved').count(),1);
 await page.locator('#category').selectOption('Flowers');
 assert.equal(await page.locator('.item').count(),2);
 await page.locator('#category').selectOption('');
 await page.locator('#search').fill('Jaguar');
 assert.equal(await page.locator('.item').count(),1);
 await page.getByRole('button',{name:'Jaguar Plushie',exact:false}).filter({has:page.locator('.secondary')}).click();
 const input=page.getByRole('spinbutton',{name:'Your outbound flight duration in minutes'});
 await input.fill('25');
 await page.waitForTimeout(1200);
 assert.equal(await input.inputValue(),'25');
 const request=page.waitForResponse(r=>r.url().includes('flight_seconds=1500'));
 await page.getByRole('button',{name:'Apply',exact:true}).click();await request;
 await page.waitForFunction(()=>document.querySelector('.timings').textContent.includes('25m'));
 assert((await page.locator('.graphlink').getAttribute('href')).includes('country=mex'));
 await page.evaluate(()=>{
   const row=rows.find(r=>r.item_key==='mex:Jaguar Plushie');window.savedTestRow=structuredClone(row);
   row.departure_epoch=now()-10;row.departure_deadline_epoch=now()+20;
   row.decision.execution_policy='publication_delay_30s_v1';row.decision.publication_tolerance_seconds=30;
   row.decision.valid_until_epoch=now()+100;tick();
 });
 assert.notEqual(await page.locator('#tripDeparture').textContent(),'—');
 assert.equal(await page.locator('#tripArrival').textContent(),await page.evaluate(()=>time(now()+rows.find(r=>r.item_key==='mex:Jaguar Plushie').decision.player_flight_seconds)));
 await page.evaluate(()=>{rows.find(r=>r.item_key==='mex:Jaguar Plushie').departure_deadline_epoch=now()-1;tick();});
 assert.equal(await page.locator('#tripArrival').textContent(),'—');
 await page.evaluate(()=>{Object.assign(rows.find(r=>r.item_key==='mex:Jaguar Plushie'),window.savedTestRow);tick();});
 await page.locator('#search').fill('Panda');
 await page.getByRole('button',{name:'Panda Plushie',exact:false}).filter({has:page.locator('.secondary')}).click();
 assert((await page.locator('.events').textContent()).includes('3 restock estimates'));
 assert((await page.locator('.events').textContent()).includes('independently'));
 assert.notEqual(await page.locator('#tripDeparture').textContent(),'—');
 await page.evaluate(()=>{const row=rows.find(r=>r.item_key==='chi:Panda Plushie');row.decision.valid_until_epoch=now()-1;tick();});
 assert.equal(await page.locator('#tripDeparture').textContent(),'—');
 assert.equal(await page.locator('#tripArrival').textContent(),'—');
 assert.equal(await page.locator('#tripDeadline').textContent(),'—');
 await page.locator('#search').fill('Jaguar');
 await page.getByRole('button',{name:'Jaguar Plushie',exact:false}).filter({has:page.locator('.secondary')}).click();
 await page.locator('#search').fill('');
 fs.mkdirSync('test-output',{recursive:true});
 await page.screenshot({path:'test-output/travel-decisions-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'test-output/travel-decisions-mobile.png',fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 await page.evaluate(()=>{snapshot.source_poll_age_seconds=181;tick();});
 assert.equal(await page.locator('#tripArrival').textContent(),'—');
 assert.equal(await page.locator('#tripDeparture').textContent(),'—');
 assert.equal(await page.locator('#upcoming').textContent(),'0');
 assert((await page.locator('.eta').first().textContent()).includes('Awaiting a fresh window'));
 await page.getByRole('spinbutton',{name:'Your outbound flight duration in minutes'}).focus();
 failApi=true;
 await page.evaluate(()=>document.getElementById('refresh').click());
 await page.waitForFunction(()=>!document.getElementById('tripClock'));
 assert((await page.locator('#trip').textContent()).includes('Forecast unavailable'));
 assert.deepEqual(errors,[]);
 // Exercise the original graph's additive panel and marker without a CDN.
 const graph=await browser.newPage();
 await graph.setContent('<div id="sharedDeparturePreview" hidden></div>');
 await graph.evaluate(()=>{window.Chart={register(plugin){window.testPlugin=plugin;}};});
 await graph.addScriptTag({content:fs.readFileSync('web/static/shared_departure_preview.js','utf8')});
 await graph.evaluate(()=>{
   const t=Math.floor(Date.now()/1000);window.testNow=t;window.testDraws=0;
   const row={departure_epoch:t+1200,departure_deadline_epoch:t+1200,
     departure_source:'explicit_recommendation',decision:{player_flight_seconds:1020,valid_until_epoch:t+100}};
   window.sharedDeparturePreview.set({row,source_poll_age_seconds:10,asof_epoch:t,evaluated_at_epoch:t});
   window.testChart={scales:{x:{getPixelForValue(){return 50;}}},chartArea:{left:0,right:300,top:0,bottom:200},
     ctx:{save(){},restore(){},setLineDash(){},beginPath(){},moveTo(){},lineTo(){},stroke(){window.testDraws++;},fillText(){}}};
   window.testPlugin.afterDraw(window.testChart);
 });
 assert((await graph.locator('#sharedDeparturePreview').textContent()).includes('Land'));
 assert.equal(await graph.evaluate(()=>window.testDraws),1);
 await graph.evaluate(()=>{Date.now=()=>(window.testNow+101)*1000;window.testPlugin.afterDraw(window.testChart);});
 assert.equal(await graph.evaluate(()=>window.testDraws),1);
 await graph.waitForTimeout(1100);
 assert((await graph.locator('#sharedDeparturePreview').textContent()).includes('Await a fresh'));
 await graph.evaluate(()=>{
   const t=window.testNow+101;
   window.sharedDeparturePreview.set({row:{departure_epoch:t-10,departure_deadline_epoch:t+20,
     departure_source:'explicit_recommendation',decision:{publication_tolerance_seconds:30,
       player_flight_seconds:1020,valid_until_epoch:t+100}},
     source_poll_age_seconds:10,asof_epoch:t-10,evaluated_at_epoch:t});
 });
 assert((await graph.locator('#sharedDeparturePreview').textContent()).includes(await graph.evaluate(()=>new Date((window.testNow+101+1020)*1000).toLocaleTimeString())));
 await graph.evaluate(()=>{Date.now=()=>(window.testNow+122)*1000;});
 await graph.waitForTimeout(1100);
 assert((await graph.locator('#sharedDeparturePreview').textContent()).includes('Await a fresh'));
 await graph.evaluate(()=>window.sharedDeparturePreview.clear());
 assert.equal(await graph.locator('#sharedDeparturePreview').isHidden(),true);
 await graph.close();
 await browser.close();console.log('Travel UI: search, category, watchlist persistence, personalized flight, graph link, desktop/mobile passed.');
})().catch(e=>{console.error(e);process.exit(1)});
