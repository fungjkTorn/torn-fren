# V39 CPU scalability: controlled V37-derived production upgrade

2026-10-09. **Never merge research/v38 directly into production.**
This branch descends from V37 safety release
`a93879d42808c7a2f7485b88b6393056d87d01c9`.

## Measured prior to optimization

Oracle VM: 2 OCPU / ~11GiB RAM; ~10GiB available.
Load ~3.7–4.4; 97–100% CPU user utilization, near-zero I/O wait.
Main poller PID 3860 consumed **94.1% one CPU average** with 7+
Python threads (regular model auditing/seeding); Uvicorn PID 760 ~58.4%.
Collector itself remained healthy at 30 successful heartbeats/15m,
9–26sec age, and 3–6 FDs after V37 fix.

Those are **operator-collected pre-release statistics**, not guaranteed
post-V39 measurements. Goal: free CPU for 21 flower/plushie models +
Japan Xanax first, then 236 total-item coverage.

## Exact production changes (no V38 models deployed)

1. The **poller** now only fetches, persists stock observations,
   records heartbeats/recovery incidents and sleeps to 30sec cadence.
   No `threading.Thread` for V2 model selection, forecast auditing or
   startup seeding. This removes costly model work from the collector.
2. Each changed quantity row atomically upserts a durable audit job
   into `routine_audit_jobs_v39` *within the same SQLite transaction*.
   Price-only changes don't queue model audits. Jobs are keyed by
   country/item, generation counters prevent lost updates when a stock
   change arrives while the prior audit executes. Crashed/slow jobs
   lease-expire and retry with bounded exponential backoff.
3. A new per-minute systemd oneshot drains up to 4 jobs or 40 seconds
   per invocation at **35% of one CPU**, nice 17, RAM max 768MiB,
   hard start timeout 125s. It preserves old baseline audits,
   resolved future forecasts, and Japan Xanax shadow auditing.
   It refuses to run during collector outage/recovery backlog.
   On first run it seeds existing V2 tracked/profiled items plus
   the last 30 minutes of recent stock changes (bounded latest 3000
   rows), preserving pre-upgrade ephemeral in-memory audit work.
   This prioritizes data integrity and collection continuity; it
   may accumulate coalesced pending work at peak rates, and backlog
   visibility is mandatory.
4. A **source-versioned website cache** (`TORN_FREN_V38_REVISION_CACHE=1`)
   shares graph analysis, cached seven-day stock history and V2
   predictions by item state/gap revision/five-minute clock slot.
   Current departure reachability still rolls forward without
   retraining; source change or gap invalidates immediately;
   stale/missing/future collector heartbeat fails closed.
   The history cache has a fixed 64-entry LRU and 32 striped locks
   to prevent duplicate DB scans under concurrent visitors.
5. A 30s `/api/catalog` cache
   (`TORN_FREN_V38_CATALOG_CACHE=1`) uses single background rebuild
   and explicitly marks stale/overdue data.
6. Existing V37 gap recovery worker/timer, bot and original V18
   Heather/Wolverine shadow timer remain intact. No new V38
   model routing, database erase, trades/travel, API keys, or
   236-model inference fanout.

Tests are on Python 3.12 (VM version) and 3.13:
- durable queue atomic insert/rollback, recovery of expired lease,
  crash-safe incremented generation, partial queue supersession,
  bootstrap and one-shot drain;
- V37 SQLite deterministic FD closure and deferred gap recovery;
- verified-source five-minute graph/V2 caches and default fallback;
- 30s catalog stale-while-refresh, LRU graph rolling-window
  equality, concurrent duplicate requests and bounded locks.
GitHub Actions on this release branch must be **green at the exact
deployment SHA**, not merely earlier commits.

## User action at deployment time (one script, SHA pinned)

The operator has SSH access; assistant has GitHub but **cannot log
into the VM directly**. After final release CI passes:

```bash
cd /opt/torn-fren
git fetch origin release/v37-scalability-audit-20261009
git show FETCH_HEAD:deploy/scripts/deploy_v39_cpu_scalability.sh \
  > /tmp/torn-fren-deploy-v39.sh
bash /tmp/torn-fren-deploy-v39.sh EXACT_40_CHAR_GREEN_RELEASE_SHA
```

