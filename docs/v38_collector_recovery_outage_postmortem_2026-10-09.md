# V38 incident and nonblocking recovery design — 2026-10-09

**Production: NOT CHANGED.** Existing `/opt/torn-fren` remains
`profitability-v1` at `062f3a2`. The user manually restarted only
`torn-fren-poller.service` after gathering evidence. That action restored
fresh stock heartbeats; latest observed post-restart heartbeat age: 28s.
No V38 rollout was authorized.

## Verified incident chronology (UTC, user-supplied logs)

- Last normal successful heartbeat before the 40-minute stall:
  **18:55:17 UTC**, last changed stock 18:55:14. Research V18 native
  proposals refused to run if heartbeat age exceeded 180s.
- An earlier poll cycle completed in **177.7s**; a following successful
  poll detected a 186s collection gap and recorded **39 pending forecast
  points invalidated**.
- That same recovery cycle then reported total wall time **2400.6s**
  (40m 0.6s). This timing strongly implicates recovery-audit invalidation
  and related expensive historical continuity reads, but per-stage timers
  are not yet available: cannot prove exactly which operation consumed
  the 2400s. The ordering of log lines implies the long wait occurred
  *after* the successful heartbeat write and before the cycle completed.
- Next provider fetch: YATA read timed out after 10s; Prometheus fallback
  succeeded. Next gap 2386s recovered and normal stock collection resumed.
  YATA timeout is **not** the cause of the prior 2400s event, since it
  occurred on the subsequent poll.
- Existing poller was `active/running` PID 759 despite stale stock; it
  showed 7 threads (main and background audit/model threads), including
  waiting-on-futex tasks.
- After user-issued poller-only restart, next two polls completed in
  **3.8s** and **2.2s**, latest heartbeat age **28s**, `Collector fresh:
  True`; same V37 web/bot/shadow services not restarted.

## Exact code-level hazard in V37

In `poller.run()`, on `recovered_from_gap`, the **main 30-second
collection thread** calls
`forecast_auditor.invalidate_pending_forecasts_crossing_gap()` and
waits for all pending run continuity checks. The latter calls
`_interval_gaps_preserve_item_cycle` per pending forecast run,
often repeating long historical-cycle scans for identical items.
This can starve stock collection long after a successful heartbeat was
recorded, and produces another gap when recovery finally completes.

## Research-only V38 mitigation — no deployment

- `services/forecast_auditor.py`: group pending forecasts by normalized
  country/item key; evaluate expensive continuity once per item/gap; perform
  point invalidations in one short writer transaction. Original
  item-specific evidence thresholds, reasons, and `status='pending'`
  guards preserved. Regression test includes 80 duplicate pending
  Heather forecasts plus independent Xanax and recent forecasts;
  duplicate reprocessing is idempotent.
- `research/v38_gap_recovery.py`: SQLite-backed
  `forecast_recovery_jobs_v38` queue with composite gap identity,
  retry-after status and completion count. Jobs stay pending on failure
  and can be retried after a process restart. Only existing forecast
  audits change; historical stock rows are not fabricated or deleted.
- `poller.py`: the main collector only queues newly detected gaps and
  signals a separate daemon recovery worker. The audit worker defers
  processing while recovery jobs are pending, then resumes on
  completion. A slow, expensive gap evaluation therefore does not
  synchronously stop 30-second stock polling. This still shares CPU and
  SQLite with the main poller; it does not guarantee zero contention.
- Earlier V38 heartbeat fastpath prevents full `poll_heartbeats`
  history scans every successful poll and periodically reconciles
  legacy-only failure history.
- V38 regression tests:
  `tests/test_v38_gap_recovery.py`,
  `tests/test_v38_gap_invalidation_grouping.py`, and
  `tests/test_v38_heartbeat_fastpath.py`. Existing V35 and V37
  compatibility CI continues.

## Remaining safety qualifications before production

1. **No production speedup is measured.** The old 2400s cycle is
   pathological and must be reproduced against sanitized realistic
   history in a separate research worktree before promotion.
2. The recovery worker currently runs as an in-process daemon thread:
   while the collector loop no longer waits synchronously, memory/CPU
   and SQLite locks remain shared. Consider a subprocess/systemd
   memory/CPU/time-bound worker if real gap processing is still slow.
