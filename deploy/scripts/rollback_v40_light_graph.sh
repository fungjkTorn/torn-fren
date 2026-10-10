#!/usr/bin/env bash
# Source/config rollback only. Keep all stock, audit and research history.
set -euo pipefail
BASE="dd84271a40b6e5dac2551c9fbb1291f47463c057"
TARGET="${1:-}"
if [[ ! "$TARGET" =~ ^[0-9a-f]{40}$ ]]; then echo "Exact current SHA required" >&2; exit 2; fi
cd /opt/torn-fren
test "$(git branch --show-current)" = profitability-v1
test "$(git rev-parse HEAD)" = "$TARGET"
test -z "$(git status --porcelain)"
test "$(git rev-parse backup/pre-v40-light-graph-20261009)" = "$BASE"
sudo rm -f /etc/systemd/system/torn-fren-web.service.d/v40-web-light-graph.conf
git reset --hard "$BASE"
sudo systemctl daemon-reload
sudo systemctl restart torn-fren-web.service
for n in $(seq 1 30); do
  if curl -fsS --connect-timeout 2 --max-time 3 -o /dev/null \
      http://127.0.0.1:8000/api/catalog; then
    echo "Original V39.1 graph code restored. Stock and audits untouched."
    exit 0
  fi
  sleep 2
done
echo "Rollback completed but website has not recovered; inspect journalctl" >&2
exit 2
