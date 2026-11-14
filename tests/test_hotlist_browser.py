"""Browser contracts for Hot List shortlist vs unrestricted All Items (synthetic fixtures)."""
from pathlib import Path
import json, time
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
now=int(time.time())
keys=[
 'arg:Ceibo Flower','arg:Monkey Plushie','can:Crocus','can:Wolverine Plushie',
 'can:Xanax','cay:Banana Orchid','cay:Stingray Plushie','chi:Panda Plushie',
 'chi:Peony','haw:Orchid','jap:Cherry Blossom','jap:Xanax','mex:Dahlia',
 'mex:Jaguar Plushie','sou:African Violet','sou:Lion Plushie','sou:Xanax',
 'swi:Chamois Plushie','swi:Edelweiss','uae:Camel Plushie',
 'uae:Tribulus Omanense','uni:Heather','uni:Nessie Plushie',
 'uni:Red Fox Plushie','uni:Xanax',
 'can:Bear Gall','chi:Pangolin Scales','haw:Shark Fin',
 'chi:Tiger Bone Powder','jap:Whale Meat',
 'mex:Budget Trinket'
]
nikeh={'can:Bear Gall':35000,'chi:Pangolin Scales':205000,
       'haw:Shark Fin':66000,'chi:Tiger Bone Powder':70000,
       'jap:Whale Meat':40000}
catalog={}
rows=[]
for j,key in enumerate(keys):
 country,name=key.split(':',1)
 entry={'item_name':name,'item_id':j+1,'foreign_price':18910,'market_price':20000,
        'market_price_stale':False}
 if key=='haw:Shark Fin':
  entry.update(foreign_price=20546,market_price=65795)
 if key=='mex:Budget Trinket':
  entry.update(foreign_price=100,market_price=1000)
 catalog.setdefault(country,[]).append(entry)
 if key not in nikeh and key!='mex:Budget Trinket':
  flight={'arg':111,'can':27,'cay':23,'chi':160,'haw':89,'jap':149,
          'mex':17,'sou':197,'swi':116,'uae':180,'uni':106}[country]*60
  rows.append({'item_key':key,'valid_until_epoch':now+180,
               'source_heartbeat_epoch':now,
               'forecast':{'observed_current_quantity':2500},
               'decision':{'player_flight_seconds':flight,
                           'estimated_departure_epoch':now,
                           'estimated_departure_deadline_epoch':now+130,
                           'selected_restock_event_index':1}})
  if key=='swi:Edelweiss':
   rows[-1]['decision']['estimated_departure_epoch']=now+120
   rows[-1]['decision']['estimated_departure_deadline_epoch']=now+150
payload={'countries':[{'country':c,'items':v} for c,v in catalog.items()]}

