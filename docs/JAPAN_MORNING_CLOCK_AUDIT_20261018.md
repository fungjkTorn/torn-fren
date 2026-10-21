# Morning clock audit — October18,2026

The clock logging activated around00:11EDT worked overnight. A sealed sanitized snapshot through1792327680 (08:48EDT) contained1,034 Japan country receipts spanning8.608h. Receipt gaps ranged19–40sec with no gap>180sec. This is selected-country logging, not two-source polling on every attempt or certified per-item/game freshness.

YATA:1,007receipts, report age at receipt median40sec/p9072sec/max172sec; Prometheus:27receipts, median10sec/p9045.4sec/max87sec. Both had29items reported in every sampled country payload. No within-provider update-clock regressions; there were26 selected-provider switches and six switches to an older reported country timestamp. Country item count29 does not certify that Xanax appeared in every payload. Do not infer that these switches caused the149min prediction errors.

Since first logged receipt, strict history accepted two complete cycles, two clean zero halves and four clean positive halves. Newest accepted whole cycle was about0.99h old at cutoff. Logging did not change the original history acceptance rules, so these are newly observed clean intervals, not a model-accuracy gain attributable to logging. The latest24h audit has80completed cycles versus78before, with150/288READY and138unknown physical-phase issues. The clock data does not retroactively label older provider switches.

Private run39130591124, source dbe08738c9633c067379c20bea2dcf2ca0895515, artifact12138106384; ZIP SHA256 d3a0d71285cb2ed6853dc01f22f2b8b6fc3b5cc1485569d2679a7f1c6051f123 verified before extraction. Four clock-audit tests and all public compatibility workflows passed. Read-only research, no collector/model changes. This is not a live-flight accuracy report.

## Score the completed all24 shadow journal now

The owner VM holds the journal; the isolated research snapshot intentionally does not export it. No new model run or collection restart is needed to score its already recorded frozen plans. Run in the UbuntuVM terminal:

```bash
(
set -euo pipefail
cd "$HOME/torn-fren-country-clocks-1304b3580bf9"
export TORNFREN_REPLAY_WORK="$PWD"
export TORNFREN_REPLAY_PINNED_RESEARCH="$PWD/research"
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
"$HOME/torn-fren-shared-canary-00bbfa9355bc/.venv/bin/python" -B \\
  -m research.japan_xanax.renewal_shadow score \\
  --source /opt/torn-fren/data/stock_history.db \\
  --journal "$HOME/torn-fren-full-roster-shadow-20261017T164459Z.sqlite" \\
  --model-sha e8df776b1d8a07c5ec520118b7f9493f55ce2361 \\
  --progress
)
```

The newer scorer reads the old producer journal, validates its identity and reports scorer_sha separately. Progress is printed per item on stderr. This compares eight recorded shadow variants for all24 items; it is not a new champion assignment or automatic release decision. Original journal lacks per-plan source clocks; frozen arrival scoring remains available, but source-fresh replanning cannot be reconstructed as fact. Hourly cohorts are correlated. The separate Japan paired-handoff journal can still be scored with its original pinned command; incomplete recorded waiting followup must remain pending even after arrival truth matures.
