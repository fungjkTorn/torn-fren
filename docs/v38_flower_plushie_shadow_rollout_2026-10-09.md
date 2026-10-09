# Flower/plushie V38 progressive shadow rollout — 2026-10-09

The October 9 V37 collector-safety release `a93879d` is running on the
Oracle 2-OCPU/12GiB VM. Its user-measured post-deploy window showed
**30 successful polls in 15 minutes**, last heartbeat 19s, **6 FDs** (vs
681), all 2/2 live V18 pilot champions executed, website healthy and
recovery queue empty. No reason to modify the production collector again.

## Exactly which models are ready

**11 flowers** plus **5 plushies** have isolated, source-pinned,
research-only single-tick adapters, or 16 of 21 target items. These
are *executable research adapters*, **not** 16 proven live winners.

Remaining plushies:
- **Red Fox** original k18/global-regime 0.5 has a separate candidate
  `research.v38_red_fox_single_tick` but is excluded from default
  runtime/scheduler because its original cross-plushie feature builder
  needs cold VM resource and causal parity checks. Do not silently add
  it as a 17th approved model.
- **Monkey**: historical `checkpoint4_online_selector.py` winner uses
  2-day resolved-outcome expert weights across 24 template experts.
- **Chamois**: same expert bank with 3-day resolved-outcome window.
  A live wrapper must use *only as-of-time resolved* historical outcomes,
  not a full offline replay with later data.
- **Panda**: ExtraTrees two-expert classifier needs causal historical
  feature preparation, matching exact original 300 trees/depth3/
  leaf3/balanced/random_state2 trained only on previously resolved
  cases, otherwise abstain. Synthetic-parity and no-lookahead tests.
- **Lion**: original balanced logistic two-expert selector with
  exact source-pinned k14/.35 vs k18/.50 configuration.
- **Japan Xanax** is the separate 22nd model, not part of 21 flowers/
  plushies; do not count it as ready.

## Fastest safe staged schedule (estimates, contingent on measurements)

- **Within 24h**: isolate an initial 5-item read-only probe and, *only
  if website/poller/bot stay healthy*, optionally enable a separate
  PRIVATE, rate-limited research canary. Not yet public.
- **Within 1–2 days**: increase to all 16 executable models **only if**
  measured aggregate wall time, CPU budget and missing-item abstentions
  demonstrate that five-minute active replanning is sustainable. The
  current serial runner defaults to only 4 jobs per 5m tick; it does
  NOT satisfy all-16 concurrent cadence without a measured schedule
  change, and deferred runs must be explicit.
- **Next 2–4 days, not guaranteed**: integrate Red Fox with validated
  causal/reference coverage and the four missing plushie selectors,
  including exact winning training and performance parity. Preserve
  `INSUFFICIENT_EVIDENCE` rather than substitute V2 and call it the
  specialist. Their original replay code is *not* a live adapter.
- **Website beta** only after private evidence, healthy production
  latency, and source-pinned model provenance. The public V2 route
  must remain the default, with expired/unintegrated V38 results
  explicitly falling back.

## Correct source-freshness rule (fixed on research branch)

`stock_history` is change-only; an item may have no fresh
`stock_history.timestamp` for hours despite 30s collector successes.
`research.v38_incremental_observer` now obtains last successful
`poll_heartbeats` timestamp separately and
`research.v38_budgeted_runner` refuses execution when that heartbeat
is missing/stale (>180s)/future. It records verified heartbeat as
`stock_as_of` for prediction freshness, NOT the latest item change
timestamp. A successful heartbeat and no changed item state is
legitimate fresh stock. Regression checks exercise this case. Production
V37 is unchanged.

## Isolated, **read-only** VM benchmark setup (do not deploy V38)

After CI is green and only when convenient, from the already connected
Oracle VM's `ubuntu` account. This creates a separate detached worktree;
it doesn't change production `profitability-v1`, systemd, database
observations, bot or public API.

```bash
set -e
cd /opt/torn-fren
git fetch origin research/v38-full-roster-live-prep-20261009
git worktree add --detach /home/ubuntu/torn-fren-v38-probe FETCH_HEAD
cd /home/ubuntu/torn-fren-v38-probe
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r research/plushie_champions/requirements-research.txt
echo "==== FIRST: FAILURE-CLOSED LIVE ADMISSION CHECK ===="
.venv/bin/python -m research.v38_shadow_canary_preflight \
    --db /opt/torn-fren/data/stock_history.db
```

**STOP if** `status` is `DEFER_PROBE`, disk/RAM is strained, or
`source.status` isn't `FRESH`. `READY_FOR_BOUNDED_READONLY_PROBE`
means only the *next benchmark* is admissible, NOT approval to enable
an ongoing timer.

Initial 5-model **one-off** workload, separately authorized:

```bash
cd /home/ubuntu/torn-fren-v38-probe
nice -n 15 timeout 120s .venv/bin/python \
    -m research.v38_readonly_resource_probe \
    --db /opt/torn-fren/data/stock_history.db \
    --timeout 15 --budget 95
```

Watch heartbeat, first 5 model statuses, wall-time, website p95, and
poller FDs *before and after* the test. Any timeout, missing successful
heartbeat or site regression means do not start any new V38 timers.
Run original 4-item V37 capture untouched. No subprocess or HTTP calls
in the preflight; benchmark reads stock in mode=ro.

## Release acceptance gates

1. Every champion offered by the canary must execute its **original**
   version/config; synthetic temporal no-lookahead parity and
   full gap/future-stock rejection verified.
2. Baseline 30 successful heartbeats/15m and >=90 minutes forward
   collection during canary; freshness <180s; no new outage.
3. Poller FD count stays bounded near post-fix 3–6, not hundreds.
4. Resource guard load1<=0.8x available CPU slots, per-subprocess
   budget measured; no repeated public `/api/catalog` p95 >1s caused
   by research.
5. Every five-minute slot logs scheduled / executed / deferred / timeout
   for **all eligible** candidates; do not infer overall hit rate from
   attempts that were skipped, and never score the same resolved restock
   multiple times as independent trials.
6. Research sidecar separate from `/var/lib/torn-fren` collector DB
   and `/var/lib/torn-fren-shadow` V37 evidence; no gameplay automation.
7. Public routing, production poller and original shadow timer remain
   untouched until separate explicit release approval.

Current checkpoint: first five isolated tests can start as soon as
worktree and Python dependencies are ready and host admission is green.
No new V38 timers or public pages are enabled by this document.
