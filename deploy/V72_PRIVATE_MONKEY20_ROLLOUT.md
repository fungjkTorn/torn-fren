# V72 — Monkey-first private 20-model shadow rollout

Status: candidate only. Keep public poller/web/bot and production collector unchanged.

## Proof already established
V66 original Monkey 24-expert / 2-day resolved selector parity: passed.
V68 isolated Monkey: passed in ~5s wall (single VM sample).
V69 original 19: 19/19, but Monkey cache watermark raced ahead of frozen source.
V70 Monkey first and 19 original later: all 20 research proposals persisted.
V71 read-only issued-time audit: 20/20 valid at issuance, zero invalid
source-pinned issues, 20 immutable proposal records; expired departures
at audit time are separate from as-issued correctness. These tests do NOT
measure true forward-looking restock prediction accuracy.

## V72 architecture
The existing torn-fren-v38-private-shadow.timer continues its 5-minute
cadence. The new deploy/systemd/v72-private-mirror20.conf changes ONLY
ExecStart for the private research service, retaining CPUQuota=25%,
MemoryMax=1024M, Nice=19, timeout 240s, sandbox restrictions and independent
V48 warmup timer. No automatic travel or game action.

The V72 scheduled runner:
1. Checks measured host pressure; defers if unsafe.
2. Creates one fresh, private immutable SQLite snapshot with V65's
   existing retry and freshness gate.
3. Runs Monkey first against the original 24-expert, 2-day source-pinned
   V48 cache, preserving all original V66 validation gates.
4. Writes Monkey research proposal OR explicit NULL-departure abstention to
   /var/lib/torn-fren-v38/v72_private_predictions.db.
5. Runs V65's ORIGINAL 19 champion adapters and due scheduler against
   the SAME snapshot, with unchanged 19-job / 30s worker / 220s budget.
6. Reports exact counts, source heartbeat age, Monkey parity and any
   source staleness. Do not claim successful live validation if age >180s.

The V65 rollback sidecar /var/lib/torn-fren-v38/private_predictions.db is
NOT modified. No public website or bot consumes the V72 private sidecar.

## Guarded VM procedure
- Fetch the research branch and apply deploy/scripts/v49_safe_update.sh.
- Run the V72 unit tests in tests/test_v72_private_mirror20_shadow_tick.py.
- One-shot smoke V72 under a 25% CPU, 1GiB memory, Nice=19, 240s timeout,
  read-only collector sandbox, preferably while V65 service is idle.
  Keep V38 and V48 timers enabled.
- Require V72_EXECUTED_RESEARCH_ONLY, original_19_proposal_count=19,
  monkey_status=V68_MONKEY_ISOLATED_RECORD_READY, proposal_count=20,
  snapshot_fresh_after_cycle=true, no errors/stale statuses.
- Only AFTER successful smoke, obtain explicit operator approval and run:
  bash deploy/scripts/v72_private20_transition.sh status
  bash deploy/scripts/v72_private20_transition.sh enable
  This pauses ONLY the V38 timer momentarily, waits naturally for the running
  V38 service to finish, installs V72 override above V65, daemon-reloads,
  starts V38 timer, and verifies the ExecStart. V48 remains enabled.
- Inspect multiple unattended scheduled cycles, plus public system health;
  do not count 20/24 as SCHEDULED until V72 is actually enabled and healthy.

Rollback:
  bash deploy/scripts/v72_private20_transition.sh rollback
This removes only V72 override and restores V65 ExecStart. The V65 overlay
and private prediction DB remain untouched. Do not stop production polling.

## Invariants
Never bypass source watermark/gap fingerprint or use cache evidence newer
than the immutable snapshot. Do not present selector scores as probabilities.
As-issued valid proposals and still-actionable departures are different.
Actual travel is NOT observed, triggered, or simulated as gameplay.
