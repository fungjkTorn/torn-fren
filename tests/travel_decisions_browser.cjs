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
 await page.locator('#search').fill('');
 fs.mkdirSync('test-output',{recursive:true});
 await page.screenshot({path:'test-output/travel-decisions-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'test-output/travel-decisions-mobile.png',fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
 await page.getByRole('spinbutton',{name:'Your outbound flight duration in minutes'}).focus();
 failApi=true;
 await page.evaluate(()=>document.getElementById('refresh').click());
 await page.waitForFunction(()=>!document.getElementById('tripClock'));
 assert((await page.locator('#trip').textContent()).includes('Forecast unavailable'));
 assert.deepEqual(errors,[]);
 await browser.close();console.log('Travel UI: search, category, watchlist persistence, personalized flight, graph link, desktop/mobile passed.');
})().catch(e=>{console.error(e);process.exit(1)});
