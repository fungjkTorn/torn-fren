#!/usr/bin/env bash
# V151 paired LOW-HIGH model versus independent benchmark; no deployment.
# Uses the same private research Python stage that the successful V139 audit
# already verified; only research source files are staged there.
# Never writes live collector, V128 sidecar, V75, website or timers.
set -euo pipefail
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: must run as ubuntu"; exit 1; }
WORK=/home/ubuntu/torn-fren-v38-probe
STAGE=/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research
VENV="$WORK/.venv/bin/python"
PIN=afbac3d3b93203aafc5d905f80d7739aa9c52f69
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
for module in v145_provider_continuous_phases v148_observed_earliest_stock_cycle v150_stock_window_failure_diagnostic v151_stable_earliest_departure v152_first_restock_timing_evidence v153_recent_completed_restock_baseline v156_item_cycle_profile_router v157_prequential_stock_survival_router v158_flight_horizon_router v159_issue_phase_episode_audit v146_v145_same_issue_replay v149_v146_compact_report; do
  test ! -L "$STAGE/$module.py" || { echo "STOP: staged module symlink"; exit 1; }
  git show "${PIN}:research/${module}.py" > "$STAGE/$module.py"
  "$VENV" -m py_compile "$STAGE/$module.py"
done
echo "===== V159 CORRECTED PHASE-EPISODE GROUPING: FIXED CUTOFF NO-WRITE AUDIT ====="
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OMP_NUM_THREADS=1
nice -n 19 timeout 240s "$VENV" - <<'PY'
import importlib
import json
import os
import time
from pathlib import Path
import research
stage=Path("/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research").resolve(strict=True)
research.__path__=[str(stage), *[str(x) for x in research.__path__ if Path(x).resolve()!=stage]]
importlib.invalidate_caches()
audit=importlib.import_module("research.v146_v145_same_issue_replay")
assert Path(audit.__file__).resolve().parent == stage
raw=os.environ.get("REPLAY_ASOF_EPOCH")
if raw is None:
    asof=int(time.time())
elif len(raw)<=11 and raw.isdecimal():
    asof=int(raw)
else:
    raise ValueError("REPLAY_ASOF_EPOCH must be decimal Unix epoch")
if asof<=0 or asof>int(time.time())+5:
    raise ValueError("invalid or future replay cutoff")
print(f"===== FIXED READ-ONLY ASOF_EPOCH={asof}; DAYS=1; MC_BUDGET=96 =====",flush=True)
result=audit.replay(now=asof,days=1,max_model_evals=96)
assert result["asof_epoch"]==asof
report=importlib.import_module("research.v149_v146_compact_report")
print(report.compact(result))
PY
echo "===== V146 REPLAY DONE; NO COLLECTOR, SIDECAR OR WEBSITE CHANGES ====="
