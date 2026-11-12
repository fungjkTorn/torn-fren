#!/usr/bin/env bash
# Opt-in V40 lightweight graph. No DB replacement, no bot or poller restarts.
set -euo pipefail
BASE="dd84271a40b6e5dac2551c9fbb1291f47463c057"
REF="release/v40-light-graph-20261009"
TARGET="${1:-}"
if [[ ! "$TARGET" =~ ^[0-9a-f]{40}$ ]]; then echo "STOP: exact CI-passing commit required" >&2; exit 2; fi
cd /opt/torn-fren
test "$(git branch --show-current)" = profitability-v1
test "$(git rev-parse HEAD)" = "$BASE"
test -z "$(git status --porcelain)"
for u in torn-fren-poller.service torn-fren-web.service torn-fren-bot.service \
    torn-fren-routine-audit.timer torn-fren-v38-private-shadow.timer; do
    test "$(systemctl is-active "$u")" = active
done
curl -fsS --max-time 15 -o /dev/null http://127.0.0.1:8000/api/catalog
git fetch origin "$REF"
test "$(git rev-parse FETCH_HEAD)" = "$TARGET"
git merge-base --is-ancestor HEAD FETCH_HEAD
backup="/home/ubuntu/torn-fren-before-v40-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$backup"
git rev-parse HEAD > "$backup/previous_git_head.txt"
sudo cp -a /etc/systemd/system/torn-fren-web.service.d "$backup/web-service-dropins"
git branch backup/pre-v40-light-graph-20261009 "$BASE"
git merge --ff-only FETCH_HEAD
test "$(git rev-parse HEAD)" = "$TARGET"
/opt/torn-fren/venv/bin/python -m py_compile web/app.py
/opt/torn-fren/venv/bin/python -m unittest discover -s tests -p test_v40_light_graph.py -q
sudo install -m 644 deploy/systemd/v40-web-light-graph.conf \
    /etc/systemd/system/torn-fren-web.service.d/v40-web-light-graph.conf
sudo systemctl daemon-reload
sudo systemctl restart torn-fren-web.service
echo "===== WAIT FOR HEALTHY WEB START ====="
ok=0
for n in $(seq 1 30); do
  if curl -fsS --connect-timeout 2 --max-time 3 -o /dev/null http://127.0.0.1:8000/api/catalog; then
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" -ne 1 ]; then
  echo "WEB START CHECK FAILED: remove v40 drop-in and restore prior code before continuing" >&2
  exit 2
fi
test "$(systemctl is-active torn-fren-poller.service)" = active
test "$(systemctl is-active torn-fren-bot.service)" = active
test "$(systemctl is-active torn-fren-routine-audit.timer)" = active
test "$(systemctl is-active torn-fren-v38-private-shadow.timer)" = active
curl -fsS --max-time 15 -o /dev/null \
  'http://127.0.0.1:8000/api/history?country=uni&item=Heather&minutes=60'
echo "V40 LIGHT GRAPH ACTIVE. Prior service configs saved at $backup."
