# TORN Fren V38: scaling 22 specialist candidates to 236 catalog items

**Created:** 2026-10-09. **Status:** architecture/design, not a deployed scheduler.

## Verified repository facts

- `research/all_236_champions_v26.json` lists **236** provisional items:
  - **21** flowers and plushies: 10 `V18`, 3 `V19`, 1 `V20`, and 7 unique specialist families.
  - **1** Japan Xanax, separately classified `japan_xanax_specialist`.
  - **214** other items: 52 `v19`, 10 `v20`, 70 `v21`, 30 `depart_now_baseline`, 24 `best_effort_sparse`, 27 `quantity_below_30`, and 1 quantity-requalified item requiring a new tournament.
- The registry is explicitly **provisional development evidence**, not calibrated future success probability. Generic lowercase `v19/v20/v21` are the all-item tournament families, not the same thing as the V18/V19/V20 file naming for flower/plushie tournament implementations.
- The website's `/api/catalog` already returns the stock catalog from `get_stock_catalog()`, and enriches its items with profitability. The problem to solve is **236 cheap, timely model predictions**, not making 236 names visible.
- `/api/history` calls both background stock analysis and `_get_prediction_nonblocking`, which has a **two-worker background model executor** and returns warming/stale results under load. The V37 research sampler sometimes gets `available_stale`. **Do not warm 236 V2 forecasts by issuing 236 simultaneous HTTP history requests.**
- `get_stock_catalog()` selects latest rows using aggregate `MAX(timestamp)` over historical records each call. `get_item_history_since()` currently reads all historical rows for a requested item and filters them in Python. Both merit profiling/optimization, with output-parity tests, if site latency degrades.
- `stock_history` uses SQLite WAL and basic indexes for country, item, timestamp; a case-normalized lookup uses `LOWER(item_name)`, so confirm index utilization using `EXPLAIN QUERY PLAN` before adding indexes or migrating large databases.
- Existing V18 live worker repeatedly reads full item history, rebuilds validated cycles/features/historical points, then evaluates all departure options for each tick. Historical neighbor sorting has already been optimized to **once per query**, but reloading all rows every tick is still repeated work.
- Deployed isolation service has CPU quota `CPUQuota=50%`, `MemoryMax=512M`, `TimeoutStartSec=75`. Two V18 pilots have completed under VM isolation; no hardware capacity numbers have been supplied yet.

## Target architecture — keep site and collector protected

```text
Existing 30s Torn stock poller -> stock_history SQLite (collector remains sole writer)
                                  |
                                  v (read-only change observer / incremental watermark)
                latest-item state + new restock/depletion events
                                  |
                     +------------+-------------+
                     |                          |
             background feature cache   research evidence/scoring queue
             keyed item/model/source            |
                     |                          |
              five-minute budgeted planner <----+
                   |      |      |
        active actionable / near departure / cold & rare items
                   |
             small capped process pool
             CPU+RAM+wall-time budget, bounded concurrency
                   |
           separate latest_predictions SQLite
            immutable model version/config;
            computed_at, stock_as_of, expires_at;
            abstention, error, causal provenance
                   |
          fast read-only website endpoint
                   |
        catalog/history pages, Discord bot
          no synchronous champion compute
```

### Model execution policies

1. Preserve real five-minute replanning for **active travel sessions** and **actionable departures**. Don't silently relabel a one-hour-old recommendation as fresh.
2. Restock intervals of days are not an argument for recalculating everything every five minutes. For rare items outside the eight-hour actionable horizon, update on observed stock changes, material forecast expiry, model changes, or a capped watch cadence. Show broad watch windows / insufficient evidence, not invented minute-precision departure advice.
3. Never make the production website compute the 236 champions when users open a page. Precompute a latest prediction snapshot; serve a fast indexed read with explicit `as_of`, `valid_until`, `model_family`, and `status`. A worker failure must not block site traffic.
4. Separate **stock freshness**, **model freshness**, and **forecast accuracy**. Store `V2 available_stale` distinctly from a recomputed baseline. Never claim backtest hit rates are calibrated per-trip probabilities.
5. Preserve +10s grace, quantity >=30 at arrival, 8h max planning, 5m replanning for active plans, known collection gaps, no lookahead, and no automated gameplay.
6. Group related targets by original engine/model family; reuse immutable histories and features per key + watermark. Rebuild only when new collector rows impact a model. Cache invalidation on source updates, model changes, gaps, or time-bound feature changes.
7. Start with **one** bounded worker, benchmark, then add workers only if VM cores/RAM and 99th-percentile website latency support them. The 50%-CPU unit is a safety limit, **not** proof 236 models fit.
8. Budget overall resource use per tick. Priority: user actively waiting to depart > departure within horizon > affected-by-new-stock event > other recently actionable > passive rare/cold monitoring. Record deferred/rejected workloads honestly; don't mark them `RECORDED` with fake champion data.
9. Retain one latest row per item for site reads, plus append-only prospective evidence only as needed for audit/scoring. Use TTL/partition/archival for high-volume ticks; **236 x 288 = 67,968 item-ticks/day** at five-minute cadence before deduplication. Avoid unbounded web cache and large per-request historical series.
10. Test the biggest SQL queries first. Consider a latest-item materialized table maintained by the existing collector or a read-only sidecar; measure before migrating. Add selective indexes based on actual `EXPLAIN QUERY PLAN`. Never add migrations to live DB without backup and integrity checks.

