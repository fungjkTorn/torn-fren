# TORN Fren — complete handoff for next ChatGPT conversation
**Prepared:** Friday, 2026-10-09. **Project:** fungjkTorn/torn-fren (TORN Projects).

## Message to start the next chat

> Continue the TORN Fren 236-item live-prediction optimization and V38 rollout from this handoff. Work in GitHub branch `research/v38-full-roster-live-prep-20261009`; DO NOT merge into `main`, change production `profitability-v1` without my VM confirmation, touch API credentials, or restart the existing website, bot, poller, or V37 research timer. The primary priority is affordable, resource-bounded background inference for **all 236 catalog items** with a fast, nonblocking website. Target all 22 flower/plushie + Japan Xanax champion models for research collection by Saturday Oct 10 if validated, and an experimental website beta by Wednesday Oct 14 if safe. Inspect GitHub current branch/CI before coding, resolve test failures from concurrent work, then complete missing specialist adapters, scalable scheduler, feature cache, snapshot API, benchmarking, and rollback. Use exact frozen model winners, no lookahead, 5-minute active replanning, 8-hour departure horizon, quantity >=30, +10s grace. Give me concrete VM read-only benchmark commands and gate any deployment on measured VM CPU/RAM and production latency.

## User goals and constraints

- **Near term**: All 22 flower/plushie/Japan Xanax candidates doing genuine private champion inference by **Sat Oct 10, 2026**, so prospective evidence accrues through the weekend.
- **Public beta**: Wednesday **Oct 14**, *experimental only* for technically verified champion predictions, with visible model freshness and quick V2 fallback. Do not require weeks of future accuracy data for a clearly labeled beta, but do not pretend development hit rates are forward-validated.
- **Major new emphasis**: Get **ALL 236** items onto the live prediction system without crashing the existing website. User strongly prefers **$0 new VM costs**, high site responsiveness, and shared/cache-based CPU optimizations rather than increasing VM size. Items with restocks days apart need slower/event-driven or broad monitoring, not fabricated precise arrivals.
- Never overwrite current production web prediction V2; no gameplay automation or external proprietary API violations. No secret values/API keys in GitHub.
- Current 236 stock items already appear in website catalog; primary scaling work is **236 forecast inference/read APIs**, not adding item labels to catalog.
- Preserve five-minute replan for *active/actionable* sessions, eight-hour departure horizon, arrival quantity >=30, +10s grace, leakage-free as-of-source timestamps, stock outage exclusion, only actual source-pinned champions, and distinct `available_stale` V2 evidence.
- User is at work and will run VM commands when home. Do not ask the user to run deployment commands right now or assume hardware capacity.

## Infrastructure and SSH

- Oracle Ubuntu VM: **`ubuntu@150.136.108.146`** / hostname `torn-fren-prod`.
- Exact previously working Windows PowerShell SSH command:
  ```powershell
  ssh -i "C:\Users\fungb\Desktop\.ssh\torn-fren.key" ubuntu@150.136.108.146
  ```
- Production repo: `/opt/torn-fren`; **must remain on branch `profitability-v1`**. Last confirmed HEAD **`062f3a27f33062b50b505f9f492b931e9c654cfd`** (V37).
- Production services `torn-fren-web.service`, `torn-fren-bot.service`, `torn-fren-poller.service`, and `torn-fren-shadow-capture.timer` all **active** in last user verification; `/api/catalog` HTTP **200**.
- Collector database `/opt/torn-fren/data/stock_history.db`; independent research evidence `/var/lib/torn-fren-shadow/capture.db`; services use read-only collector access for inference, never train/write to it. `/etc/torn-fren/private-shadow.env` contains private shadow credentials; **never print, copy or commit it**.
- V37 systemd research service: `deploy/systemd/torn-fren-shadow-capture.service` installed, `CPUQuota=50%`, `MemoryMax=512M`, `TimeoutStartSec=75`, `Nice=15`; one isolated item per tick rotating every five minutes, so each of four items sampled every 20m. Inactive service between ticks is normal (oneshot).
- Timer OnCalendar about `:01/5`; previous duplicated first tick `DUPLICATE_FIVE_MINUTE_SLOT` harmless.
- No actual CPU core count, VM RAM capacity, GPU/device type, current CPU saturation, or catalog p95 has been supplied yet. **Do not promise 236 every five minutes fits**. An NVIDIA GPU is not required for the existing CPU-oriented models.

