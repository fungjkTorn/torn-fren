#!/usr/bin/env bash
# Controlled V39 CPU-isolation release; invoked by operator on Oracle VM.
# Usage: bash deploy_v39_cpu_scalability.sh <pinned-40-character-release-sha>
set -euo pipefail

EXPECTED_BASE="a93879d42808c7a2f7485b88b6393056d87d01c9"
RELEASE_REF="release/v37-scalability-audit-20261009"
TARGET="${1:-}"
REPO="/opt/torn-fren"
if [[ ! "${TARGET}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: provide exact CI-passing release SHA" >&2
  exit 2
fi

cd "$REPO"
test "$(git branch --show-current)" = "profitability-v1"
test "$(git rev-parse HEAD)" = "$EXPECTED_BASE"
test -z "$(git status --porcelain)"

echo "===== VERIFY EXACT SOURCE ====="
git fetch origin "$RELEASE_REF"
test "$(git rev-parse FETCH_HEAD)" = "$TARGET"
git merge-base --is-ancestor HEAD FETCH_HEAD
git diff --name-status HEAD FETCH_HEAD

echo "===== CONSISTENT VERIFIED BACKUPS ====="
sudo python3 - <<'PY'
import os, pwd, sqlite3
from datetime import datetime, timezone
from pathlib import Path
stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
folder=Path("/home/ubuntu/torn-fren-pre-v39")/stamp
folder.mkdir(parents=True,exist_ok=False)
for label,src in (
    ("stock_history.db","/opt/torn-fren/data/stock_history.db"),
    ("shadow_capture.db","/var/lib/torn-fren-shadow/capture.db")):
    source=Path(src)
    if not source.is_file():
        raise SystemExit(f"STOP: missing database {src}")
    dest=folder/label
    # SQLite backup API includes uncheckpointed WAL and is non-destructive.
    from contextlib import closing
    with closing(sqlite3.connect(f"file:{source}?mode=ro",uri=True,timeout=45)) as live:
        with closing(sqlite3.connect(dest,timeout=45)) as copy:
            live.backup(copy)
            copy.commit()
    with closing(sqlite3.connect(dest)) as checked:
        integrity=checked.execute("PRAGMA quick_check").fetchone()[0]
    print(label,dest.stat().st_size,"quick_check=",integrity)
    if integrity!="ok": raise SystemExit("STOP: backup failed verification")
user=pwd.getpwnam("ubuntu")
os.chown(folder,user.pw_uid,user.pw_gid)
for dest in folder.iterdir(): os.chown(dest,user.pw_uid,user.pw_gid)
print("BACKUPS VERIFIED",folder)
PY

echo "===== SAVE SOURCE ROLLBACK ====="
git branch backup/pre-v39-scalability-20261009 HEAD
echo "===== FAST FORWARD AND VERIFY ====="
git merge --ff-only FETCH_HEAD
test "$(git rev-parse HEAD)" = "$TARGET"
venv/bin/python -m py_compile \
    poller.py services/history_service.py \
    services/durable_audit_queue_v39.py \
    web/app.py web/v38_revision_fingerprint.py \
    web/catalog_cache_v38.py

echo "===== INSTALL BOUNDED BACKGROUND WORKER ====="
sudo install -m 644 deploy/systemd/torn-fren-routine-audit.service \
    /etc/systemd/system/torn-fren-routine-audit.service
sudo install -m 644 deploy/systemd/torn-fren-routine-audit.timer \
    /etc/systemd/system/torn-fren-routine-audit.timer
sudo mkdir -p /etc/systemd/system/torn-fren-web.service.d
printf '[Service]\nEnvironment=TORN_FREN_V38_CATALOG_CACHE=1\nEnvironment=TORN_FREN_V38_REVISION_CACHE=1\n' \
  | sudo tee /etc/systemd/system/torn-fren-web.service.d/v39-source-cache.conf >/dev/null
sudo systemctl daemon-reload
sudo systemd-analyze verify \
    /etc/systemd/system/torn-fren-routine-audit.service \
    /etc/systemd/system/torn-fren-routine-audit.timer

echo "===== RESTART ONLY V37 POLLER AND WEB ====="
sudo systemctl restart torn-fren-poller.service
sudo systemctl restart torn-fren-web.service
sudo systemctl enable --now torn-fren-routine-audit.timer

echo "===== INITIAL HEALTH (NO NEW CHAMPIONS) ====="
systemctl is-active \
    torn-fren-poller.service torn-fren-web.service \
    torn-fren-bot.service torn-fren-gap-recovery.timer \
    torn-fren-routine-audit.timer
venv/bin/python - <<'PY'
from services.history_service import get_collector_recovery_status
from services.durable_audit_queue_v39 import status
print("Collector:",get_collector_recovery_status())
print("Routine audit queue:",status())
PY
curl -fsS --max-time 15 -o /dev/null \
  -w 'Website catalog HTTP %{http_code} in %{time_total}s\n' \
  http://127.0.0.1:8000/api/catalog
echo "===== DEPLOY FINISHED; WATCH FOR 30 MINUTES BEFORE SHADOW EXPANSION ====="
git log -1 --oneline