### Website latency targets (engineering objectives, not measurements)

- `/api/catalog` typical cached requests <0.25s, p95 <1s.
- Latest prediction read typical <0.1s.
- No synchronous site wait for champion inference; return `warming`, `stale`, `unavailable`, or last safe value as appropriate.
- Production web, poller, bot remain active and responsive during 236-item stress testing.
- Benchmark CPU usage, RSS peak, per-family seconds, p95 page response, SSD size, DB read lock, and missed scheduler ticks.

### Deployment stages

A. **Current production unchanged:** V37 four-item research rotation; *real* V18 Heather and Wolverine, baseline-only Nessie and Japan Xanax.

B. **Research-only V38 branch:** 13 original source-pinned V18/V19 live adapters and additional specialist adapters are being developed/tested without changing site code; preserve the older V35 two-item allowlist at its CLI. A bounded read-only sequential resource probe gathers representative VM timings.

C. **By Sat Oct 10 desired:** 22-item research roster running with **actual source-pinned champions wherever technically validated**. No silently substituted models; missing specialists remain explicitly baseline-only. Run VM measurements before enabling any 22-item scheduler. No assumption that 22 items can be serially recomputed inside 300s.

D. **By Wed Oct 14 proposed public beta:** Only technically verified champion snapshots via feature-gated, read-only website presentation with V2 fallback; users see experimental label and freshness. No claim of validated future hit rate after 2-4 days.

E. **214 remaining items:** bulk-register the 132 existing generic V19/V20/V21 provisional candidates in grouped model-family workers; do not train 132 separate models. Handle 82 classified baseline/sparse/quantity-unqualified items with honest statuses and specialized re-evaluation. Rare-restock forecasts may be broad/non-actionable.

F. **Prospective accuracy:** score independently resolved stock windows, plus missed/fail/late/deferred coverage, fresh vs stale V2 comparisons, and Wilson intervals. Do not count 288 consecutive predictions as 288 independent restocks.

### VM profiling commands

Connect from Windows PowerShell:

```powershell
ssh -i "C:\Users\fungb\Desktop\.ssh\torn-fren.key" ubuntu@150.136.108.146
```

Read-only diagnostic:

```bash
cd /opt/torn-fren
nproc
lscpu
free -h
uptime
vmstat 1 5
df -h / /opt/torn-fren
ps -eo pid,comm,%cpu,%mem,rss --sort=-%cpu | head -20
command -v nvidia-smi >/dev/null && nvidia-smi || echo "No NVIDIA device/tool detected"
command -v lspci >/dev/null && lspci | grep -Ei 'vga|3d|display' || true
systemctl show torn-fren-shadow-capture.service -p CPUQuotaPerSecUSec -p MemoryMax -p TimeoutStartUSec
systemctl is-active torn-fren-web.service torn-fren-bot.service torn-fren-poller.service torn-fren-shadow-capture.timer
for i in 1 2 3 4 5; do curl -sS --max-time 15 -o /dev/null -w '%{http_code} %{time_total}s\n' http://127.0.0.1:8000/api/catalog; done
```

**Do not spend on a GPU:** model families are CPU-oriented; we lack measured proof that hardware needs upgrading. Avoid changes to the currently running stock collector and public V2 before bench/rollback readiness.
