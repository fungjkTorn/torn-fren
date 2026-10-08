# V24 replay validation checkpoint — 2026-10-08

**Scope:** Research-only safety and measurement fixes on branch `research/v24-replay-validation`; no collector, website, Discord, live predictions, or production model promotion.

## Source review findings

1. The inherited `services/frozen_champion_shadow_v24.py` contained a literal `\\n` in the Python settings dictionary, preventing module compilation. Replaced it with a real line break.
2. The V24 paired result originally intersected only rows where every model produced a recommendation. This can inflate apparent success by excluding skipped hard sessions. Schema `frozen-champion-v24-new-data-shadow-v2` instead stores **every eligible shared start** and reports per-model all-start success, coverage, conditional success, session caps, and asymmetric paired wins/losses. Missing recommendations are not silently excluded.
3. The V20 source script's default replan cadence is **900 seconds**, whereas the inherited V24 runner used 300 seconds. The saved V20 master records a **300-second departure grid**, but does not record its historical replan cadence. The replay now defaults to 900s, accepts `--v20-replan-seconds`, records the actual value, and explicitly flags its source as a default rather than proven original invocation.
4. Native-policy/settings compatibility checks now reject V20 departure-grid and V21 policy mismatches with recorded master settings.
5. Missing `torn_fren_matched_provisional_registry.json` no longer blocks **research-only all-master coverage**: `--registry` is optional. Without it, the union of V19/V20/V21 master keys is used, excluding specialist Japan Xanax, and no prior provisional winner is inferred.
6. Resume is intentionally incompatible with old V24-v1 output. Create a fresh V24-v2 output file instead of changing an existing checkpoint.
7. Regression tests added for all-start denominators, coverage, head-to-head counts, malformed start sets, and 900s V20 default cadence.

## Physical feasibility context from the frozen original 41-item audit

At >=30 quantity with +10s landing grace and a fully observed 12-hour departure horizon, **2,668 of 5,631 starting sessions (47.38%)** had any exact feasible departure. This is a hindsight oracle, **not** a realized model success rate or forecast confidence.

- 6 high-opportunity items (>=90% exact oracle): 1,317 of 1,319 starts were feasible.
- 6 medium (60–<90%): 436 of 626 starts.
- 25 low (>0–<60%): 915 of 2,926 starts.
- 4 zero: 0 of 760 starts.

Per-item suggested **candidate** departure grids based on *past completed* qualified-stock lifetimes (not a guaranteed model improvement):

| Item | Exact oracle | Median qualified interval | Past-lifetime suggested grid |
|---|---:|---:|---:|
| Argentina Tear Gas | 100% | 92 sec | 30 sec |
| China Katana | 99.1% | 152 sec | 60 sec |
| Argentina Compass | 100% | 762 sec | 120 sec |
| China Fireworks | 100% | 730 sec | 120 sec |
| Japan Kabuki Mask | 100% | 429 sec | 120 sec |
| Japan Sumo Doll | 100% | 543 sec | 120 sec |

Do not use finer departure grids indiscriminately; cost grows with number of candidates and may be expensive in V19's historical-neighbor scorer. Use coarse-to-fine local refinement after validating a causal proposal. Do not penalize necessary long restock droughts.

## V24-v2 smoke command (Windows PowerShell)

First copy the checksum-matching newer frozen SQLite snapshot into the project data directory. Never point at the live collector's writing DB. Ensure the master file paths match your PC. On the research branch:

```powershell
cd C:\Users\fungb\Desktop\torn-fren
.\venv\Scripts\Activate.ps1
git fetch origin
git switch research/v24-replay-validation
git pull --ff-only
python -m py_compile services\frozen_champion_shadow_v24.py
python -m unittest discover -s tests -p "test_frozen_champion_shadow_v24.py" -v
python -m unittest discover -s tests -p "test_stock_opportunity_geometry.py" -v
python -u -m services.frozen_champion_shadow_v24 `
  --db "data\torn-fren-stock-history-latest.db" `
  --v19 "data\all_item_v19\master.json" `
  --v20 "data\weak_item_v20\master.json" `
  --v21 "data\all_item_v21\full_master.json" `
  --cutoff 1791241486 `
  --only "arg:Tear Gas" --only "can:Fire Hydrant" `
  --workers 2 --max-starts 8 `
  --output "data\frozen_champion_v24\new_vm_master_v2_smoke.json" --resume
```

Optional: `--registry data\torn_fren_matched_provisional_registry.json` preserves the exact provisional catalog scope when available. The original newer VM frozen DB SHA256 requirement remains `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`. If the only DB available has a different hash, do not override the guard casually: freeze and document a new snapshot with a new cutoff first.

After smoke, use a **new output path** for 24+ starts / broader coverage. Report all-start success with honest denominators. Do not conflate arrival success with next-restock time error, calibration, or production readiness.

**Validation status:** Source edits and regression cases committed. Native project unit tests and the newer-data replay have not yet been executed in this environment because the frozen VM SQLite snapshot is absent. No revised V24 champions or improved success percentages are claimed.
