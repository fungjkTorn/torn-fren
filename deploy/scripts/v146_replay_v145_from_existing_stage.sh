#!/usr/bin/env bash
# V146 research-only offline same-issue V128/V145/V148 audit (not a deployment).
# Uses the same private research Python stage that the successful V139 audit
# already verified; only NEW v145/v146 source files are staged there.
# Never writes live collector, V128 sidecar, V75, website or timers.
set -euo pipefail
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: must run as ubuntu"; exit 1; }
WORK=/home/ubuntu/torn-fren-v38-probe
STAGE=/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research
VENV="$WORK/.venv/bin/python"
PIN=4c1febf6919a048a616f298a71c212a5fb04f66c
LIVE=/opt/torn-fren/data/stock_history.db
V128=/var/lib/torn-fren-v38/v128_earliest24_shadow.db

for target in "$WORK/.git" "$STAGE/v128_full24_earliest_shadow.py" \
              "$VENV" \
              "$LIVE" "$V128"; do
  test -e "$target" || { echo "STOP missing input: $target"; exit 1; }
done
test -x "$VENV" || { echo "STOP: venv Python unavailable"; exit 1; }
test -r "$LIVE" && test -r "$V128" || {
  echo "STOP: approved read-only evidence unavailable"; exit 1;
}
test ! -L "$STAGE" || { echo "STOP: stage is symlink"; exit 1; }

cd "$WORK"
git fetch -q origin research/v38-full-roster-live-prep-20261009 2>/dev/null
git cat-file -e "${PIN}^{commit}"
for module in v145_provider_continuous_phases v148_observed_earliest_stock_cycle v150_stock_window_failure_diagnostic v151_stable_earliest_departure v152_first_restock_timing_evidence v153_recent_completed_restock_baseline v146_v145_same_issue_replay v149_v146_compact_report; do
  test ! -L "$STAGE/$module.py" || { echo "STOP: staged module symlink"; exit 1; }
  git show "${PIN}:research/${module}.py" > "$STAGE/$module.py"
  "$VENV" -m py_compile "$STAGE/$module.py"
done
echo "===== V151 CODE CHANGE: 60SEC VS 300SEC SAME-ISSUE DEPARTURE COMPARISON ====="
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OMP_NUM_THREADS=1
nice -n 19 timeout 240s "$VENV" - <<'PY'
import importlib
import json
from pathlib import Path
import research
stage=Path("/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research").resolve(strict=True)
research.__path__=[str(stage), *[str(x) for x in research.__path__ if Path(x).resolve()!=stage]]
importlib.invalidate_caches()
audit=importlib.import_module("research.v146_v145_same_issue_replay")
assert Path(audit.__file__).resolve().parent == stage
result=audit.replay(days=1,max_model_evals=96)
report=importlib.import_module("research.v149_v146_compact_report")
print(report.compact(result))
PY
echo "===== V146 REPLAY DONE; NO COLLECTOR, SIDECAR OR WEBSITE CHANGES ====="
