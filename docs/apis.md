# API Research Notes

## Official Torn API
Two versions currently exist:
- **v1** (classic): `https://api.torn.com/{category}/{id}?selections=...&key=...`
  Categories: User, Property, Faction, Company, Market, Torn.
- **v2** (newer, actively developed): accepts selections and IDs as path and query params.
  Docs: https://www.torn.com/swagger.php

### Open questions to research:
- [ ] What travel-related endpoints/selections exist?
- [ ] What item endpoints exist, and do they include travel-country stock data?
- [ ] What market endpoints exist beyond `bazaar`?
- [ ] What are the current rate limits per key?
- [ ] Is v2 worth migrating to now, or stable enough to wait on?

## YATA
### Open questions to research:
- [ ] What endpoints does YATA's public API expose?
- [ ] Does it cover travel, stocks, market, or profit data specifically?
- [ ] Does it require its own API key, or Torn's?

## TornStats
### Open questions to research:
- [ ] What endpoints exist?
- [ ] What data does it offer that Torn's own API doesn't?