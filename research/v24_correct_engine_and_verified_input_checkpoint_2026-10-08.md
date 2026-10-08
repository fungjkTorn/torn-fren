# V24 checkpoint: actual V19 engine identity and new-snapshot inputs

Date: 2026-10-08. **Research only. No live change or model promotion.**

## New primary artifact verification

The user uploaded the real frozen 140,181,504-byte newer VM SQLite snapshot; SHA-256 `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f43a02faf10a03d1359761`. This is the expected V24 checksum.

The uploaded research masters:
- V19 `master(7).json`: schema `all-item-dynamic-challenger-v19-master-v1`, SHA `e6569d46f02ac630b83020a66677f18aaa6722f9ce85f62415984580c993d664`, 236 item keys, 134 complete. **Stored individual item schema `plushie-flower-dynamic-planner-v18.1-item-v1`**.
- V20 `master(6).json`: schema `weak-item-targeted-tournament-v20-master-v1`, 187 item keys, 114 complete. **Individual engine schema v19**.
- V21 `full_master(1).json`: schema `all-item-v21-corrected-checkpoint-v1`, 170 item keys, 116 complete. **Individual engine schema v19**. V21's recorded V19 SHA matches the uploaded V19 file.
- V21 specialist `corrected_master(1).json`: ten complete entries exactly match the corresponding V21 full master entries, including config and full results. **Do not double count** this fourth file.

Across 236 item keys, 68 have all three models, 65 have exactly two, 30 exactly one, 73 none.

## Critical original-engine correction

Review of the historical `services/all_item_dynamic_tournament_v19.py` source showed V19 imports `services.plushie_flower_dynamic_planner_v18.worker`; the saved V19 item schema confirms v18.1. But our inherited V24 replay had been running V19's configs through `plushie_flower_dynamic_planner_v19`. This changes features and scoring: the newer engine uses additional cycle-sequence distances, different gap handling, and can produce different departures.

The V24 research branch now selects **v18 for V19** and **v19 for V20 and V21**, with explicit schema assertions. The same >=30 observed-stock truth and common post-cutoff starting sessions still score all versions. This is essential before any native champion comparison. The corrected branch has passed GitHub Actions compilation/unit suite, but **native replay against the uploaded DB has not been run with the complete original source in this environment**.

## Self-contained exploratory port on newer VM DB

A self-contained local compatibility port was executed on the original snapshot, with isolated all-start denominators and source-style plan/replan logic. It is **not** bit-for-bit equivalent to the GitHub native runner: some historical stored departure timestamps fail parity, and provider/cycle validation is simplified. Output is exploratory only, cannot establish exact original-engine head-to-head, or qualify for live model promotion.

Initial post-cutoff 12h clean-horizon samples:
- Canada Fire Hydrant, 36 shared starts: V19 dyn1 22/36 (61.1%), V20 dyn6 33/36 (91.7%), V21 dyn13 33/36 (91.7%), depart-now 14/36, exact hindsight 33/36. V20 vs V21 success tie; V20's median wait 240 min vs V21 277.5 min, but long waits are not themselves penalized.
- Argentina Tear Gas, 30 shared starts: V19 dyn7 6/30 (20.0%), V20 dyn3 2/30 (6.7%), V21 dyn5 9/30 (30.0%), depart-now 6/30, exact hindsight 30/30.

Sessions at 30-minute intervals are correlated. Historical native parity is not established; no winner is promoted. V22/V23 prior VM exposure means this snapshot also cannot count as wholly untouched prospective data.

## Native next steps

Use the research branch and original repo/venv on a machine with all four uploaded inputs, pointing at the frozen read-only SQLite copy:

```powershell
git fetch origin
git switch research/v24-replay-validation
git pull --ff-only
python -m py_compile services\frozen_champion_shadow_v24.py
python -m unittest discover -s tests -p "test_frozen_champion_shadow_v24.py" -v
python -u -m services.frozen_champion_shadow_v24 `
  --db "data\torn-fren-stock-history-latest.db" `
  --v19 "data\all_item_v19\master.json" `
  --v20 "data\weak_item_v20\master.json" `
  --v21 "data\all_item_v21\full_master.json" `
  --cutoff 1791241486 `
  --only "can:Fire Hydrant" --only "arg:Tear Gas" `
  --max-starts 12 --workers 2 `
  --output "data\frozen_champion_v24\native_smoke_v2_engine_correct.json" --resume
```

This is a read-only research run, not a live deployment. Before comparing models for promotion, verify that the exact V19 module and per-generation cadence match original settings, then hold out a future post-model-selection time period.
