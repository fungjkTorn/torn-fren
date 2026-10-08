from services.arbitrage_live import (
    get_foreign_item_catalog,
    fetch_tornw3b_bazaar,
    fetch_tornw3b_buy_offers,
    fetch_tornexchange_buy_offers,
    parse_tornexchange_listings_html,
    _session,
    TORN_EXCHANGE_LISTINGS_URL,
)

TARGETS={"Lighter","Samurai Sword","Grenade","Paper Weight","AK-47","Axe","Meteorite Fragment","Patagonian Fossil","Basalt Point"}
catalog={x.item_name:x for x in get_foreign_item_catalog() if x.item_name in TARGETS}
s=_session()

for name in sorted(TARGETS):
    item=catalog.get(name)
    print("\nTARGET", name, "id", getattr(item,"item_id",None), "countries", getattr(item,"countries",None), "costs", getattr(item,"abroad_costs",None))
    if item is None:
        continue
    try:
        b=fetch_tornw3b_bazaar(item,session=s)
        print("W3B_BAZAAR",len(b),"cheapest",min((x.unit_price for x in b),default=None))
    except Exception as e:
        print("W3B_BAZAAR_ERROR",repr(e))
    try:
        t=fetch_tornw3b_buy_offers(item,session=s)
        print("W3B_TRADERS",len(t),"best",max((x.unit_price for x in t),default=None))
    except Exception as e:
        print("W3B_TRADER_ERROR",repr(e))

    r=s.get(TORN_EXCHANGE_LISTINGS_URL,params={"model_name_contains":name},timeout=12)
    print("URL",r.url,"status",r.status_code,"bytes",len(r.text))
    rows=parse_tornexchange_listings_html(r.text,item_id=item.item_id,item_name=item.item_name)
    print("TE_PAGE_PARSED",[(x.buyer_name,x.unit_price,x.url) for x in rows[:10]])

    try:
        offers=fetch_tornexchange_buy_offers(item,session=s,force=True)
        print("TE_FINAL",[(x.buyer_name,x.unit_price,x.url) for x in offers[:10]])
    except Exception as e:
        print("TE_FINAL_ERROR",repr(e))

    from bs4 import BeautifulSoup
    soup=BeautifulSoup(r.text,"html.parser")
    count=0
    for a in soup.find_all("a",href=True):
        href=str(a.get("href") or "")
        if "/prices/" not in href:
            continue
        node=a
        card=None
        for _ in range(7):
            if node is None: break
            text=node.get_text(" ",strip=True)
            if "$" in text and ("Price List" in text or "Trade Now" in text):
                card=node;break
            node=node.parent
        if card is None: continue
        text=card.get_text(" ",strip=True)
        if name.casefold() in text.casefold():
            print("CARD",repr(text[:500]))
            count+=1
            if count>=6: break