3. A very narrow crash window remains between saving the successful
   heartbeat and inserting the durable gap job. Before promotion,
   add startup reconciliation of unqueued recent collection_gaps
   or insert the job atomically in the heartbeat transaction.
4. Ensure the queue drain and forecast-audit pause do not cause
   unbounded audit backlog or fresh-reference V2 latency regression.
5. The October 9 gap is unknown ground truth, not a model failure.
   Preserve `COLLECTOR_STALE_OR_NO_HEARTBEAT` evidence and
   `available_stale` V2 status. Do not backdate observations.
6. Restore all four existing prospective native/baseline research
   attempt streams first, before enabling V38 22-item research collection.

## Safe immediate observation (read-only, no service changes)

```bash
cd /opt/torn-fren
python3 - <<'PY'
import sqlite3,time
p='/opt/torn-fren/data/stock_history.db'
with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:
    hb=db.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
age=int(time.time())-hb if hb else None
print('Heartbeat age seconds:',age)
print('Fresh (<180s):',age is not None and 0<=age<=180)
PY
systemctl is-active torn-fren-poller.service torn-fren-shadow-capture.timer
journalctl -u torn-fren-poller.service --since '5 minutes ago' --no-pager -o cat |
    grep -E 'Poll cycle completed|COLLECTION RECOVERY|error' | tail -18
```

Check after at least one full 20-minute research rotation whether
Heather and Wolverine actually log `champion_executed=1` again.
Nessie and Japan Xanax are still specialist-not-integrated in V37.


## Third stall sample: ~22:xx UTC, October 9

User's live poller PID 2492, uptime 2h37, 7 Python threads. Recent
journal showed:
- `Poll cycle completed in 1858.2s; sleeping 0.0s...`
- `Invalidated 100 pending forecast point(s) whose item cycle became
  ambiguous during the gap.`
- Following cycle saved all country snapshots, detected `COLLECTION
  RECOVERY: 1836s without verified polling`, and was still waiting
  when heartbeat age was **449 seconds**.
- Background forecast/model traceback repeatedly showed
  `sqlite3.OperationalError: unable to open database file` from
  `services.history_service._connect` during expensive cycle rebuild.
  This error does NOT mean SQLITE_BUSY. Possible transient storage,
  inode, access, file descriptor, or resource exhaustion remain unproven
  until local VM diagnostics (`df -h`, `df -i`, `ls`,
  `/proc/<PID>/fd`, process open-files soft limit and independent
  read-only SQLite SELECT 1) are received.
- Live forward-test records again mark V18 models
  `COLLECTOR_STALE_OR_NO_HEARTBEAT` while V37 timer still runs.
  Preserve gaps as unknown historical outcomes; no synthetic backfill.

## Updated V38 mitigation: completely separate recovery worker

Previous V38 design used an in-process daemon thread. Research
branch now has a **separate systemd oneshot service/timer**:
`deploy/systemd/torn-fren-gap-recovery.service` and
`deploy/systemd/torn-fren-gap-recovery.timer`.
This completely removes historical gap invalidation from the poller
process, not merely its main thread. The low-priority recovery process
uses `CPUQuota=50%`, `MemoryMax=768M`,
`TimeoutStartSec=180`, `Nice=15`, and one durable pending job per
timer invocation. One timer firing every minute is a bounded attempt,
not a promise of completion; timed-out work gets a retry lease
before the audit to avoid immediate retry storms. The durable
`forecast_recovery_jobs_v38` table and gap heartbeat are committed
atomically. Retry rescores only pending points, never fabricates
outcomes. The in-process poller audit thread refuses to process
unresolved forecast attempts until the pending recovery jobs finish.

**Important**: the new recovery timer must be installed and enabled
together with any eventual poller code promotion. If no recovery
service is enabled, the pending queue can delay ordinary forecast
audit progress indefinitely. No production rollout authorized or
performed yet. Never turn on the timer against the old V37 code
without an explicit migration plan, and do not switch the prod branch
to the 236-item V38 research branch directly.

Remaining follow-up: prospective performance test on sanitized history,
verify unit security hardening and external job can complete with resource
caps, inspect SQLite connection errors, characterize recovery catch-up,
safe rollback plan, and confirm public site and independent V37 evidence.

