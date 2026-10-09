#!/usr/bin/env bash
# Controlled rollback of SOURCE ONLY. Additive queue table is preserved.
# Usage: bash deploy/scripts/rollback_v39_cpu_scalability.sh <current-release-sha>
set -euo pipefail
EXPECTED_BASE="a93879d42808c7a2f7485b88b6393056d87d01c9"
CURRENT="${1:-}"
if [[ ! "$CURRENT" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: pass exact deployed SHA" >&2;exit 2
fi
cd /opt/torn-fren
test "$(git branch --show-current)" = "profitability-v1"
test "$(git rev-parse HEAD)" = "$CURRENT"
test -z "$(git status --porcelain)"
test "$(git rev-parse backup/pre-v39-scalability-20261009)" = "$EXPECTED_BASE"
echo "===== DISABLE NEW AUDIT/CACHING UNITS ====="
sudo systemctl disable --now torn-fren-routine-audit.timer
sudo systemctl stop torn-fren-routine-audit.service || true
sudo rm -f /etc/systemd/system/torn-fren-web.service.d/v39-source-cache.conf
sudo systemctl daemon-reload
echo "===== RESTORE VERIFIED ORIGINAL V37 SOURCE ====="
sudo systemctl stop torn-fren-poller.service torn-fren-web.service
git reset --hard "$EXPECTED_BASE"
sudo systemctl start torn-fren-poller.service torn-fren-web.service
systemctl is-active torn-fren-poller.service torn-fren-web.service
echo "ROLLED BACK SOURCE; preserved stock DB and additive queue history."