## Completed production rollout and measured timings

- V33 `9eef543`: started a five-minute research evidence timer.
- V34 `deca908`: standalone read-only forward outcome audit `research/v34_prospective_ops_audit.py`, separate evidence DB, missing-attempt awareness.
- V35 `e9ac999`: naive 4-item private endpoint batch failed on production (Heather recorded; Wolverine/Nessie/Xanax private request timeout), web momentary startup HTTP000 then recovered. Stopped timer for remediation.
- V36 `6b398cbdfd1924d3bb2eea24537ffdbff0c285cd`: research isolated `research/v36_isolated_museum_sampler.py`: no private endpoint/secret, only original V18 subworker with hard 38s limit and separate public V2 `/api/history` timeout. 4 items: Heather and Wolverine native; Nessie and Xanax **baseline-only**. Initial 3s V2 timeout insufficient.
- V37 `062f3a2`: increased public V2 reference HTTP timeout from 3s to **10s**, labels `available_stale` vs fresh; 32 CI tests. Current production.
- User ran original V18 champion Heather manual `RECORDED`, 7.448s, `champion_executed:true`, V2 `available_stale`.
- Wolverine manual `RECORDED`, 9.310s, `champion_executed:true`, V2 `warming`.
- After installing updated systemd unit, first one-shot Xanax baseline `RECORDED` in ~4s and public web/bot/poller healthy.
- Overnight production rotation logs show Heather and Wolverine `RESEARCH_PROPOSAL_ONLY`, Nessie/Xanax `SPECIALIST_NOT_INTEGRATED`, V2 `warming` or `available_stale`. Wolverine ~13s under systemd. All services healthy as of Friday morning; user to recheck.
- **Live predictive accuracy remains unproven**. Historical development wins are not prospective proof; 12 hours of collection only gives limited independent restock windows. V34 scorer requires honest resolution / missed attempt handling.

## Crucial question: why V18 champion when development is in the V30s?

There are **two independent numbering schemes**:
1. **V18/V19/V20/V21** names identify research **model generations/algorithm families**. Different algorithms competed in tournaments; the winning method for a specific item may be older V18 even though the entire infrastructure is newer.
2. **V33–V38** refer to the **collector/deployment/research evidence iteration** and can run winners from any algorithm family.

The latest provisional 21-item handoff `research/all_236_champions_v26.json` selected **original V18 for 10 flowers/plushies**, including Heather V18 dyn3 and Wolverine Plushie V18 dyn8. These are the *selected historical tournament winners*, NOT fallback to outdated production app version. Re-test prospectively. Other items choose V19, V20, or seven bespoke plushie winners. Lowercase `v19/v20/v21` for all-item generic inventory refer to tournament generations in `services/frozen_candidate_worker_v31.py` and require **exact source-pinned configs**, not mapping by filename alone.

## Full research registry numbers (verified from repository)

`research/all_236_champions_v26.json` has **236** provisional entries:
- 21 flowers/plushies = 10 **V18**, 3 **V19**, 1 **V20**, 7 **bespoke specialist**.
- 1 Japan Xanax specialist = V8 leading recency-weighted Ridge candidate (development only).
- Other 214 = **132 generic candidates** (52 v19, 10 v20, 70 v21), plus **82 baseline/review classes** (30 `depart_now_baseline`, 24 `best_effort_sparse`, 27 `quantity_below_30`, 1 `quantity_requalified_needs_new_tournament`).
- Total **236**. For slow rare restocks, retain broad next-watch windows or explicit insufficient-evidence state; no forced <8h departure when next stock likely days away.

**The 22 chosen models:**