## Second live incident — 2026-10-09 22:11 UTC

After a successful user-initiated V37 poller-only restart, live V18
champions executed again: `uni:Heather` at **21:21:05 UTC** and
`can:Wolverine Plushie` at **21:26:09 UTC**, both
`RESEARCH_PROPOSAL_ONLY` / `champion_executed=1`.

At the user's next read-only diagnostic after 22:11 UTC, current heartbeat
age was **332 seconds** (`Fresh: False`). Heather and Wolverine had
`COLLECTOR_STALE_OR_NO_HEARTBEAT` and
`champion_executed=0` at 21:41/21:46 and 22:01/22:06 UTC.
Both specialist-unintegrated items (`uni:Nessie Plushie`, `jap:Xanax`)
continued recording baseline-only research attempts. This is **another
collector stall**, not a shadow timer stoppage. The exact blocking operation
during incident #2 is not yet observed; DO NOT ascribe it to recovery
invalidation without current poller journal/thread snapshots.

The user was asked to capture:
- `ps -L` on the active poller PID including TID, CPU and wait-channel;
- last 70 journal lines from the poller over 20 minutes;
- current read-only `poll_heartbeats` latest success age.

No production code edits / forced restart made by the assistant.

**Priority order:**
1. Capture stall evidence before service restart while stale.
2. Restore verified successful heartbeats safely, accepting and preserving
   any uncertain stock-outage evidence.
3. Reproduce and profile the known 40-minute outage path in an isolated
   VM copy (not on the running collector).
4. Production promotion of V38 mitigation must first pass known/unknown
   outage scenarios, DB backup, bounded resource canary, and explicit
   user authorization. Do not enable 22-champion schedule while live
   collector continues stalling.

## V37 collector-safety production deployment — verified at 2026-10-09 ~22:36 UTC

User personally performed a guarded, fast-forward release from
`profitability-v1` SHA `062f3a2` to **`a93879d`** from
`release/v37-collector-safety-20261009`. They checked exact original and
release SHAs, branch and clean worktree; `git fetch`, local backup branch,
`git merge --ff-only FETCH_HEAD`; installed bounded recovery service/timer;
restarted only `torn-fren-poller.service` and enabled timer. The compiler
and systemd unit validation reported no errors (systemd gave unrelated Oracle
unified-agent executable-permission warnings).

Consistent, read-checked backups produced *before* deploy:
- `/home/ubuntu/torn-fren-pre-collector-safety/20261009T223349Z/stock_history.db`
  size **153,378,816 bytes**, `PRAGMA quick_check=ok`.
- `/home/ubuntu/torn-fren-pre-collector-safety/20261009T223349Z/shadow_capture.db`
  size **143,360 bytes**, `PRAGMA quick_check=ok`.

Post-restart after 90 seconds:
- `systemctl is-active`: **active** for poller, web, bot, existing
  V37 four-item shadow timer, and new gap-recovery timer.
- Collector last success age **26 seconds**, verified fresh (<180s).
- Poller /proc file descriptors **3** vs prior **681**, consistent with
  deterministic SQLite closure operating in the real process.
- Six recent poll cycle times `4.7,5.3,2.8,0.2,1.0,0.3` seconds,
  mean **2.38 seconds**. The recovery observation reported
  `COLLECTION RECOVERY: 1611s without verified polling`, followed by
  successive near-30-second healthy polling intervals. This initial
  observation demonstrates that the known recovery gap was not
  synchronously blocking the poller at the time of the snapshot.
- Website catalog `HTTP 200 | 0.228088s`.
- New timer had `LAST Fri 2026-10-09 22:35:02 UTC`, **NEXT -** in
  `systemctl list-timers --all` despite active status. Must verify
  `systemctl show` `NextElapseUSecRealtime`, timer state,
  oneshot service result/logs, and pending recovery-job count. Active
  timer alone does NOT prove recovery backlog drained.

**Do not claim sustained outage elimination yet.** Recheck after at least
15–30 minutes under production traffic; verify that outstanding recovery
jobs reach `done` and prospective V18 champion-executed observations
resume. No prod V38 model deployments. Do not change user's production
release commit except through newly authorized controlled deployment.
