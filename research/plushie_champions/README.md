# Plushie champion research bundle

Research-only reproduction bundle for the item-specific plushie champions discovered on the October 2026 historical stock database. This directory is intentionally isolated from production code.

## Invariants

- quantity threshold: `>= 30`
- arrival success: stocked at landing or becomes stocked within `+10s`
- replanning cadence: `300s` (5 minutes)
- planning horizon: `28800s` (8 hours)
- collection gaps invalidate training/evaluation paths
- recommendations are causal: historical analogs/outcomes are only eligible after they are resolved before the query time
- no SQLite database or API credentials are committed

## Winning configurations

- Nessie: recent phase/template `(lookback_h=2, lags=(1,), shift_h=1, minfit=.5, recency_pow=1.0)` with the most recent 15% pre-holdout selection window.
- Red Fox: global-regime analog `k=18`, `global_regime_weight=.5`.
- Lion: expert A `(k=14, gw=.35)`, expert B `(k=18, gw=.5)`, logistic selector.
- Panda: expert A `(k=16, gw=.15)`, expert B `(k=18, gw=.75)`, ExtraTrees selector `depth=3`, `min_samples_leaf=3`.
- Monkey: 24-template expert bank, online resolved-performance selector, 2-day window.
- Chamois: same bank, 3-day window.
- Camel: same 24-template bank, select the current recommendation with the highest predicted plan probability.

The historical development scores associated with these configs are documented in the project handoff. They are not treated as pristine final lockbox claims because the Oct holdout was repeatedly inspected during research.

## Run

From the repository root:

```bash
python -m pip install -r research/plushie_champions/requirements-research.txt
python research/plushie_champions/replay.py --db /path/to/torn-fren-stock-history.db --target all
```

Or run a single script directly, for example:

```bash
python research/plushie_champions/rf_localgrid.py --db /path/to/torn-fren-stock-history.db
python research/plushie_champions/checkpoint4_online_selector.py --db /path/to/torn-fren-stock-history.db --target monkey
```

These scripts are for the all-item champion tournament to reproduce and compare incumbents before live integration. They do not modify production services.
