// Canary bridge preserves the upstream response and ignores prior selections.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({headless:true}),page=await browser.newPage();
 await page.goto('about:blank');
 await page.evaluate(()=>{
  window.seenPreview=[];window.sharedDeparturePreview={clear(){window.seenPreview.push(null)},set(v){window.seenPreview.push(v)}};
  window.pendingRequests=[];
  window.fetch=(input)=>new Promise(resolve=>{window.pendingRequests.push({input,resolve})});
 });
 await page.addScriptTag({content:fs.readFileSync('web/static/shared_canary_graph_boot.js','utf8')});
 // Use same-origin absolute URLs for the about:blank test surface.
 await page.evaluate(()=>{
  window.first=fetch('about:/api/history?country=mex&item=Jaguar');
  window.second=fetch('about:/api/history?country=chi&item=Peony');
  const response=value=>({clone(){return {json:async()=>({analysis:{shared_departure_preview:value}})}},original:true});
  window.pendingRequests[1].resolve(response({item:'Peony'}));
  window.pendingRequests[0].resolve(response({item:'Jaguar'}));
 });
 const result=await page.evaluate(async()=>{const r=await Promise.all([window.first,window.second]);return {original:r.every(x=>x.original),seen:window.seenPreview}});
 assert(result.original);assert.equal(result.seen.filter(x=>x?.item==='Peony').length,1);
 assert.equal(result.seen.filter(x=>x?.item==='Jaguar').length,0);
 await browser.close();console.log('Canary graph bridge: original response and selection race passed.');
})().catch(e=>{console.error(e);process.exit(1)});
