from services.arbitrage_live import (
    get_foreign_item_catalog,
    fetch_tornw3b_bazaar,
    fetch_tornw3b_buy_offers,
    fetch_tornexchange_buy_offers,
    parse_tornexchange_listings_html,
    _session,
    TORN_EXCHANGE_LISTINGS_URL,
)

TARGETS={"Meteorite Fragment","Patagonian Fossil"}

for item in get_foreign_item_catalog():
    if item.item_name not in TARGETS:
        continue
    print(f"TARGET name={item.item_name!r} id={item.item_id!r} countries={item.countries!r} costs={item.abroad_costs!r}")
    s=_session()
    try:
        rows=fetch_tornw3b_bazaar(item,session=s)
        print("W3B_BAZAAR",len(rows),"cheapest",min((x.unit_price for x in rows),default=None))
    except Exception as e:
        print("W3B_BAZAAR_ERROR",repr(e))
    try:
        rows=fetch_tornw3b_buy_offers(item,session=s)
        print("W3B_TRADERS",len(rows),"best",max((x.unit_price for x in rows),default=None))
    except Exception as e:
        print("W3B_TRADER_ERROR",repr(e))
    try:
        rows=fetch_tornexchange_buy_offers(item,session=s,force=True)
        print("TE_API",[(x.buyer_name,x.unit_price,x.buyer_id) for x in rows])
    except Exception as e:
        print("TE_API_ERROR",repr(e))

    for params in [
        {"model_name_contains":item.item_name},
        {"model_name":item.item_name},
        {"search":item.item_name},
        {"q":item.item_name},
    ]:
        try:
            r=s.get(TORN_EXCHANGE_LISTINGS_URL,params=params,timeout=12)
            print("TE_PAGE",params,"status",r.status_code,"url",r.url,"bytes",len(r.text))
            parsed=parse_tornexchange_listings_html(r.text,item_id=item.item_id,item_name=item.item_name)
            print("TE_PAGE_PARSED",len(parsed),[(x.buyer_name,x.unit_price,x.buyer_id) for x in parsed[:5]])
        except Exception as e:
            print("TE_PAGE_ERROR",params,repr(e))
