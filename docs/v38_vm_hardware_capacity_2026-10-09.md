# V38 Oracle VM sizing checkpoint — October 9, 2026

Production remains `profitability-v1` at `062f3a2`. Do not resize, deploy
V38, start extra workers or restart services without explicit user approval.

## User-provided read-only evidence

- CPU: **one** ARM Neoverse-N1 logical CPU (`nproc=1`).
- CPU: `vmstat 1 5` measured 93–97% user on all four interval samples
  and approximately 0% idle. One-minute load 4.50; 5m 4.67; 15m 4.71.
- RAM: 5.8 GiB, **4.4 GiB available**; no swap. Memory is not the
  immediate saturation point.
- Disk: 45 GiB filesystem, 39 GiB available (13% used); collector
  SQLite 145 MiB, private research evidence 108 KiB.
- No NVIDIA compute GPU. `lspci` reports Red Hat Virtio display controller.
- V37 public catalog: ten HTTP 200 requests, elapsed
  0.987996, 0.918495, 0.902877, 0.903704, 0.942637, 0.951244,
  0.923630, 0.923230, 0.901722, 0.902179 seconds
  (~0.93s average, 0.988s worst).
- V37 research quota: `CPUQuota=50%`, `MemoryMax=536870912`,
  `TimeoutStart=75s`. Web, bot, poller and timer were active.
- Top CPU-attributed Python processes: PID 106384 (90.6% RSS 424672 KiB),
  PID 289020 (48.8% RSS 313600 KiB), and PID 124634
  (0.4%, RSS 212092 KiB). PID-to-service mapping **unknown**; these CPU
  percentages are process reports, not proof of simultaneously available CPU.
- **Follow-up cgroup attribution, verified by user:** PID 106384 is
  `torn-fren-poller.service` (90.5% lifetime CPU, 426600 KiB RSS);
  PID 289020 is `torn-fren-web.service` (48.9% lifetime CPU,
  313620 KiB RSS); PID 124634 is `torn-fren-arbitrage.service`
  (0.4%, 212092 KiB RSS). Bot MainPID 162431. Research capture
  `MainPID=0` is normal for an inactive oneshot between timer ticks.
- `/proc/pressure/cpu`: **some avg10/60/300=100.00**;
  **full avg10/60/300=0.00**. This indicates sustained runnable
  CPU waiting, not all runnable threads stalled. Percent CPU via
  `ps` is lifetime-average, so thread-level current samples still
  needed to identify the active poller hotspot.
- Verified V37 code: `poller._audit_worker` runs
  `update_prediction_audits_for_item`, `resolve_forecast_audits`
  and for tracked items `build_live_prediction_v2` for changed
  stock quantities; this may repeat expensive validated-cycle builds.
  `history_service.record_poll_heartbeat` also invokes both
  `_reconcile_known_collection_gaps_conn` and
  `_reconcile_heartbeat_collection_gaps_conn` **every 30-second
  successful poll**; latter reads all successful heartbeat history
  and reconciles previous gaps again. These are code-level candidates,
  not yet demonstrated timing contributions.
- This observed load means there is **no safe extra CPU headroom now**.
  Do not start a 16- or 22-model high-cost benchmark or a 236-item loop.

## Safe next CPU attribution — no secrets or process command lines

```bash
ps -p 106384,289020,124634 -o pid,ppid,etime,stat,%cpu,%mem,rss,comm
for pid in 106384 289020 124634; do
    echo "===== PID $pid cgroup ====="
    if test -r "/proc/$pid/cgroup"; then
        cat "/proc/$pid/cgroup"
    else
        echo "PID no longer present"
    fi
done
systemctl show torn-fren-web.service torn-fren-bot.service torn-fren-poller.service torn-fren-shadow-capture.service -p Id -p MainPID -p ControlGroup
cat /proc/pressure/cpu
```

No `ps -ef` or environment-file dump: command-line parameters may
contain secrets. Existing systemd services stay unchanged.

## V38 safeguards already coded on *research branch only*

- Opt-in `TORN_FREN_V38_CATALOG_CACHE=1` stale-while-revalidate
  `/api/catalog` cache: 30s TTL, a single background refresh,
  explicit cache age/status; original uncached behavior without flag.
  This is a likely optimization, **not measured production speedup**.
