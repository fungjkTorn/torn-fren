"""Browser contract checks with explicitly synthetic fixtures, no network."""
from pathlib import Path
import json,time
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
now=int(time.time())
names=['Camel Plushie','Xanax','African Violet','Bearer Bond']
items=[{'item_name':names[i%4]+(' '+str(i) if i>=4 else ''),'item_id':i+1,'foreign_price':100,'market_price':200,'quantity':2500,'market_price_stale':False} for i in range(24)]
rows=[{'item_key':'sou:'+i['item_name'],'valid_until_epoch':now+170,'source_heartbeat_epoch':now,'forecast':{'observed_current_quantity':2500},'decision':{'player_flight_seconds':11820,'estimated_departure_epoch':now,'estimated_departure_deadline_epoch':now+120,'selected_restock_event_index':1}} for i in items]
with sync_playwright() as p:
 chromium_path='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None
 browser=p.chromium.launch(headless=True,executable_path=chromium_path,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  path=r.request.url.split('https://test.local')[-1].split('?')[0]
  if path=='/api/catalog':r.fulfill(json={'countries':[{'country':'sou','items':items}]})
  elif path=='/api/first-release':r.fulfill(json={'rows':rows})
  elif path.startswith('/first-release-assets/'):
   f=root/'web/first_release_assets'/path.rsplit('/',1)[-1];r.fulfill(body=f.read_bytes(),content_type='text/css' if f.suffix=='.css' else 'application/javascript')
  elif path=='/':r.fulfill(body=(root/'web/first_release_assets/hotlist.html').read_bytes(),content_type='text/html')
  else:r.abort()
 page.route('**/*',route);page.goto('https://test.local/');page.wait_for_function("document.querySelectorAll('#rows tr').length===10")
 assert 'Page 1 of 3' in page.locator('#page').inner_text()
 page.locator('#next').click();assert 'Page 2 of 3' in page.locator('#page').inner_text()
 page.get_by_role('button',name='Drugs',exact=True).click();assert page.locator('#rows tr').count()==1
 page.get_by_role('button',name='All',exact=True).click();page.get_by_role('button',name='All Items',exact=True).click()
 page.locator('#capacity').fill('30');page.locator('#capacity').dispatch_event('change');assert '$2,700' in page.locator('#rows').inner_text()
 detail_key=page.locator('[data-details]').first.get_attribute('data-details')
 page.evaluate("document.addEventListener('click',e=>{window.__lastHotClick={target:e.target.tagName,closest:e.target.closest('[data-details]')?.getAttribute('data-details'),button:e.target.outerHTML.slice(0,180)}},true)")
 page.locator('[data-details]').first.click()
 detail_text=page.locator('#detail-body').inner_text()
 diagnostic=page.evaluate("({url:location.href,open:document.getElementById('details').open,html:document.getElementById('detail-body').innerHTML,clicked:document.querySelector('[data-details]')?.getAttribute('data-details'),event:window.__lastHotClick})")
 assert 'Net sale value after 5% Item Market fee' in detail_text,(detail_key,diagnostic,detail_text,errors)
 assert page.locator('#detail-body input').count()==0
 page.locator('#details .beta-dialog-close').click()
 assert 'Item Market estimate · 5% fee' in page.locator('#rows').inner_text()
 assert page.locator('#rows .beta-dot').count()==0
 page.screenshot(path=str(root/'desktop-test.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 assert not errors,errors
 browser.close()
print('PASS: pagination, categories, capacity recalculation, automatic Item Market pricing, no dots, mobile overflow, no JS errors')
