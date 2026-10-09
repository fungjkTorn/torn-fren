# OCI Torn Fren two-core CPU saturation — 2026-10-09 23:21 UTC

**Research scope only.** No production changes, no V38 benchmark until
the existing service CPU load is identified and reduced. V37 collector
release `a93879d` stays installed and is operationally healthy.

## Live operator measurements

- VM `uptime`: 6h08, `load average: 3.67, 3.93, 3.61`
- `vmstat 1 5`: 97–98% user CPU on four 1s live intervals,
  0–1% system, 0% idle, 0% iowait, 0–1% stolen.
- `/proc/pressure/cpu`: `some avg10=50.33 avg60=43.00
  avg300=45.17`, `full avg*=0`.
- `free -h`: ~11 GiB total, ~947 MiB used,
  **~10 GiB available**, no swap; memory not the current limiter.
- Process list cumulative CPU usage: **PID 3860 93.8% CPU**, elapsed
  47m15s, RSS ~104 MiB, PPID 1; **PID 760 58.2% CPU**,
  elapsed 6h08m, RSS ~237 MiB, PPID 1. These CPU percentages
  reflect process lifetime averages, not precise second-by-second
  utilization; `vmstat` confirms current aggregate saturation.
- **PID 3860 timing is consistent with the newly restarted V37 poller,
  but not independently identified yet**. PID 760 is a long-running
  Python service, also not yet mapped.
- V37 poller completed its last 10 cycles in 0.7–6.6 seconds, all
  sleeping for the remainder of their 30-second intervals, so
  the main polling loop has not stalled in this sample.
- V38 source freshness 9 seconds; preflight `DEFER_PROBE` because
  load1 3.774 exceeds 2 OCPU x 0.8 = 1.6. The five-item read-only
  benchmark **did NOT run**. Minimal Python 3.12 ARM venv deps have
  now installed successfully in an isolated detached worktree.

## Strong code-path hypothesis (not yet confirmed by PID mapping)

Production V37 `poller.py` runs an in-process daemon
`_audit_worker` that iterates the items changed since 30-second polls
and calls `_run_item_audits`, which invokes
`update_prediction_audits_for_item`,
`resolve_forecast_audits` and
`build_live_prediction_v2` (plus Japan shadow auditing).
This path rebuilds historical cycle features and SQLite coverage data
per item/run. `_seed_audits_async` also starts on poller launch and
can perform many sequential V2 model refreshes. These two background
threads may consume almost a full OCPU while independent polls still
finish quickly. Do not claim root cause before verifying PID identity
and CPU threads.

Potential second source: web or Discord service (PID 760): map it first.

## Minimal, read-only attribution on VM

```bash
echo '===== SERVICE-PID MAP ====='
for unit in torn-fren-poller.service torn-fren-web.service \
  torn-fren-bot.service torn-fren-gap-recovery.service \
  torn-fren-shadow-capture.service; do
  echo "$unit"
  systemctl show "$unit" -p MainPID -p ActiveState -p SubState \
      -p ControlGroup --no-pager
done

echo '===== HOT PID ATTRIBUTION ====='
for pid in 3860 760; do
  echo "==== $pid ===="
  ps -p "$pid" -o pid,ppid,stat,etime,%cpu,rss,args
  if test -r "/proc/$pid/cgroup"; then cat "/proc/$pid/cgroup"; fi
  ps -L -p "$pid" -o pid,tid,stat,time,pcpu,wchan:25,comm
done

echo '===== CURRENT PRESSURE ====='
vmstat 1 5
```

The commands only inspect /proc and systemd. No restarts, profiler
injection, `strace`, DB writes or elevated thread scheduling.

## Next engineering steps (after attribution)

1. Identify which service accounts for PID 3860 and PID 760 and
   whether the V37 poller's `_audit_worker` or `_seed_audits_async`
   dominates its CPU. Avoid stopping the collector and invalidating
   prospective evidence while diagnosing.
2. Source-profile the costly per-item path in an isolated process on a
   copy of stock data, not using unrestricted worker fanout against
   live production SQLite. Avoid disabling audits without preserving
   pending outcomes, last-update watermarks and fresh V2 fallbacks.
3. Restructure one-time history/feature building with dirty-item
   watermarks and explicit CPU budgets; consider an independent
   low-priority systemd audit process with resource limits, as already
   proven for gap recovery, only after parity tests.
4. With 2 OCPU, long-run admission requires load1 <=1.6 plus
   sustained normal live `/api/catalog` latency and 30-second
   heartbeat cadence. Memory and storage headroom do not substitute
   for CPU.
5. Reattempt V38 five-model benchmark only when CPU threshold returns
   below the guard **without relaxing it**. Do not promote additional
   live champion models during measured CPU saturation.