- `research/v38_capacity_guard.py` denies new research worker execution
  at >0.80 one-minute load per affinity-visible CPU. At the supplied load
  (4.50 on one CPU), V38 runner returns `DEFERRED_CPU_PRESSURE` before
  touching collector or sidecar. No guarantee of true spare capacity is
  inferred merely because this conservative check later passes.
- Historical-feature cache invalidation preserves unchanged-quantity polls
  (with time-slot-specific features still bound to their clock slot);
  model engine integration of the cache remains outstanding.

## Possible zero-dollar CPU increase — verify OCI console first

Oracle's *current* Always Free documentation:
https://docs.oracle.com/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

This says Arm VM.Standard.A1.Flex is allocated **2 OCPUs/12 GB total**
equivalent, subject to tenancy eligibility and other Always Free instance use.
If this is an A1.Flex 1 OCPU/6GB VM with unused eligibility, a free resize
may be possible. Check exact shape, free eligible usage, available capacity,
and account-specific cost estimate. OCI notes resizing a running VM **reboots
the instance**, so take snapshots/backups, schedule downtime, verify fixed IP
and boot volume safety, and get user approval; no resize is authorized.

## Quantified inference budgets

One CPU provides at most 300 CPU-seconds per 5-minute block shared by
everything. Twenty-two items at even 10 CPU-seconds each would consume
~73% of one core before serving public users; 236 at 1 CPU-second each
already consumes ~79%. Both are inappropriate at observed near-100% load.

Preserve 5-minute replan only for truly active/actionable plans; defer
cold/rare forecasts, use event-driven invalidation, grouped cached histories
and separate precomputed snapshots. An overload is an explicit
miss/deferred event, not a synthesized champion prediction.

## Before considering Oct 14 beta

Identify production process CPU demand, validate catalog caching gain
in separate/isolated context, check web p95/p99 and post-probe status, and
prove per-family model wall time/RSS without exhausting host capacity.
Do not change `profitability-v1` or systemd until confirmation.

## Follow-up read-only attribution while system is running

```bash
# Identify whether the poller main polling thread or the audit thread is hot.
ps -L -p 106384 -o pid,tid,stat,%cpu,etime,comm --sort=-%cpu
ps -L -p 289020 -o pid,tid,stat,%cpu,etime,comm --sort=-%cpu

# Avoid secrets/process command-line/environment disclosure in logs.
journalctl -u torn-fren-poller.service --since '10 minutes ago' --no-pager -o cat |
  grep -E 'Poll cycle completed|inserted |prediction audit |forecast audit |shadow audit |Poll cycle save error' |
  tail -80

# Per-process 1 second CPU sample only if sysstat is present.
if command -v pidstat >/dev/null 2>&1; then
  pidstat -u -t -p 106384,289020 1 5
else
  echo 'pidstat not installed; ps -L provides lifetime thread signal'
fi
```

Do **not** disable audits or gap reconciliation until output parity and
collection-freshness regressions have been tested on V38. A shorter heartbeat
path and audit work coalescing may help, but their CPU savings remain unmeasured.

## Second user sample: Oct 9, 2026

- OCI console confirms `VM.Standard.A1.Flex`, **1 OCPU / 6 GB RAM**,
  Always Free-eligible, account banner **Free Trial** (not an entitlement
  confirmation for extra resources). OCPU selection says **"OCPU count
  is restricted by account limits."** "41 max" is technical shape maximum,
  not the Always Free allowance.
- **2026 Oracle official Always Free allocation:** **1,500 Ampere OCPU-hours
  and 9,000 GB-hours monthly**, equivalent to **2 OCPUs / 12 GB RAM total**
  running continuously, *across instances*. Oracle reduced the older
  4-OCPU/24-GB allocation. See:
  https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Verify the *account's actual* available A1 resources under
  **Governance & Administration > Tenancy Management >
  Limits, Quotas and Usage > Compute**, particularly
  `standard-a1-core-count` and `standard-a1-memory-count`;
  service limit versus used and available. If only 1 is available,
  diagnose account quota and other instance usage, **do not attempt**
  an unapproved resize or chargeable alternative.
  Guide:
  https://docs.oracle.com/en-us/iaas/Content/General/service-limits/view-tenancy.htm
- `ps -L` on poller PID 106384 returned **only one live thread**,
  while V38 source has polling and audit background threads; its runtime
  started >11 days before the current V37 deployment and may have loaded
  older code, or audit thread may have exited. Do not assume the current
  source's audit worker runs in that process. Do not restart poller blindly.
