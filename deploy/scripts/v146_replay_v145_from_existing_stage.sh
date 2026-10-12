#!/usr/bin/env bash
# V146 research-only offline same-issue V128/V145 audit (not a deployment).
# Uses the same private research Python stage that the successful V139 audit
# already verified; only NEW v145/v146 source files are staged there.
# Never writes live collector, V128 sidecar, V75, website or timers.
set -euo pipefail
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: must run as ubuntu"; exit 1; }
WORK=/home/ubuntu/torn-fren-v38-probe
STAGE=/home/ubuntu/torn-fren-private-models/v128_stage/pinned/research
VENV="$WORK/.venv/bin/python"
PIN=945a570d65eccdd5df19fca67e53ca98ba70fe78
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
for module in v145_provider_continuous_phases v146_v145_same_issue_replay; do
  test ! -L "$STAGE/$module.py" || { echo "STOP: staged module symlink"; exit 1; }
  git show "${PIN}:research/${module}.py" > "$STAGE/$module.py"
  "$VENV" -m py_compile "$STAGE/$module.py"
done
echo "===== V146 READ-ONLY SAME-ISSUE PHASE-RECOVERY AND ARRIVAL PROXY ====="
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
print(json.dumps(result,sort_keys=True,indent=2))
PY
echo "===== V146 REPLAY DONE; NO COLLECTOR, SIDECAR OR WEBSITE CHANGES ====="
