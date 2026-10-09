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
