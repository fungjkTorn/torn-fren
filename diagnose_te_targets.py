from services.arbitrage_live import (
    get_foreign_item_catalog,
    parse_tornexchange_listings_html,
    _session,
    TORN_EXCHANGE_LISTINGS_URL,
)

TARGETS={"Axe","AK-47","Meteorite Fragment","Patagonian Fossil","Basalt Point"}
catalog={x.item_name:x for x in get_foreign_item_catalog() if x.item_name in TARGETS}
s=_session()

for name in sorted(TARGETS):
    item=catalog.get(name)
    print("\nTARGET", name, "id", getattr(item,"item_id",None))
    if item is None:
        continue
    r=s.get(TORN_EXCHANGE_LISTINGS_URL,params={"model_name_contains":name},timeout=12)
    print("URL",r.url,"status",r.status_code,"bytes",len(r.text))
    rows=parse_tornexchange_listings_html(r.text,item_id=item.item_id,item_name=item.item_name)
    print("PARSED",[(x.buyer_name,x.unit_price,x.url) for x in rows[:10]])

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
            if count>=5: break
