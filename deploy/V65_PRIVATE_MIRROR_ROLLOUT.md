# V65 Private 19-Model Mirror Rollout

Research only; does not modify the production poller, website, bot, DB schema, or independent V48 cache timer.

## Evidence

- V57/V59 identified SQLITE_CANTOPEN (14) and SQLITE_READONLY_RECOVERY (264) in workers accessing live SQLite WAL with strict read-only sandboxing.
- V62: four approved models, 4/4 proposals under protected systemd using a private DELETE-journal-mode snapshot.
- V63/V64: all 19 approved models, 19/19 proposals, zero errors, runtime 114.6 seconds, 27.7 CPU seconds, heartbeat age 4s at snapshot and 114s at end.
- Five missing specialists remain absent: Monkey, Chamois, Lion, Panda, Japan Xanax.

## Behavior

The explicitly opt-in V65 private research entry point executes under the existing V44 service timer, resource limits and filesystem sandbox. It checks idle admission first, backs up the approved collector using SQLite mode=ro, validates a fresh successful poll heartbeat, changes ONLY the private backup to rollback DELETE journal mode, and atomically publishes that copy. It then runs the exact 19 approved models using the existing due-model scheduler and existing private-only prediction sidecar. The workers no longer read the live WAL source directly. If the snapshot is stale, unavailable, or invalid, there is no fallback to live WAL. Errors are fingerprinted privately, and a failed snapshot means a nonzero service result. Snapshot acquisition retries ONLY transient WAL/open/lock errors, with bounded delays.

The overlay deploy/systemd/v65-private-mirror19.conf changes only ExecStart. No CPU, RAM, permission, timer or environment setting is changed. The V44 Red Fox overlay is preserved as the fallback if the V65 drop-in is removed.

## Guarded operator activation

1. Verify CI, V65 tests, the currently effective V44 19-model ExecStart, and both research timers active.
2. Stop ONLY the V38 private shadow timer. Let its current one-shot service finish; do not kill it.
3. Install deploy/systemd/v65-private-mirror19.conf into /etc/systemd/system/torn-fren-v38-private-shadow.service.d/v65-private-mirror19.conf and daemon-reload.
4. Confirm the effective ExecStart is research.v65_private_mirror_shadow_tick and that ProtectSystem=strict, ReadWritePaths=/var/lib/torn-fren-v38, CPUQuota=25%, MemoryMax=1024M remain intact.
5. Restart the V38 research timer, trigger one service run, and observe at least three consecutive five-minute cycles. Confirm per-model outcome mix, snapshot freshness, overall wall time, collector success, and V48 cache progress.
6. Never modify production or merge to main as part of this activation.

## Rollback

Stop ONLY torn-fren-v38-private-shadow.timer and wait for torn-fren-v38-private-shadow.service to finish. Remove ONLY /etc/systemd/system/torn-fren-v38-private-shadow.service.d/v65-private-mirror19.conf. Run systemctl daemon-reload, verify the effective ExecStart returns to the original V44 budgeted_runner --with-xanax --with-redfox command, and restart the V38 research timer. The V48 timer and production web/poller/bot are not affected.

## Caveats

This is not a continuously updated source: a snapshot can age during a long serial run. Each model retains its 180-second heartbeat gate and abstains if the frozen source has aged too much. Previous snapshots must never be reused after a failed refresh. This is a private research capability only; no public probability or gameplay automation claim is made.