The script asserts clean `profitability-v1` at exactly V37
`a93879d`, exact matching fetched release SHA and ancestry.
Then it makes two read-checked SQLite backups with backup() API,
creates the immutable pre-release Git backup branch, fast-forwards,
compiles, installs the 35%-quota service/timer and both website cache
flags, restarts **only** poller and web, and verifies bot/timer status
and HTTP 200. **Stop if any check fails; do not force merge.**

The already-running V37 gap recovery and V18 shadow timers are not
disabled. Expect a very brief poller/web restart.

## Post-deployment acceptance (at 2, 15 and 30+ min)

- Last verified poll heartbeat age <180 seconds, ideally <30;
  at least 30 successful poll cycles in each trailing 15min.
- Poller FD count stays near 3–6, not 681; collector cycles
  remain <30 sec including CPU-pressure periods.
- `vmstat 1 5`: aggregate CPU user+system **clearly below
  100%**; 1min system load typically <=1.6 on 2 OCPU before
  admitting a V38 inference canary. This is not yet measured.
- Web catalog and `/api/history` work, with returned forecasts
  carrying fresh source state and no stale countdown.
- `torn-fren-routine-audit.timer` active and worker leaves recent
  `routine_audit_jobs_v39` rows `done`. Monitor `pending`
  counts and oldest `queued_at`; backlog must not increase
  without bound. Review any `last_error`/lease retries.
- `torn-fren-gap-recovery.timer`, bot and V37 shadow timer active,
  no repeat collector incident.
- Keep V38 full 236-item model execution DISABLED until passes.

Suggested read-only checks:
```bash
cd /opt/torn-fren
uptime
vmstat 1 5
systemctl is-active torn-fren-poller.service torn-fren-web.service \
    torn-fren-bot.service torn-fren-gap-recovery.timer \
    torn-fren-routine-audit.timer
venv/bin/python - <<'PY'
import time
from services.history_service import get_collector_recovery_status
from services.durable_audit_queue_v39 import status
print("heartbeat",get_collector_recovery_status())
print("audit_queue",status())
PY
sudo journalctl -u torn-fren-routine-audit.service --since "20 min ago" \
    --no-pager -o cat | tail -25
PID=$(systemctl show -p MainPID --value torn-fren-poller.service)
echo "poller_fd_count $(sudo ls /proc/$PID/fd | wc -l)"
curl -sS --max-time 10 -o /dev/null -w 'catalog: %{http_code} %{time_total}s\n' \
  http://127.0.0.1:8000/api/catalog
```

## Rollback

If critical health checks fail after deployment, the checked-in
`deploy/scripts/rollback_v39_cpu_scalability.sh` takes the currently
installed **exact release SHA** as argument. It disables the new
routine-audit timer, removes the v39 web flag drop-in, and restores
exactly the saved V37 source commit, restarting poller/web only.
The additive queue schema is safe for old V37 to ignore.
Do **not** delete SQLite WAL/SHM, erase shadow evidence, drop audit
tables or restore database files unless corruption is specifically
diagnosed. Do not run `git reset --hard` except through verified
rollback and clean worktree checks.

## 22-model next milestone

Once V39 CPU is genuinely measured with sustained headroom:
- run the five-model **read-only** V38 probe from the already
  isolated Python 3.12 worktree (not production source);
- enable the separate low-priority 5-item private shadow timer
  ONLY if 5-in-5m can run at its 20%-of-core quota and the main
  collector stays fresh. The research V38 branch contains unit files
  and a strict 5-item allowlist.
- progressively expand to 16 source-pinned runnable adapters
  with actual 5-minute deadline compliance and bounded queue delay;
- integrate exact Red Fox, Lion, Panda, Monkey and Chamois on original
  causal algorithms; Japan Xanax remains a separate specialist pilot.
  Unknown winners show `NOT_INTEGRATED`, never a fake champion.
- all observed 236 catalog entries can be visible using caching,
  but 236 independent champions must not be claimed or spawned.

Forward tests must remain out-of-sample: timestamp of forecast,
model SHA/config, >=30 stock on arrival with 10s grace, 8h horizon,
300sec replans, source freshness, and censor outage/timeout/missing
data. No invented success rates or automated gameplay.
