# V30 native parity provenance checkpoint — 2026-10-08

**No main merge, no VM deployment. V30 is a research diagnostic, not a champion promotion.**

## Exact-source discovery

The original V21 `full_master(1).json` embeds:
- `settings.db_sha256 = 9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`

The newer VM snapshot used in V28's local replay is:
- `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`

**These are different DBs.** V19/V20 master files generally do not embed their input DB SHA; their `db_path` refers to `C:\\Users\\fungb\\Desktop\\torn-fren\\data\\torn-fren-stock-history-fresh.db`, not the later VM database.

The 33/42 exact departure agreement from V28 therefore **cannot be called same-input native parity**. In addition, it came from a self-contained local compatibility port, not the original engine modules, which further disqualifies an exact-engine claim.

### Four affected item/version cohorts (nine mismatches)

| Item | Version | Previously matched | Departure errors in seconds |
|---|---|---|---|
| Argentina Monkey Plushie | V19 | 0/3 | +4800, +4800, +300 |
| Argentina Tear Gas | V20 | 0/3 | +1500, +1500, +1200 |
| China Peony | V19 | 1/3 | -3000, -2700 |
| UK Red Fox Plushie | V20 | 2/3 | +300 |

The other ten tested item/version cohorts matched all saved starts (33/42 overall). We tested two independent local-port changes (remove V19-only scored-label gap restriction, and switch to cycle-window rather than observed-interval labels); **neither closed these nine mismatches**. They are not verified code bugs.

Original model snapshot counts also differ materially from the later DB. Example: `arg:Monkey Plushie` saved V19 `cycles=694`, `historical_points=3133`, `provider_bounces_suppressed=39`; newer reconstructed port `cycles=745`, `historical_points=3263`, `bounces=43`. These are incompatible prepared feature sets.

## V30 safeguard implementation

- New `research/v30_native_parity_probe.py` calls **original versioned planner code**, never the V28 research port. It validates original result schema, uses original V18.1/V19 engine family, original frozen config, original historical simulation rules, deterministic label-blind sample starts, complete denominator and strictly read-only SQLite.
- Before execution, compare tested DB SHA to the original master `settings.db_sha256`. If missing or different, report `UNKNOWN_SOURCE_DB_HASH` / `CROSS_SNAPSHOT` and **refuse to claim parity**. `--force-cross-snapshot-diagnostic` allows only explicitly labeled non-certifying exploratory comparisons.
- Enhanced `research/v25_release_gate.py` with required `same_source_db_verified` flag for public model activation, in addition to native parity and causal prefix-invariance.
- GitHub Actions V30 source-provenance CI passed 9 provenance/test-contract tests + 1 true native-engine synthetic SQLite integration test (V19, V20, V21 paths) + 14 release-gate tests. The native integration test executes original planner code and verifies the source SQLite digest stays unchanged; synthetic stock accuracy is not predictive validation. Separate V25 guard job passed 14 + 10 tests.

### To run genuine native parity when original frozen source DB is available

From the repository root on the V30 research branch:

```powershell
python -u -m research.v30_native_parity_probe `
  --db "data\torn-fren-stock-history-fresh.db" `
  --v19 "data\all_item_v19\master.json" `
  --v20 "data\weak_item_v20\master.json" `
  --v21 "data\all_item_v21\full_master.json" `
  --only "arg:Monkey Plushie" `
  --only "arg:Tear Gas" `
  --only "chi:Peony" `
  --only "uni:Red Fox Plushie" `
  --max-rows 3 `
  --output "data\v30_native_original_parity.json"
```

**First verify that the original source DB hashes to the V21 embedded digest**. The original `torn-fren-stock-history-fresh(3).db` appears in this project's Library (approx 126MB), but attempts to materialize its original binary bytes into this runtime failed with a raw-byte authorization error. It **has not been run here**. The only locally mountable SQLite in this session is the newer 134MB VM snapshot.

Never add the DB to GitHub, commit API keys, or merge research PRs to main in order to perform this comparison.

## Remaining next stages

1. Obtain authorized byte access to the archived original source DB, verify SHA, run the exact native four-cohort parity probe; review all differing rows and feature fingerprints.
2. Use a later untouched snapshot for genuinely prospective all-start success across independent stock windows. The October 5–8 sample has been inspected and is no longer a lockbox.
3. Build real item-specific live adapters and score side-by-side V2/champion forecasts with source freshness, gap suppression, no-abstention accounting, and rollback. V29 private endpoint still shows V2 only, not challenger inference.
4. Keep all item entries `RESEARCH_ONLY_BLOCKED` until the release gate independently passes.

