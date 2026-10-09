# Torn Fren V37 collector safety — controlled VM rollout

**Release:** `release/v37-collector-safety-20261009`
**Base production SHA:** `062f3a27f33062b50b505f9f492b931e9c654cfd`
**Production local branch:** `profitability-v1` (NOT a remote branch).
**Do not merge into main, pull V38, restart whole VM, remove SQLite WAL files,
or alter API keys.**

## Scope

- Deterministic SQLite connection closure in collector, Japan shadow audit,
  and legacy model metadata queries.
- Per-heartbeat O(1) gap detection and throttling of September historical repair.
- Atomically queued durable recovery audit jobs.
- Gap invalidation calculated once per unique item, not per pending forecast.
- Resource-capped **external** recovery timer
  (`torn-fren-gap-recovery.timer`) to prevent a 31–40 minute historical
  validation from blocking 30-second stock collection.
- No V38 model/adapters, 236-item predictor launch, UI model routing, secrets,
  auto game actions, or changes to V37's 4-item research timer.

## Stage 1 — exact-code checks (Ubuntu VM)

```bash
(
set -euo pipefail
cd /opt/torn-fren
test "$(git branch --show-current)" = "profitability-v1"
test "$(git rev-parse HEAD)" = "062f3a27f33062b50b505f9f492b931e9c654cfd"
test -z "$(git status --porcelain)"
git fetch origin release/v37-collector-safety-20261009
git merge-base --is-ancestor HEAD FETCH_HEAD
echo "Release SHA: $(git rev-parse FETCH_HEAD)"
echo "Changes being staged:"
git diff --name-status HEAD FETCH_HEAD
)
```

If any test fails, **STOP**. The first deployment should be SHA-pinned
to the release commit that passed CI.

## Stage 2 — consistent, new SQLite backup

The two SQLite databases must be backed up through the SQLite backup API,
not a bare copy of the live .db or its WAL. The source DBs stay in service.

```bash
sudo python3 - <<'PY'
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
import os
import pwd

stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
folder = Path('/home/ubuntu/torn-fren-pre-collector-safety') / stamp
folder.mkdir(parents=True, exist_ok=False)
for label, source in (
  ('stock_history.db','/opt/torn-fren/data/stock_history.db'),
  ('shadow_capture.db','/var/lib/torn-fren-shadow/capture.db'),
):
    src = Path(source)
    if not src.is_file():
        raise SystemExit(f'Missing source DB: {src}')
    dest=folder/label
    with sqlite3.connect(f'file:{src}?mode=ro',uri=True,timeout=30) as readonly:
        with sqlite3.connect(dest) as backup:
            readonly.backup(backup)
    with sqlite3.connect(f'file:{dest}?mode=ro',uri=True) as verified:
        ok=verified.execute('PRAGMA quick_check').fetchone()[0]
    print(f'{dest}: {dest.stat().st_size:,} bytes, quick_check={ok}')
    if ok!='ok':
        raise SystemExit('Backup verification failed; STOP')
user=pwd.getpwnam('ubuntu')
os.chown(folder,user.pw_uid,user.pw_gid)
for dest in folder.iterdir():
    os.chown(dest,user.pw_uid,user.pw_gid)
print('BACKUPS VERIFIED')
PY
```

## Stage 3 — only after backup and CI

Review `git diff --name-status HEAD FETCH_HEAD` and release SHA. Record
the original local commit before a fast-forward to facilitate rollback.

