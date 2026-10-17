# V38 — Friday research-to-live handoff (no automatic deployment)

**Production is intentionally unchanged:** branch `profitability-v1` in
`/opt/torn-fren` at V37 commit `062f3a2`, existing `torn-fren-shadow-capture.timer`
continues its isolated four-item rotation. V2 web, Discord bot and poller are
not modified, and V38 is not connected to public routing.

## Prepared roster — 16 genuine single-tick models

From the frozen 22-item `research/v38_roster.json`:
- 10 original V18 winners, exact source configurations, shared verified engine
  (`research/v38_v18_single_tick.py`).
- 3 original V19 winners, original V19 source configurations
  (`research/v38_v19_single_tick.py`).
- China Peony: source-restored original V20 `traj12` model
  (`research/v38_peony_single_tick.py`).
- UK Nessie Plushie: 1-day phase-template winner with 2h lookback / +/-1h
  shift / .5 min fit, reusing the original TemplatePlanner
  (`research/v38_nessie_single_tick.py`).
- UAE Camel Plushie: original 24-template bank and highest current plan
  probability selection (`research/v38_camel_single_tick.py`).

**Source correction:** The imported historical TemplatePlanner had a
`TypeError` in its group tie-break (`-z[0]` negated a tuple). V38 corrects
this to `-z[0][0]` (the intended numeric earliest-delay tie-break) and tests
real inference. That is one explicitly documented source bug fix, not an
unreported change to winning hyperparameters.

## Remaining six specialists

- `uni:Red Fox Plushie`: global-regime analog; shared cross-item features
  need a bounded cached inference implementation.
- `sou:Lion Plushie`: LogisticRegression selector trained only on resolved
  historical opportunity labels as-of prediction time.
- `chi:Panda Plushie`: ExtraTrees selector, same causal/frozen training gate.
- `arg:Monkey Plushie`: 24-template bank with prior **resolved** two-day
  expert-performance selection. Do not substitute simple best-current expert.
- `swi:Chamois Plushie`: same 24 bank, prior **resolved** three-day window.
- `jap:Xanax`: V8 weighted rolling Ridge timing specialist, a separate regime
  and outcome definition. Do not represent a generic algorithm as the V8 winner.

These six remain pending real live integration; `research/plushie_champions/`
contains the untouched champion replay sources (except the documented tuple
tie-break correction). No research-only scores become calibrated probabilities.

## VM check — read-only, separate worktree, NO switch to production branch

**First:** inspect CPU, RAM, and production health; keep the installed timer
running and do not restart public services. Then, from production checkout:

```bash
cd /opt/torn-fren
git fetch origin research/v38-full-roster-live-prep-20261009
git worktree add --detach /home/ubuntu/torn-fren-v38 FETCH_HEAD
cd /home/ubuntu/torn-fren-v38

# Isolated dependency environment; no application-wide pip install.
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install 'numpy>=2.0'

# Four original family examples + Nessie; sequential, never calls website.
nice -n 15 timeout 110s .venv/bin/python -m \
  research.v38_readonly_resource_probe \
  --db /opt/torn-fren/data/stock_history.db \
  --timeout 20 --budget 100
```

The default probe benchmarks five representative candidates and **does not
write the stock DB, modify public routing, or query V2**. Report each model's
`elapsed_seconds` and `status`. Only if these look safe, separately run
`--all --budget 240 --timeout 25` to benchmark all 16 one by one; that is
**not** the production five-minute scheduler. Apply additional OS resource
limits if hardware metrics warrant.

Nessie and Camel require NumPy in the isolated research venv. Other
specialists may later need scikit-learn; DO NOT install them into the public
web/bot Python environment just to complete the research tests.

## Live switch plan

1. Record actual per-model VM latency and peak memory with five-item probe.
2. Build an isolated worker pool and serialized read-only output/cache; the
   website reads only precomputed results. Keep bounded CPU and RAM so the
   website/stock poller retain priority.
3. Incorporate each model with source identity, freshness, horizon, quantity
   threshold, 5-minute replan, and failure labels; catch all overdue/failed
   scheduling attempts rather than silently dropping them.
4. Gate full-roster rotation behind a separate systemd service + timer;
   do not change the current four-item V37 research timer until replacement
   passes end-to-end tests and production health checks.
5. Aim for all 22 source-accurate champions shadowing by Saturday Oct 10,
   with failed specialists explicitly pending (never masquerade as executed).
6. Target public **experimental beta** by Wednesday Oct 14 only after
   stable production headroom, clear unverified accuracy labels, and fast
   item-specific V2 fallback/rollback.

For the remaining 214 items beyond this 22-item pilot, use the all-236 registry
to group V19/V20/V21 native families, sparse/never-30 categories, and items
with rare multiday restocks. High-frequency fast movers can be recomputed
every 5 minutes; rare items retain stock monitoring while calculation cadence
and uncertainty reflect genuine observed restock frequency.

**Caution:** CI validates original-engine execution on synthetic stock, not
real VM timing, true forward arrival success, or suitability for public use.