| Key | Frozen generation / winner |
|---|---|
| arg:Ceibo Flower | V18 dyn3 |
| arg:Monkey Plushie | 2-day online template expert selector |
| can:Crocus | V18 dyn5 |
| can:Wolverine Plushie | V18 dyn8 |
| cay:Banana Orchid | V18 dyn7 |
| cay:Stingray Plushie | V18 dyn7 |
| chi:Panda Plushie | ExtraTrees two-expert selector |
| chi:Peony | V20 traj12 |
| haw:Orchid | V18 dyn3 |
| jap:Cherry Blossom | V19 dyn2 |
| jap:Xanax | Japan V8 specialist, distinct model |
| mex:Dahlia | V18 dyn2 |
| mex:Jaguar Plushie | V18 dyn3 |
| sou:African Violet | V19 dyn7 |
| sou:Lion Plushie | logistic two-expert selector |
| swi:Chamois Plushie | 3-day online template selector |
| swi:Edelweiss | V19 dyn9 |
| uae:Camel Plushie | 24-template probability selector |
| uae:Tribulus Omanense | V18 dyn3 |
| uni:Heather | V18 dyn3 |
| uni:Nessie Plushie | recent-phase template, 2h lookback, 1-day lag, 1h shift, fit .5 |
| uni:Red Fox Plushie | global-regime analog k18/w.5 |

Historically trained specialist files under `research/plushie_champions/`: `recent_phase_select.py`, `rf_localgrid.py`, `lion_pair_selector_ml.py`, `panda_pair_selector_ml.py`, `checkpoint4_online_selector.py`, `camel_fast_selector.py`, `common.py`; they are replay/historical code, **not by themselves deployable live services**.

Japan V8 development checkpoint `research/japan_xanax_v8_regime_adaptive_checkpoint_2026-10-07.md`: leading recent-regime rolling standardized Ridge, last 60 resolved samples, alpha 0.3, half-life 40; most recent 21 inspected development cases exact 16/21 = 76.2%, +3min 17/21 = 81%; **not pristine validation**, full-coverage older regime often only ~40–50% exact. Don't claim 76% in production; freeze/reproduce exact implementation in causal live adapter.

## GitHub development completed during this chat

Development research branch **`research/v38-full-roster-live-prep-20261009`** branched from V37 `062f3a2`. This branch is NOT production and must not be merged into production until verified.

Files authored:
- `research/v38_roster.json`: frozen 22 item/config registry, no fake promotion.
- `services/private_v18_champion_worker_v35.py`: opt-in `approved_configs` parameter while preserving existing two-item CLI allowlist.
- `research/v38_v18_single_tick.py`: exact original frozen V18 execution for **all 10 V18** flowers/plushies.
- `research/v38_v19_single_tick.py`: exact original V19 for **3 selected flowers**.
- `tests/test_v38_frozen_v18_rollout.py` and `tests/test_v38_frozen_v19_rollout.py`: synth read-only stock DB, future data rejection, source unchanged and recommended departure bounds. Both passed initial CI.
- `research/plushie_champions/*`: copied original specialist research bundle from `research/plushie-champions-20261008` branch with exact configs, numpy/scikit-learn requirements (research only).
- `research/v38_readonly_resource_probe.py`: sequential bounded read-only VM per-item runtime probe, does NOT fetch V2 baseline or write research/collector DB; `--all` opt-in. Representative source-pinned model tests.
- `tests/test_v38_resource_probe.py`: enforced benchmark budget, no HTTP, no collector write. Updated after expanding roster.
- `.github/workflows/v38-research-adapters.yml`: tests new adapters and existing V35/V36 regression.
- `docs/v38_scale_to_236_plan.md`: full resource-optimized architecture and rollout.
- Additional current-branch development has **Nessie live**, **Camel live**, and **Peony V20** wrappers (`research/v38_nessie_single_tick.py`, `research/v38_camel_single_tick.py`, `research/v38_peony_single_tick.py`), and restored original `services/plushie_flower_dynamic_planner_v20.py`. The source-pinned benchmark `ALL` currently supports **16 items**, but none deployed; only CI/synthetic proof. The branch is evolving; check HEAD and CI again.
- Earlier CI passed 10+3 adapters and original V35/V36 regression. Expanding 13->16 temporarily broke the static `tests/test_v38_resource_probe.py` count assertions; fixed by testing dynamic `len(PROBES)` and >=13 source-pinned count at commit `f207438a993a0eef4c3942c31381d233a3220b6e`, and CI run `37951322524` concluded **success**. Later document commits may trigger new checks; check latest before claiming green.

**No V38 code has been installed on the VM.** Research collector still V37.

## Why 236 will be hard if naive — verified code hotspots

