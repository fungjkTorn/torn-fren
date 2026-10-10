# V40 optional lightweight graph / legacy V2 backup

Status: researched and tested release **not activated until operator runs its SHA-locked deploy script**.

## CPU reason

Live VM October 10 process observations: web uvicorn averaged ~86% of one core
over its process lifetime, v39 audit worker at 35% of one core while running,
collector ~0.2%, and fresh vmstat samples had 24–32% idle capacity.
This does not prove precisely which web function used 86% CPU, so the feature
must be tested with before/after metrics. Frequent open-page /api/history
requests start both expensive per-item cycle analysis and V2 inference, which
are plausible contributors. The background V39 audit worker is independent
and retains historical forecast evidence and its CPU cap.

## Optional graph policy

- Default V40 with `TORN_FREN_V40_LIGHT_GRAPH=1`: stock chart rows,
  latest foreign cost, profitability, market value, item browser and historical
  change graph stay active. Do not schedule `get_stock_graph_analysis`,
  `build_live_prediction_v2` or `get_recent_active_forecasts` on 30s
  webpage refreshes. Historical cycle stats/peak confidence and overlay are
  absent in this mode, rather than falsely reporting old cached estimates.
- Visible **V2 backup: Off** button enables existing original graph/V2
  prediction logic for a temporary ten-minute session. Button off or page
  reload immediately reverts to lightweight default. Public prediction
  validation never claims disabled V2 data as champion output.
- Revert via `deploy/scripts/rollback_v40_light_graph.sh` or remove
  the `v40-web-light-graph.conf` drop-in and restart only the website.
- Website cache flags from V39 remain active; original V39.1 graph is
  untouched when the new feature flag is absent.
- Collector, raw SQLite, V39 routine forecast auditing, Discord bot,
  private V38 25%-capped model timer and Japan Xanax research unchanged.
- Run observational `vmstat 1 5`, `ps -eo pid,%cpu,etime,args --sort=-%cpu`
  and read-only shadow database queries after rollout. Lifetime %CPU alone
  is not a before/after runtime comparison; use vmstat or per-process deltas.

## Release

This is a V39.1-derived release, expected production base
`dd84271a40b6e5dac2551c9fbb1291f47463c057`. CI must pass
`test_v40_light_graph.py`, V39 cache and collector regressions.
No database migration. The deploy script backs up current web systemd dropins,
fast-forwards production, installs a new web-only environment drop-in and
restarts only `torn-fren-web.service`. Health checks retry to avoid a
false failure during normal uvicorn startup. A rollback script restores V39.1
source and removes only the V40 dropin without touching any stock or audit data.