with sync_playwright() as p:
 chromium_path='/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else None
 browser=p.chromium.launch(headless=True,executable_path=chromium_path,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  path=r.request.url.split('https://test.local')[-1].split('?')[0]
  if path=='/api/catalog':r.fulfill(json=payload)
  elif path=='/api/first-release':r.fulfill(json={'rows':rows})
  elif path.startswith('/first-release-assets/'):
   f=root/'web/first_release_assets'/path.rsplit('/',1)[-1]
   media='text/css' if f.suffix=='.css' else 'application/json' if f.suffix=='.json' else 'application/javascript'
   r.fulfill(body=f.read_bytes(),content_type=media)
  elif path=='/experimental':
   r.fulfill(body=(root/'web/first_release_assets/hotlist.html').read_bytes(),content_type='text/html')
  else:r.abort()
 page.route('**/*',route)
 page.goto('https://test.local/experimental')
 page.wait_for_function("document.querySelectorAll('#rows tr').length===10 && document.querySelector('#health').textContent.includes('236 reference items')")
 assert page.locator('#capacity').input_value()=='15'
 assert page.locator('#sort').input_value()=='hourly'
 assert 'Page 1 of ' in page.locator('#page').inner_text()
 page.locator('#next').click()
 assert 'Page 2 of ' in page.locator('#page').inner_text()
 page.get_by_role('button',name='Drugs',exact=True).click()
 assert page.locator('#rows tr').count()>0
 page.get_by_role('button',name='All',exact=True).click()


 # Swiss Edelweiss is excluded from Hot List and remains available in All Items.
 page.locator('#search').fill('Edelweiss')
 assert page.locator('#rows tr').count()==0
 page.get_by_role('button',name='All Items',exact=True).click()
 page.wait_for_function("document.querySelectorAll('#rows tr').length===1")
 assert 'Edelweiss' in page.locator('#rows').inner_text()
 digits=lambda value:int(''.join(c for c in value if c.isdigit()))
 primary=digits(page.locator('#rows .hot-value').nth(1).inner_text())
 subline=page.locator('#rows td[data-label="Profit / hour"] .beta-sub').inner_text()
 assert 'including departure wait' in subline,subline
 wait_adjusted=digits(subline.split(' / hr')[0])
 assert primary>wait_adjusted,(primary,wait_adjusted)
 page.locator('#sort').select_option('cycle')
 assert digits(page.locator('#rows .hot-value').nth(1).inner_text())==wait_adjusted
 assert 'theoretical / hr' in page.locator('#rows td[data-label="Profit / hour"] .beta-sub').inner_text()
 page.locator('#sort').select_option('hourly')
 page.get_by_role('button',name='Hot List',exact=True).click()
 page.locator('#search').fill('')

 # Nikeh item appears without a published forecast, using fixed NPC, not 5% market fee.
 page.locator('#search').fill('Shark Fin')
 page.wait_for_function("document.querySelectorAll('#rows tr').length===1")
 shark=page.locator('#rows').inner_text()
 assert 'Nikeh fixed NPC · no fee' in shark,shark
 assert '$681,810' in shark,shark
 assert '$229,824' in shark,shark
 assert 'Theoretical profit only' in shark,shark
 assert 'Awaiting forecast' in shark and 'Leave now' not in shark,shark
 page.locator('[data-details]').first.evaluate("(b)=>b.click()")
 info=page.locator('#detail-body').inner_text()
 assert 'Sports Administration' in info and 'Fixed Nikeh Performance NPC payout' in info,info
 assert '$66,000' in info and '$681,810' in info,info
 page.locator('#details .beta-dialog-close').click()

 # The Hot List $15k market-value floor and manual exclusions do not affect All Items.
 page.locator('#search').fill('Budget Trinket')
 assert page.locator('#rows tr').count()==0
 page.get_by_role('button',name='All Items',exact=True).click()
 page.wait_for_function("document.querySelectorAll('#rows tr').length===1")
 assert 'Budget Trinket' in page.locator('#rows').inner_text()
 page.locator('#search').fill('Jaguar Plushie')
 assert 'Jaguar Plushie' in page.locator('#rows').inner_text()
 page.locator('#search').fill('Xanax')
 page.wait_for_function("document.querySelectorAll('#rows tr').length===4")
 xanax=page.locator('#rows').inner_text()
 assert all(country in xanax for country in ('Japan','South Africa','United Kingdom','Canada')),xanax

 # Item Market still charges 5% fee. Pricing is read-only.
 page.locator('#search').fill('Ceibo Flower')
 page.wait_for_function("document.querySelectorAll('#rows tr').length===1")
 page.locator('#capacity').fill('30')
 page.locator('#capacity').dispatch_event('change')
 assert '$2,700' in page.locator('#rows').inner_text()
 assert 'Item Market estimate · 5% fee' in page.locator('#rows').inner_text()
 page.locator('#search').fill('Orchid')
 assert 'Hawaii' in page.locator('#rows').inner_text()
 assert page.locator('#rows .beta-dot').count()==0
 page.screenshot(path=str(root/'desktop-test.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
 assert not errors,errors
 browser.close()
print('PASS: Edelweiss excluded only from Hot List; primary hourly matches selected sort; Nikeh and unrestricted All Items preserved')
