# V39.1 queue fairness + SQLite sandbox hotfix (Oct 9 2026)

This is a minimal V39-derived production hotfix. **Do not** merge the
V38 research branch into production. The user-approved V39 release
`e9ba974c96553ea36f31951b94901b7379b22624` remains the base.
No flower/plushie specialists are installed or routed publicly.

## Incident and evidence

After V39 substantially reduced observed aggregate CPU to ~18–19% busy
and restored catalog HTTP 200, private V38 launch could not pass its
audit progress gate: `pending=384, running=1, done=1`, most recent
completion age 62s, and oldest priority-10 stock audit waited
**1,500s** (25m), beyond the 1,200s gate. The collector, public web
and ordinary Japan capture remained active. The five private models did
not run, and no extra timer was enabled.

Root cause found in V39 source:
- `claim()` ordered `priority DESC, queued_at DESC`, so newest
  changes always overtook old pending work; repeated stock changes
  replaced `queued_at` on the same job. That can create unbounded
  starvation under a high-volume 236-item event stream.
- All stock transitions shared the same priority (10), so a 236-item
  historical audit backlog displaced imminent 5-item canary/legacy
  Japan Xanax auditing.
- The systemd audit unit declared `ProtectSystem=strict` and
  `ReadWritePaths=/var/lib/torn-fren`, but the actual collector
  SQLite and WAL reside at `/opt/torn-fren/data/stock_history.db`.
  This sandbox mismatch can prevent an audit worker from writing
  its durable results. Fix read-write allowlist; do not disable
  sandbox protection.

## Minimal changes

- Atomic `enqueue`: coalesce repeated changes while preserving the
  **oldest waiting timestamp**; a transition after a completed job
  starts a new waiting interval. No history, queue or evidence rows
  are erased.
- `claim`: order by priority DESC then earliest waiting event ASC,
  with deterministic country/name ties.
- Six high-urgency private pilot or existing audited items at
  priority 100: `uni:Heather`, `can:Wolverine Plushie`,
  `arg:Ceibo Flower`, `jap:Cherry Blossom`,
  `uni:Nessie Plushie`, `jap:Xanax`.
  Existing queued generations are **promoted in place** idempotently.
  Other 236-item baseline audits stay queued at priority 10 and
  historical bootstrap stays priority 0.
- The isolated systemd audit worker remains capped at **35% of
  one CPU**, `Nice=17`, `MemoryMax=768M` and
  `ProtectSystem=strict`, but can write to
  `/opt/torn-fren/data`. Collector and web remain on their
  current V39 code; no public model switches.
- Research V38 host gate is separately updated to require
  completion progress + no overdue **priority-100** target; older
  background-catalog backlog is still reported but not a false
  canary blocker.

## Tests and acceptance

CI on Python 3.12 (real ARM VM version) and 3.13 includes:
FIFO ordering; canary dispatch overtakes catalog backlog; no loss
of latest stock generation; no queued-at clock reset while pending;
legacy priority-10 job promotion without changed generations;
repeatable promotion; sandbox path; release shell syntax; existing
V37 collector + V39 graph/cache regressions.

After an exact-green-SHA guarded deployment:
- verify fresh 30-second successful poll heartbeat, web HTTP200,
  poller FD count small, bot active;
- read-only SQL priority groups show up to six priority-100 rows;
- worker logs show `COMPLETED`, no repeated sqlite
  `readonly database` errors; `last_finished_at` increases;
- priority-100 pending age eventually falls below 20 minutes.
  Existing general catalog backlog need not clear immediately.
- wait for stable 1-minute load <=1.6 before next model inference.
  Never override CPU thresholds or falsify completed status.

## Deployment

After CI is green at **exact release SHA**, SSH operator runs:

```bash
cd /opt/torn-fren
git fetch origin release/v39-priority-fairness-20261009
git show FETCH_HEAD:deploy/scripts/deploy_v39_1_queue_fairness.sh > /tmp/torn-fren-deploy-v39-1.sh
bash /tmp/torn-fren-deploy-v39-1.sh EXACT_40_CHAR_GREEN_RELEASE_SHA
```

The script checks the exact current V39 SHA/clean worktree, verifies
collector/web, makes a separate fresh SQLite online backup with
`PRAGMA quick_check=ok`, saves the original V39 Git commit, merges
the hotfix, corrects the audit-worker systemd sandbox, and restarts
**only the poller** to load improved atomic enqueue semantics. Audit
worker/timer, web and bot remain running; target queue priorities
are promoted after cutover. No snapshot replacement.

Revert source and unit with the checked-in
`deploy/scripts/rollback_v39_1_queue_fairness.sh`, passing the
exact currently deployed SHA. Rollback never deletes collected stock,
SQLite WAL, queued audits or forecast evidence.

**Research V38 five-model shadow remains OFF until the canary
rechecks live CPU, fresh stock source and priority-100 queue health.**
