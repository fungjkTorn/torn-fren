# Seven original plushie specialists are present in this checkout

**2026-10-21, research only.** Earlier `audit_incumbent_sources.py`
incorrectly treated seven original model files as missing because
`research/v38_roster.json` contains old root-level source paths while
the actual files are in `research/plushie_champions/`.

The user's PC deep scan on Desktop found all **seven** original script
filenames in the current `torn-fren-pc` clone (and older V78 training
clone). No recreation is needed. The amended audit finds the relocated
source paths without claiming any model was just validated.

## Found exact original program files

| Item(s) | Program |
| --- | --- |
| Monkey, Chamois | `research/plushie_champions/checkpoint4_online_selector.py` |
| Panda | `research/plushie_champions/panda_pair_selector_ml.py` |
| Lion | `research/plushie_champions/lion_pair_selector_ml.py` |
| Camel | `research/plushie_champions/camel_fast_selector.py` |
| Nessie | `research/plushie_champions/recent_phase_select.py` |
| Red Fox | `research/plushie_champions/rf_localgrid.py` |

`research/plushie_champions/common.py` is also present. These are
**flight-selection models**, not direct first/second/third physical 0→positive
restock clocks. Their original single-number holdout success cannot stand
in for two independent accuracy percentages. The legacy historical
cohort selection also differs from the later generic 30-day suite. Do
not rank these results against the four-clock tournament until matched
decision-time / stock-evidence replays are implemented.

Japan Xanax's original external file remains missing, but
`research/japan_xanax/renewal_shadow.py` is a separately available,
non-equivalent specialist-family research implementation. The V18/19/20
per-item versions also remain intact in `services/`.

## Offline Windows steps after GitHub updates

```powershell
cd "$env:USERPROFILE\Desktop\torn-fren-pc"
git fetch origin
git switch research/v38-full-roster-live-prep-20261009
git pull --ff-only origin research/v38-full-roster-live-prep-20261009
.\.venv\Scripts\python.exe -m pip install numpy==1.26.4 scikit-learn==1.5.2
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe .\scripts\audit_incumbent_sources.py
```

Run the launcher as a Python module or directly from `scripts/`; both
entry points are covered by a Windows subprocess regression test. Earlier
instructions used direct execution but omitted a package-import fallback,
which caused `ModuleNotFoundError: No module named 'scripts'`.
This has been fixed without requiring any `PYTHONPATH` edits.

**Smallest original-model smoke**:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_pc_original_specialists.py `
  --source .\historical_pc_data\stock_history_research.db `
  --item-key "uni:Nessie Plushie" --workers 1 --timeout-per-item 1800 `
  --output .\historical_pc_results\original-nessie-smoke
```

**Full seven-item legacy original replay, up to six CPU processes**:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_pc_original_specialists.py `
  --source .\historical_pc_data\stock_history_research.db `
  --workers 6 --timeout-per-item 7200 `
  --output .\historical_pc_results\original-seven
```

The full run may take much longer than generic clocks. Timeouts are
per-item and logged, and completed items are cached for resumption.
Requires only the existing sanitized 53 MB local SQLite file. Original
scripts now open that SQLite using `ResearchContext.build(db,readonly=True)`,
so the source DB is not opened for writing. The controller fingerprints
source and original script bytes; its output directory cannot be reused
against a different source/model commit.

The runner reports `legacy_result.json` and
`legacy_full_result.json` per item, plus aggregate `summary.json`.
It explicitly marks `separate_physical_restock_accuracy_measured=false`,
`directly_comparable_to_generic_30day_cohorts=false`,
`source_sqlite_readonly=true`, and `production_promoted=false`.
The original script outputs are legacy conditional holdout **flight**
success and coverage, not as-issued independent physical restock hit
rates and not actual player flights.

## Next engineering step

Build a *single matching retrospective issue tape* for incumbent and
baseline models, respecting five-minute decisions and at least 30 stock
through landing+10s; test already-stocked-inventory departures; score
physical next event vs **selected** ordinal and signed early/late
timing separately; compare conditional flight success, coverage, mean
wait, and distinct observed physical restocks. Match identical dates
and eligibility rules for all strategies. Retain item-specific champion
routing; do not promote automatically or alter VM production.
