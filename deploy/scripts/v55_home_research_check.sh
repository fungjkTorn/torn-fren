#!/usr/bin/env bash
# V55 read-only health and V50-V54 test suite after guarded research update.
# Usage: bash deploy/scripts/v55_home_research_check.sh
# Does NOT touch/restart/enable/disable production or research services.
set -euo pipefail
ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
SITE=http://127.0.0.1:8000/api/experimental/v41/predictions

cd "$ROOT"
test "$(id -un)" = ubuntu
test -x "$PY"
echo "=== RESEARCH CHECKOUT ==="
git log -1 --format='%h %s'
test -z "$(git status --porcelain)" || {
  echo "STOP: Research checkout contains uncommitted modifications"
  exit 1
}

echo "=== ACTIVE TIMERS (V44/V48 SHOULD BOTH REMAIN ACTIVE) ==="
for unit in torn-fren-v38-private-shadow.timer torn-fren-v48-cache-warmup.timer; do
  if systemctl is-active --quiet "$unit"; then
    echo "$unit: active"
  else
    echo "STOP: $unit inactive; do NOT assume cached research running"
    exit 1
  fi
done
echo "=== SOURCE-PINNED RED FOX OVERLAY ==="
systemctl show torn-fren-v38-private-shadow.service -p ExecStart --no-pager |
  grep -q -- '--with-redfox' || {
    echo "STOP: 19-model research overlay not configured"
    exit 1
  }

echo "=== V50–V54 TESTS ==="
PYTHONPATH="$ROOT" "$PY" -m unittest discover -s tests -p 'test_v5*.py' -q

echo "=== LATEST PRIVATE RESEARCH API (NO WRITES) ==="
"$PY" -c 'import json,urllib.request
url="http://127.0.0.1:8000/api/experimental/v41/predictions"
with urllib.request.urlopen(url,timeout=8) as resp:
    rows=json.load(resp).get("latest",[])
keys={x.get("item_key") for x in rows}
print("item snapshots:",len(rows),"red fox:", "uni:Red Fox Plushie" in keys)
from collections import Counter
print("status counts:",dict(Counter(x.get("status") for x in rows)))
if len(rows)!=19 or "uni:Red Fox Plushie" not in keys:
    raise SystemExit("STOP: expected existing 19 snapshots, no promotion attempted")'

echo "=== V48 CACHE COUNTS ==="
"$PY" -m research.v48_cache_warmup --status
echo "=== COMPLETED: read-only checks only, V44/V48 timers untouched ==="
