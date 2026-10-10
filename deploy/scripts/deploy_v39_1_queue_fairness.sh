#!/usr/bin/env bash
# Minimal v39.1 audit fairness hotfix, pinned to one CI-passing commit.
# Does NOT touch website/bot/shadow services, research workers or user keys.
set -euo pipefail
BASE="e9ba974c96553ea36f31951b94901b7379b22624"
RELEASE_REF="release/v39-priority-fairness-20261009"
TARGET="${1:-}"
cd /opt/torn-fren
if [[ ! "$TARGET" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: supply exact green 40-character release SHA" >&2;exit 2
fi
test "$(git branch --show-current)" = profitability-v1
test "$(git rev-parse HEAD)" = "$BASE"
test -z "$(git status --porcelain)"
git fetch origin "$RELEASE_REF"
test "$(git rev-parse FETCH_HEAD)" = "$TARGET"
git merge-base --is-ancestor HEAD FETCH_HEAD

echo "===== COLLECTOR AND WEBSITE HEALTH ====="
test "$(systemctl is-active torn-fren-poller.service)" = active
test "$(systemctl is-active torn-fren-web.service)" = active
test "$(systemctl is-active torn-fren-bot.service)" = active
test "$(systemctl is-active torn-fren-routine-audit.timer)" = active
test "$(systemctl is-active torn-fren-gap-recovery.timer)" = active
curl -fsS --max-time 15 -o /dev/null http://127.0.0.1:8000/api/catalog

echo "===== SAVE VERIFIED V39.1 PRE-RELEASE SQLITE SNAPSHOT ====="
sudo python3 - <<'PY'
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import os,pwd,sqlite3
src=Path("/opt/torn-fren/data/stock_history.db")
destdir=Path("/home/ubuntu/torn-fren-pre-v39-1")/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
destdir.mkdir(parents=True,exist_ok=False)
dest=destdir/"stock_history.db"
with closing(sqlite3.connect(src.as_uri()+"?mode=ro",uri=True,timeout=60)) as live:
    with closing(sqlite3.connect(dest,timeout=60)) as copy:
        live.backup(copy)
        copy.commit()
with closing(sqlite3.connect(dest)) as check:
    result=check.execute("PRAGMA quick_check").fetchone()[0]
if result!="ok": raise SystemExit("STOP: failed stock DB backup quick_check")
owner=pwd.getpwnam("ubuntu")
os.chown(destdir,owner.pw_uid,owner.pw_gid)
os.chown(dest,owner.pw_uid,owner.pw_gid)
print("VERIFIED",dest,dest.stat().st_size,result)
PY

echo "===== MINIMAL V39-DERIVED RELEASE DIFF ====="
git diff --name-status HEAD FETCH_HEAD
git branch backup/pre-v39-1-fairness-20261009 HEAD
git merge --ff-only FETCH_HEAD
test "$(git rev-parse HEAD)" = "$TARGET"
/opt/torn-fren/venv/bin/python -m py_compile \
    services/durable_audit_queue_v39.py services/history_service.py poller.py

echo "===== CORRECT WORKER SQLITE SANDBOX ====="
sudo install -m 644 deploy/systemd/torn-fren-routine-audit.service \
    /etc/systemd/system/torn-fren-routine-audit.service
sudo systemctl daemon-reload
sudo systemd-analyze verify \
    /etc/systemd/system/torn-fren-routine-audit.service

echo "===== MAKE NEW ATOMIC ENQUEUES USE FAIR AGES ====="
sudo systemctl restart torn-fren-poller.service
test "$(systemctl is-active torn-fren-poller.service)" = active
test "$(systemctl is-active torn-fren-routine-audit.timer)" = active
test "$(systemctl is-active torn-fren-web.service)" = active

echo "===== LOSSLESS TARGET PRIORITY MIGRATION ====="
venv/bin/python - <<'PY'
import time
from services.durable_audit_queue_v39 import promote_canary_pending
from services import history_service as hs
print("Promoted canary queue rows:",promote_canary_pending())
with hs._connect() as con:
    print("Queue:",con.execute("""
        SELECT status,priority,COUNT(*) FROM routine_audit_jobs_v39
        GROUP BY status,priority ORDER BY priority DESC,status
    """).fetchall())
    print("Target oldest age:",con.execute("""
        SELECT CAST(strftime('%s','now') AS INTEGER)-MIN(queued_at)
        FROM routine_audit_jobs_v39
        WHERE priority>=100 AND status IN ('pending','running')
    """).fetchone()[0])
PY
curl -fsS --max-time 15 -o /dev/null \
  -w 'Website HTTP %{http_code}; %{time_total}s\n' \
  http://127.0.0.1:8000/api/catalog
echo "V39.1 QUEUE FAIRNESS DEPLOYED, PUBLIC WEBSITE UNCHANGED."
echo "Observe audited job completion before activating private V38 research."