```bash
(
set -euo pipefail
cd /opt/torn-fren
test "$(git branch --show-current)" = "profitability-v1"
test "$(git rev-parse HEAD)" = "062f3a27f33062b50b505f9f492b931e9c654cfd"
test -z "$(git status --porcelain)"
git branch backup/pre-v37-collector-safety-20261009 HEAD
git merge --ff-only FETCH_HEAD
python3 -m py_compile poller.py services/history_service.py \
    services/forecast_auditor.py research/v38_gap_recovery.py
echo "Installed commit: $(git rev-parse --short HEAD)"
sudo install -m 644 deploy/systemd/torn-fren-gap-recovery.service \
  /etc/systemd/system/torn-fren-gap-recovery.service
sudo install -m 644 deploy/systemd/torn-fren-gap-recovery.timer \
  /etc/systemd/system/torn-fren-gap-recovery.timer
sudo systemctl daemon-reload
sudo systemd-analyze verify \
  /etc/systemd/system/torn-fren-gap-recovery.service \
  /etc/systemd/system/torn-fren-gap-recovery.timer
sudo systemctl restart torn-fren-poller.service
sudo systemctl enable --now torn-fren-gap-recovery.timer
echo "Release installed. Public web, bot, and V37 shadow timer unchanged."
)
```

**Note:** The VM has `/opt/torn-fren/data` symlinked to
`/var/lib/torn-fren`. The external worker's `ProtectSystem=strict`
exception is explicitly `ReadWritePaths=/var/lib/torn-fren`.
If systemd unit validation fails, stop **before** the poller restart and
investigate.

## Stage 4 — after at least 90 seconds and again after 15–30 minutes

```bash
echo "===== SERVICES ====="
systemctl is-active torn-fren-poller.service torn-fren-web.service \
  torn-fren-bot.service torn-fren-shadow-capture.timer \
  torn-fren-gap-recovery.timer

echo "===== COLLECTOR PULSE ====="
python3 - <<'PY'
import sqlite3,time
with sqlite3.connect('file:/opt/torn-fren/data/stock_history.db?mode=ro',uri=True) as db:
    ts=db.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
print('Age:',int(time.time())-ts if ts else None,'seconds (target <=180)')
PY

echo "===== POLLER FD COUNT ====="
PID=$(systemctl show -p MainPID --value torn-fren-poller.service)
sudo python3 - "$PID" <<'PY'
import sys,os,collections
d=f'/proc/{sys.argv[1]}/fd'
values=[]
for name in os.listdir(d):
    try: values.append(os.readlink(f'{d}/{name}'))
    except OSError: pass
print('Total:',len(values))
for path,n in collections.Counter(values).most_common(5): print(n,path)
PY

echo "===== POLLER LOG ====="
journalctl -u torn-fren-poller.service --since '5 minutes ago' \
  --no-pager -o cat | grep -E 'Poll cycle completed|COLLECTION RECOVERY|error|Error' | tail -25

echo "===== EXTERNAL RECOVERY SERVICE ====="
systemctl list-timers --all torn-fren-gap-recovery.timer
journalctl -u torn-fren-gap-recovery.service --since '20 minutes ago' \
  --no-pager -o cat | tail -20
```

Goal: heartbeat <180s, polling every ~30s, total FDs bounded well below
1024 (preferably tens rather than >500), normal web and shadow capture,
and durable recovery queue processed with limited CPU even across timeouts.

## Rollback — only if release is unhealthy

**Destructive Git step:** rollback resets the local tracked source tree,
so perform only when `git status --porcelain` is empty and the saved
original SHA is correct. It does not remove DB rows, and old V37 ignores
the additive `forecast_recovery_jobs_v38` table.

```bash
cd /opt/torn-fren
sudo systemctl disable --now torn-fren-gap-recovery.timer
sudo systemctl stop torn-fren-poller.service
test "$(git branch --show-current)" = "profitability-v1" || exit 1
test -z "$(git status --porcelain)" || exit 1
git reset --hard 062f3a27f33062b50b505f9f492b931e9c654cfd
sudo systemctl start torn-fren-poller.service
systemctl is-active torn-fren-poller.service
```

Rollback restores the previous software failure risks but does not require
restoring stock history from backup because the forward schema is additive.
Do **not** drop the recovery-queue table, delete .db-wal/.db-shm or erase
failed-evidence attempts. For severe database corruption, STOP and diagnose
before deciding whether restoring a prior consistent backup is justified.