- Seven collector cycles completed in **20.9, 20.1, 22.4, 11.9,
  13.5, 20.3, 21.1 seconds** of each 30-second target window.
  Many items were unchanged each poll; significant CPU expenditure persists.
  The exact share from poller sqlite insert/lookups, reconciliation, fetch,
  and audit must be timed before stating causality.
- Research-only optimized `services/history_service.py`:
  every successful heartbeat now checks only the immediately preceding
  verified successful heartbeat for >180s gap and inserts the exact
  boundary only when needed (O(1) normal case). Explicit
  `reconcile_collection_gaps()` still performs full historical
  backfill. September-specific changed_items failure repairs are
  scheduled at process startup and then every 600s or immediately on
  failed poll, not every 30s. The existing collector event semantics,
  heartbeat failure evidence, and database schema are unchanged.
  Synthetic parity regression tests in
  `tests/test_v38_heartbeat_fastpath.py`.
- These are *branch-only* code changes; real VM CPU savings remain
  unmeasured, and no existing service has restarted.

## Post-resize empirical baseline — 2026-10-09 17:18 UTC

User explicitly resized their original Oracle Always Free-eligible
VM.Standard.A1.Flex from 1 OCPU/6 GB to **2 OCPUs/12 GB** and rebooted.
These are actual user-pasted post-reboot CLI observations; no V38 release.

- `nproc=2`, Linux reports 11 GiB RAM / 10 GiB available,
  ~972 MiB used, no swap.
- Prod still **`profitability-v1` at `062f3a2`**. Website, Discord
  bot, poller, shadow-capture timer all `active`.
- Shadow capture timer: previous run 17:16 UTC, completed 17:16:03,
  `Result=success`, `ExecMainStatus=0`.
- Catalog HTTP times (seconds): `0.180515, 0.178922, 0.180621,
  0.181566, 0.183028, 0.182673, 0.183129, 0.182559, 0.182919,
  0.181980`; mean approx **0.182 s** versus pre-upgrade approx
  **0.926 s**, or **5.1× lower observed latency**. Warm/cold, active
  load and process restarts also differ, so do not claim CPU scaling
  explains *all* improvement; repeated snapshots are one endpoint only.
- Last 10 poll cycle wall times (seconds): `6.8, 11.4, 10.1, 1.0,
  10.8, 1.3, 1.0, 11.9, 1.9, 11.9`, mean **6.71 s** versus seven
  pre-upgrade `20.9, 20.1, 22.4, 11.9, 13.5, 20.3, 21.1`,
  mean **18.6 s**. No collection cadence change observed; 30-second
  target remains.
- CPU PSI `some avg10=47.92 avg60=50.42 avg300=32.64` and
  `full=0`. Four after-first vmstat samples show ~20–31% CPU
  idle on two cores, but persistent runnable contention remains.
  Uptime only 5 min; load `4.97,2.96,1.30` not steady state.
- Top Python processes in user snapshot: PID 759 **129% lifetime
  CPU**, PID 760 **41.2% lifetime CPU**, services not yet confirmed
  post-reboot. Together ~170% of a 200% CPU allotment averaged since
  boot, corroborating limited headroom.
- **V38 guard** `normalized load > 0.8 OCPU` currently rejects
  any opt-in research execution since 4.97/2 > 0.8; this is
  intentional fail-closed behavior. Consider rerunning once stable
  rather than lowering the cutoff blindly. Cache/snapshot reads and
  registry status remain cheaper alternatives to model execution.
- No V38 production changes, no paid upgrades authorized.

### Best next observations, read-only

```bash
echo "===== POST-REBOOT PIDS ====="
systemctl show torn-fren-poller.service torn-fren-web.service torn-fren-bot.service -p Id -p MainPID
ps -L -p 759,760 -o pid,tid,stat,%cpu,etime,comm --sort=-%cpu

echo "===== FETCH SUCCESS VS FALLBACK ====="
journalctl -u torn-fren-poller.service --since '10 minutes ago' --no-pager -o short-iso |
  grep -E 'Fetching travel|YATA|Prometheus|Saving all country|Poll cycle completed|Poll cycle save error' |
  tail -100

echo "===== STABLE CPU AFTER UPTIME 15m ====="
uptime
cat /proc/pressure/cpu
vmstat 1 5
```

Observe whether 10–12-second cycles correlate with YATA failure,
Prometheus fallback, audit work, or history reconciliation; no
attribution until per-stage timing evidence. Keep 22-champion
benchmarks disabled on public VM until pressure and budget justify it.
