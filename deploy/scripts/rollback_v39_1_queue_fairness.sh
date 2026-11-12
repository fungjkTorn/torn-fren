#!/usr/bin/env bash
# Restore the original verified V39 source/unit without altering history data.
# Pass the exact currently deployed V39.1 source SHA. No data-file reset.
set -euo pipefail
BASE="e9ba974c96553ea36f31951b94901b7379b22624"
CURRENT="${1:-}"
if [[ ! "$CURRENT" =~ ^[0-9a-f]{40}$ ]]; then
 echo "STOP: pass exact deployed SHA" >&2;exit 2
fi
cd /opt/torn-fren
test "$(git branch --show-current)" = profitability-v1
test "$(git rev-parse HEAD)" = "$CURRENT"
test -z "$(git status --porcelain)"
test "$(git rev-parse backup/pre-v39-1-fairness-20261009)" = "$BASE"

echo "===== RESTORE EXACT PRIOR V39 SOURCE AND SERVICE UNIT ====="
sudo systemctl stop torn-fren-poller.service
git reset --hard "$BASE"
sudo install -m 644 deploy/systemd/torn-fren-routine-audit.service \
 /etc/systemd/system/torn-fren-routine-audit.service
sudo systemctl daemon-reload
sudo systemctl start torn-fren-poller.service
test "$(systemctl is-active torn-fren-poller.service)" = active
test "$(systemctl is-active torn-fren-web.service)" = active
test "$(systemctl is-active torn-fren-routine-audit.timer)" = active
echo "V39 source restored; stock/audit SQLite and V38 research untouched."
