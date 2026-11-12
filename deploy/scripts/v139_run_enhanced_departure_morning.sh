#!/usr/bin/env bash
# Safe, ONE-TIME V139 enhanced morning audit. No service install, timers or DB writes.
set -euo pipefail

EXPECTED_USER=ubuntu
[[ "$(id -un)" == "$EXPECTED_USER" ]] || {
  echo "STOP: audit operator must run as ubuntu"; exit 1;
}

WORK=/home/ubuntu/torn-fren-v38-probe
STAGE=/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research
COMMIT=142f10363037b31fc299183c7cfb0734cf7df50c
LIVE=/opt/torn-fren/data/stock_history.db
V128=/var/lib/torn-fren-v38/v128_earliest24_shadow.db
V75=/var/lib/torn-fren-v38/v75_private_predictions.db

echo "===== VERIFY APPROVED READ-ONLY INPUTS ====="
test -r "$LIVE" || { echo "collector DB inaccessible"; exit 1; }
test -r "$V128" || { echo "V128 sidecar missing"; exit 1; }
test -r "$V75" || { echo "older V75 sidecar missing"; exit 1; }
test -f "$STAGE/v128_full24_earliest_shadow.py" || {
  echo "V128 pinned stage not present"; exit 1;
}
test -x "$WORK/.venv/bin/python" || {
  echo "V38 virtual environment not present"; exit 1;
}

cd "$WORK"
git fetch origin research/v38-full-roster-live-prep-20261009
git cat-file -e "${COMMIT}^{commit}"

echo "===== STAGE ONLY PINNED READ-ONLY AUDIT CODE ====="
for module in \
  v129_full24_forward_report \
  v131_multiledger_historical_arrival_audit \
  v132_departure_timing_quality_audit \
  v133_private_departure_panel \
  v134_original_graph_v2_audit \
  v135_morning_departure_brief \
  v137_original_v2_stock_at_arrival_audit \
  v138_enhanced_departure_evidence_brief
do
  git show "${COMMIT}:research/${module}.py" > "$STAGE/${module}.py"
  python3 -m py_compile "$STAGE/${module}.py"
done

echo "===== V138 ORIGINAL GRAPH / DIRECT ARRIVAL / V75 / V128 / DEPARTURE QUALITY ====="
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

nice -n 19 timeout 300s "$WORK/.venv/bin/python" -c '
import importlib
from pathlib import Path
import research

stage=Path("/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research").resolve(strict=True)
research.__path__=[str(stage), *[str(x) for x in research.__path__ if Path(x).resolve()!=stage]]
importlib.invalidate_caches()
for name in (
    "v129_full24_forward_report",
    "v131_multiledger_historical_arrival_audit",
    "v132_departure_timing_quality_audit",
    "v133_private_departure_panel",
    "v134_original_graph_v2_audit",
    "v135_morning_departure_brief",
    "v137_original_v2_stock_at_arrival_audit",
    "v138_enhanced_departure_evidence_brief",
):
    module=importlib.import_module("research."+name)
    assert Path(module.__file__).resolve().parent==stage,name
from research import v138_enhanced_departure_evidence_brief as v138
v138.main()
'

echo "===== AUDIT DONE, NO MODEL OR DATABASE CHANGES ====="
