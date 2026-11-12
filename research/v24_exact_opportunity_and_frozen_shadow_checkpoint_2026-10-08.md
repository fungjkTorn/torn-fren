# V24 research checkpoint — exact opportunity geometry and frozen champion shadow (2026-10-08)

**No production changes, no champion promotion.** This corrects a genuine flaw in earlier V22 12-hour 'oracle feasibility' diagnostics: scanning hypothetical departures every 15 minutes misses brief qualifying-stock intervals.

## Exact historical feasibility findings
Frozen original DB SHA256 `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`, all 41 sub-50% item-country pairs, minimum 30 units at arrival or within 10 seconds, full 12-hour recorded horizon, provider bounce and collection gap exclusions.

- Total complete observable starting sessions: **5,631**.
- At least one feasible hindsight arrival using 15-minute departure grid: **2,594** sessions.
- Using five-minute grid: **2,666**.
- Using all actual qualified-stock intervals (second-level timing): **2,668**.
- Thus 15-minute sampling missed **74** viable hypothetical opportunities, 72 from only two items; five-minute sampling missed **2**.
- Cayman Steel Drum: **48/232 (20.7%)** feasible with exact/five-minute departure timing, **0/232** at 15-minute grid. Its only two qualified segments lasted **331 and 423 seconds**.
- China Bo Staff: **24/166 (14.5%)** feasible with exact/five-minute departure timing, **0/166** at 15-minute grid; median qualified segment duration about **601 seconds**.
- Canada Safety Boots: 36/118 exact vs 35/118 at five and fifteen-minute grid.
- China Katana: 232/234 exact vs 231/234 at five and fifteen-minute grid.
- Other items with zero exact 12-hour feasibility under >=30 remain separately categorized; the exact oracle is still hindsight, not a prediction.

**Crucial correction:** Earlier reports calling Steel Drum and Bo Staff absolutely unreachable over the historical test horizon were false due to coarse grid sampling. Their actual V19/V20/V21 historical model success remains 0%. This fix only reveals a *physical* opportunity ceiling; it does not claim a new predictive model success rate. Restock durations of hours remain legitimate and do not cause arrival-score penalties; rare short stock windows warrant finer candidate departure resolution.

The old V19–V21 candidate-grid spacing (V20 five minutes, all-item V21 fifteen minutes) is a plausible missed-opportunity contributor for some low-stock items. This diagnostic does **not** establish that merely making the planner grid finer will improve live success: the forecast still has to know when the stock will be reachable.

## Executable research components committed
- `services/stock_opportunity_geometry.py`: observed qualified-stock intervals, exact hindsight feasible departure, past-resolved-lifetimes-only proposed adaptive candidate departure grid (30,60,120,300 seconds). The hindsight helper is explicitly forbidden as a live prediction input.
- `tests/test_stock_opportunity_geometry.py`: short-stock window, grace, gaps, natural 11-hour restock wait, data validity and grid tests.
- `services/frozen_champion_shadow_v24.py`: new-data, per-item **native V19/V20/V21 frozen-config** dynamic policy replay. Uses original selected config, original native replan/departure settings and corrected direct stock quantity scoring, on shared post-cutoff VM timestamps. Checkpoints item by item; no training or holdout-based model selection.
- `tests/test_frozen_champion_shadow_v24.py`: deterministic matched start and frozen-config guards.

**Local pure-geometry 9-test suite passed**. Repo-native shadow runner tests and replay **have NOT yet been run**; cannot assert a new champion victory or full live readiness.

The full detailed CSV and Python artifacts live in ChatGPT conversation research outputs:
`v24_41_weak_exact_grid_comparison.csv`,
`v24_weak_feasibility_exact.json`,
`v24_departure_grid_sensitivity_all41.json`,
`torn_fren_v24_exact_opportunity_research_2026-10-08.zip`.

## Runbook for native new-VM replay after obtaining frozen inputs
Open Windows venv from `torn-fren`, `git pull --ff-only`. Tests:
```powershell
python -m unittest discover -s tests -p "test_stock_opportunity_geometry.py" -v
python -m unittest discover -s tests -p "test_frozen_champion_shadow_v24.py" -v
```

The following is an **illustrative path setup**: the frozen latest VM DB and the exported candidate registry are **not automatically present on the PC**. Copy the frozen newer snapshot, export `torn_fren_matched_provisional_registry.json` to the indicated location, or adjust paths. Do not point research at an actively updated SQLite file.

```powershell
python -u -m services.frozen_champion_shadow_v24 `
  --db "data\torn-fren-stock-history-latest.db" `
  --registry "data\torn_fren_matched_provisional_registry.json" `
  --v19 "data\all_item_v19\master.json" `
  --v20 "data\weak_item_v20\master.json" `
  --v21 "data\all_item_v21\full_master.json" `
  --cutoff 1791241486 `
  --only "arg:Tear Gas" --only "can:Fire Hydrant" `
  --workers 2 --max-starts 8 --resume
```

The native runner may be compute-heavy: it reproduces each frozen dynamic model's repeated forecast/replan behavior on 12-hour-long observation-complete sessions. Once smoke tests pass, use a **new --output path** to increase --max-starts to 24; checkpoint settings intentionally prevent mixing.

## Outstanding actions
1. Execute and inspect native frozen new-VM replay with genuine shared timestamps, compare V22/V23 alternatives using those same starts and independent additional future periods. Keep previous V19–V21 champions as fallback. 
2. Improve genuinely weak event-driven models (Tear Gas/Fireworks/Katana) and specific ultra-scarce short windows (Steel Drum, Bo Staff), rather than claiming oracle rates.
3. Verify dual-layer website outputs: first qualifying stock, substantial restock, depletion, reachable later restock, estimated departure window, uncalibrated-vs-calibrated confidence and collector heartbeat.
4. Build a production-safe registry and opt-in shadow path with rollback; no automatic public release. 
