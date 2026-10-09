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
