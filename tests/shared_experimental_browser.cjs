// Synthetic API/history and chart stub; exercises the exact recovered page renderer.
const {chromium}=require('playwright');
const cp=require('child_process'),fs=require('fs'),assert=require('assert');
(async()=>{
 const html=cp.execFileSync('python',['-c','from pathlib import Path;from deploy.scripts.prepare_shared_experimental_page import prepare_html;print(prepare_html(Path("tests/fixtures/experimental_owner_20261012.html").read_bytes()))']).toString();
 const browser=await chromium.launch({headless:true}),page=await browser.newPage();
 const errors=[];let failed=false;
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/api/experimental/v41/predictions')return route.fulfill(failed?{status:503,body:'{}'}:{contentType:'application/json',body:cp.execFileSync('python',['tests/experimental_shared_fixture.py'],{env:{...process.env,PYTHONPATH:process.cwd()}}).toString()});
  if(u.pathname==='/api/history')return route.fulfill({contentType:'application/json',body:JSON.stringify({rows:[{timestamp:Math.floor(Date.now()/1000)-60,quantity:200}],analysis:{}})});
  if(u.pathname==='/shared_experimental_rows.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync('web/static/shared_experimental_rows.js','utf8')});
  if(u.pathname==='/champion_graph.js')return route.fulfill({contentType:'text/javascript',body:'window.ChampionGraph={extractEvents(){return []},describe(){return {restockCount:0,depletionCount:0,lastRestock:null,lastDepletion:null,avgZeroToRestockSeconds:null,avgStockLifetimeSeconds:null}},stockPoints(){return []},eventPoints(){return []}};'});
  if(u.hostname==='cdn.jsdelivr.net')return route.fulfill({contentType:'text/javascript',body:u.pathname.includes('chart.umd')?'window.Chart=class{constructor(){window.testLastGraph=this;this.update=()=>{};this.destroy=()=>{};}};':''});
  if(u.pathname==='/experimental')return route.fulfill({contentType:'text/html',body:html});
  return route.fulfill({status:404,body:''});
 });
 await page.goto('http://experimental-preview.test/experimental');
 await page.waitForSelector('#rows tr');
 assert((await page.locator('#rows tr').textContent()).includes('Reconfirm before leaving'));
 assert.notEqual(await page.locator('#rows tr td').nth(3).textContent(),'—');
 await page.getByRole('button',{name:'mex:Jaguar Plushie',exact:true}).click();
 await page.waitForFunction(()=>window.testLastGraph?.$snap?.actionable===true);
 await page.evaluate(()=>{const t=sharedRawRows[0].valid_until+1;Date.now=()=>t*1000;});
 await page.waitForTimeout(1100);
 assert.equal(await page.locator('#rows tr td').nth(3).textContent(),'—');
 assert.equal(await page.locator('#rows tr td').nth(4).textContent(),'—');
 assert.equal(await page.evaluate(()=>window.testLastGraph.$snap.actionable),false);
 failed=true;await page.evaluate(()=>refresh());
 await page.waitForFunction(()=>document.getElementById('state').textContent.includes('unavailable'));
 assert.equal(await page.locator('#rows tr').count(),0);
 assert.equal(await page.evaluate(()=>window.testLastGraph.$snap),null);
 assert.deepEqual(errors,[]);
 await browser.close();console.log('Recovered experimental page: shared row, observed graph, fixed expiry, API failure passed.');
})().catch(e=>{console.error(e);process.exit(1)});