1. `services/private_v18_champion_worker_v35.py` original V18 live `single_tick` reads **all history** and rebuilds cycles/features/points per invocation. Its inner distance ranking already optimized once per query; focus on preventing repeated historical preparation, incremental append and caching by item/model/source watermark.
2. `web/app.py:/api/history` includes stock history analysis, profitability enrichment, background V2, and forecasting history. `_get_prediction_nonblocking` queues up to two background V2 workers and returns cached `prediction_v2_stale` under load. Heavy *on-demand* V2 computations should not be multiplied by 236 hot calls.
3. `web/app.py:/api/catalog` calls `history_service.get_stock_catalog`, then profitability `enrich_items_with_profitability` across items. Catalog currently exists; optimize repeated full-query latest stock and caching as measured.
4. `history_service.get_stock_catalog` uses aggregate max timestamp over stock_history, repeated per request. `get_item_history_since` calls `_get_all_item_rows_with_source` (reads all recorded rows for an item), then filters Python-side; a bounded SQL approach plus neighboring rows to preserve bounce suppression could improve site performance. Need output-parity tests.
5. Collector uses WAL and index `(country,item_name,timestamp)`; `LOWER(item_name)` equality may not fully use it; **EXPLAIN QUERY PLAN** and test before index changes.
6. **236*288 = 67,968 five-minute item-slots/day**, not necessarily 67,968 high-cost computations. Need bounded decision/evidence retention and independent completed-cycle outcomes, not giant unbounded tick rows.
7. Website read path should consume **latest_predictions** snapshot table (cheap per-item indexed read) with `generated_at`, `stock_as_of`, `valid_until`, candidate generation/config and honest abstention/fallback, not invoke inference during HTTP requests.
8. Small bounded process pool, queue priorities, hard CPU/RAM/time limits and active-trip/near-departure first. Rare items days between stock: keep monitoring source every poll, but recalc model on meaningful change, approaching window, or slower watch cadence; preserve 5-minute **active** replanning requirement. Don't present stale predictions as fresh.
9. Avoid more external Torn API traffic, don't modify gameplay, don't run background workers on main FastAPI threads. Keep rollbacks immediate.
10. Don't schedule all 236 until read-only representative benchmarks and actual Oracle VM hardware/cgroup specs; user doesn't want to pay for new server, and may already have sufficient compute after caching.

## Immediate next tasks — prioritize

1. Check current V38 GitHub branch and CI; resolve any concurrent-modification tests without reverting working specialist code. **Never merge main.**
2. Complete remaining **Red Fox, Lion, Panda, Monkey, Chamois, Japan Xanax** single-tick adapters with exact winning configs, matching original causal replay outputs. There may be ongoing parallel changes; inspect live tree.
3. Add safe 22-model backend scheduler that can emit per-item completed/missed/timeout/late states, without 22 expensive on-demand V2 history calls and without defeating 5-minute active planning or starving public service.
4. Plan true 236 roster by the 132 generic candidates + 82 baseline/review; source-pinned source verification for each, event-driven cold-tier evaluations, latest predictions table; do not claim all 236 full champions when many are classified fallback.
5. Generate VM profiling commands; after user returns to PC run `nproc`, `lscpu`, `free -h`, `uptime`, `vmstat 1 5`, disk usage, `ps`, systemd limits and 10 sequential `curl -w '%{time_total}' http://127.0.0.1:8000/api/catalog`. Run isolated `research.v38_readonly_resource_probe` only after the branch is fetched separately / fast-forward gating, and under conservative nice/timeout.
6. Finish multi-item performance and synthetic parity tests; then stage into separate canary service with `PrivateTmp`, `ProtectSystem`, process resource caps. Observe website p95 and site/bot/poller health. Never replace existing timer blindly.
7. By Wed experimental website feature-flagged latest-snapshot predictions with V2 fallback and model provenance. Future forward scoring by unique resolved restocks, no false precision.

## Last user status and readiness

As of the latest submitted production output: site, bot, poller, research timer `active`, website `HTTP 200`, live Git `062f3a2`; overnight four-item rotation `RECORDED`. User is away from PC but plans to return and provide hardware diagnostics. Needs **full SSH command including key file**, not IP-only. Handoff requested because conversation length is exhausted.

**Links**
- Repo: https://github.com/fungjkTorn/torn-fren
- Production-safe V37 hotfix PR: https://github.com/fungjkTorn/torn-fren/pull/14
- Research V38 branch: https://github.com/fungjkTorn/torn-fren/tree/research/v38-full-roster-live-prep-20261009
- Scale plan: `docs/v38_scale_to_236_plan.md` on V38 branch.
