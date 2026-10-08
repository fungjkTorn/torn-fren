# Torn Fren V24 — exact opportunity scorer and frozen replay handoff (2026-10-08)

**Checkpoint complete for V24 implementation and local geometry verification.** The frozen V19/V20/V21 champion replay runner is committed, but its full in-repository native execution on the newer VM snapshot is **NOT YET RUN**. No live deployment, model promotion, or changes to the bot/website/collector.

## Confirmed results (frozen original historical DB)
Original snapshot SHA256: `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`.
41 selected weak items, 5,631 historical fully observable decision sessions with >=30 items on landing or +10 seconds, 12-hour departure search horizon.
- 15-minute departure grid: 2,594/5,631 sessions had at least one reachable qualified stock opportunity.
- 5-minute grid: 2,666/5,631.
- Exact-event geometry: 2,668/5,631.
- Cayman Steel Drum: 48/232 reachable sessions by exact windows versus zero on 15-minute grid; 2 very short observed stock segments (331s, 423s).
- China Bo Staff: 24/166 exact reachable sessions versus zero on 15-minute grid.
- This is a **hindsight feasibility oracle** and emphatically NOT 2,668 real model successes. Fixed coarse grids had caused materially incorrect 'unreachable' claims. Natural long restock waits are never penalized just for being hours long.

## GitHub files and safety changes
- `services/stock_opportunity_geometry.py`: pure hindsight-only interval windows and earliest viable departure / grace / gap checking; candidate departure grid suggested *only* from past resolved lifetime data.
- `tests/test_stock_opportunity_geometry.py`: unit test coverage for short windows, gap censoring, 10s grace, natural 11h restock waits and invalid input.
- `services/frozen_champion_shadow_v24.py`: frozen config V19/V20/V21 native dynamic planner replays on the same newer starting timestamps; records per-version paired results and saves checkpoint per item.
- `tests/test_frozen_champion_shadow_v24.py`: config-freezing, pairing, and explicit SQLite read-only guard regression.
- Critical fix in runner: the shared `history_service.init_db()` normally performs `PRAGMA journal_mode=WAL` and schema initialization during reads. For shadow replay, it is overridden and every history connection is opened `mode=ro`, `query_only=ON` to guarantee no writes even to frozen copies.
- Runner now rejects DB snapshots with wrong SHA256, defaults expected newer VM hash `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`, binds resume settings to database *and registry* digests, does not overwrite existing results, and requires a copy of DB rather than the collector's live writer DB.
- Newer VM DB exact frozen SHA256 was independently verified in local research runtime: `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`.

## Local test evidence
The archived V24 geometry implementation completed its 9 unit tests. Two additional independent local checks were run:
1. 1,500 seeded randomized no-gap windows compared exact/grid geometry against an exhaustive one-second brute-force candidate scan: all matched.
2. SQLite read-only connection test read existing stock and rejected both INSERT and CREATE; before/after file digest was unchanged.
Result: **11 local tests PASS**. These were run on the archived local research mirrors and check the same geometry and RO helper logic. The GitHub repository's full unit suite and full native replay were **not run locally in the GitHub source tree**; require an on-PC run for final acceptance.

## Executing native newer VM shadow replay on project PC
Use a **copy** of `torn-fren-stock-history-latest.db` with the expected hash, and download/copy the 236-entry research JSON `torn_fren_matched_provisional_registry.json` into your project `data` folder. Do not assume they are already on PC. Open venv and pull the latest repo.

```powershell
cd C:\Users\fungb\Desktop\torn-fren
.\venv\Scripts\Activate.ps1
git pull --ff-only
python -m unittest discover -s tests -p "test_stock_opportunity_geometry.py" -v
python -m unittest discover -s tests -p "test_frozen_champion_shadow_v24.py" -v

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

Repo V24 shadow default output: `data\frozen_champion_v24\new_vm_master.json`. Changing max-starts for an expanded test changes frozen settings. Use `--output "data\frozen_champion_v24\new_vm_24starts.json"` for an expanded `--max-starts 24` run. No model versions reselected, but the policy can replan causally as new observations arrive. 12h full horizon shared for fairness; V19 native policy itself retains its own 6h limit.

## Key next-chat requirements
1. Run native V24 replay smoke test on project PC and upload saved results; do **not** invent native head-to-head results until verified.
2. Run broader same-session V19/V20/V21 versus frozen V22/V23 on newer VM; user wants strong and weak items improved, especially <50%. Previous V22/V23 numbers against depart-now are not proof of superiority over champions.
3. Separate *next qualifying availability* from *major restock event*. The website needs next drop estimate/window, confidence, current stock/survival, reachable departure and arrival times, second reachable drop. Restock point/window MAE and calibrated confidence were **not established** by V19–V21 arrival metrics.
4. Preserve specialist Japan/UK/Canada Xanax research and parallel flower/plushie improvements from the other chat. Keep V2 fallback, data freshness/heartbeat, shadow flags and rollback before live.
5. No generic penalty for necessary 11h restock waits. Better prediction is accurate stocked arrival, not shorter wait per se. Separate avoidable skipped opportunities with an oracle ONLY for hindsight.

**Final state:** V24 exact-window scoring module + tests + read-only guarded frozen-champion replay have been committed; V24 exact feasibility research verified. Native project integration/replay remains an explicit acceptance gate, not a completed result.
