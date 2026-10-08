# V31 private frozen-challenger adapter & forward-data readiness — October 8, 2026

**Research only. Do not merge to main, update the VM, or enable private shadow on a public website until explicitly approved.** Branch `research/v31-frozen-shadow-adapter`, draft PR #7, based on V30 draft PR #6.

## Added

1. `services/frozen_candidate_worker_v31.py`: executes an **actual original-versioned V18/V19 generic model** for one decision timestamp, without simulating any future gameplay. V19 uses the V18 engine, V20/V21 use the V19 engine and V21 analog outcomes use corrected observed quantity-at-arrival truth. A read-only connection and isolated subprocess prevent global `history_service` monkey-patching of the website process.
2. `services/private_challenger_adapter_v31.py`: gated by the existing V29 private token/flag **and** separate `TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED` (OFF by default). Requires a private DB path and corresponding frozen master file AND pinned SHA-256. Validates model family, config name, response identity, fresh data and timeout; caps child runtime at 35 seconds and suppresses private paths/errors.
3. `services/private_champion_shadow_v29.py` may now show a separately labeled research challenger proposal **inside the private endpoint**. It still returns the current V2 forecast unmodified as `baseline`; no changes to `/api/history`, Discord, travel, main or the VM.
4. `tests/test_v31_private_challenger.py`: synthetic SQLite integration invokes original V21 planning code; tests fresh heartbeat, stale heartbeat, future observation rejection, explicit collection gap, strict read-only DB, invalid master SHA, model identity mismatch, disabled shadow and baseline preservation.

### Key invariant

A private challenger proposal is **one single-tick departure suggestion**, not a validated eight-hour replanning simulation or calibrated success probability. Historical model policies may have 6h/12h horizons; when a generic version is used for flowers/plushies, the private comparison truncates options to 8h and labels that normalized research horizon. Specialist code for the seven distinctive plushies and Japan Xanax is **not yet attached as a live adapter**; the private service explicitly declares those families unsupported rather than substituting a generic model.

## Frozen master SHA-256 (from user-uploaded files)

| Version | Source file | Frozen master hash |
|---|---|---|
| V19 | `master(7).json` | `e6569d46f02ac630b83020a66677f18aaa6722f9ce85f62415984580c993d664` |
| V20 | `master(6).json` | `3caf736d13d947872f5f9a25feb445c6984e4ce989a5c4791ff7b175a2028be7` |
| V21 | `full_master(1).json` | `dadf6fbcb6c6b5f68ed39871bae7185a1e23e773948ffffacabc8aaeca7362f7` |

V21 embeds original DB SHA `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761` and V19 master hash `e6569d...`. V20 source DB digest is not cryptographically embedded in the master; this remains an explicit provenance qualification.

## Environment flags (documentation only; do NOT enable automatically)

```text
TORN_FREN_CHAMPION_SHADOW_ENABLED=0
TORN_FREN_CHAMPION_SHADOW_NATIVE_ENABLED=0
TORN_FREN_CHAMPION_SHADOW_TOKEN=<new long random private secret, never committed>
TORN_FREN_CHAMPION_SHADOW_DB_PATH=<frozen read-only or live collector database path>
TORN_FREN_CHAMPION_V19_MASTER_PATH=<master(7).json path>
TORN_FREN_CHAMPION_V19_MASTER_SHA256=e6569d46f02ac630b83020a66677f18aaa6722f9ce85f62415984580c993d664
TORN_FREN_CHAMPION_V20_MASTER_PATH=<master(6).json path>
TORN_FREN_CHAMPION_V20_MASTER_SHA256=3caf736d13d947872f5f9a25feb445c6984e4ce989a5c4791ff7b175a2028be7
TORN_FREN_CHAMPION_V21_MASTER_PATH=<full_master(1).json path>
TORN_FREN_CHAMPION_V21_MASTER_SHA256=dadf6fbcb6c6b5f68ed39871bae7185a1e23e773948ffffacabc8aaeca7362f7
```

The V31 worker checks whether it is being asked to replay a historical decision using data that contains future observations, returning `FUTURE_RECORDS_PRESENT`; for historical backtesting, use the separate versioned locked replay, never V31 single-tick live inference.

The default rollback is simply leaving or setting **either** shadow flag to `0`. No change to V2 behavior occurs even when the private endpoint is enabled.

## Independent stock-window readiness: newer Oct 8 snapshot

Read-only audit on `torn-fren-stock-history-latest(3).db` (SHA `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`), with model cutoff `1791241486` (2026-10-05 23:04:46 UTC). Counted full observed transitions from >=30 units to below 30, suppressing one-poll cross-provider bounces and dropping windows crossing known collection gaps. Partial/currently active windows were excluded.

| Completed stock windows since cutoff | Item count |
|---|---:|
| 0 | 109 |
| 1–2 | 51 |
| 3–7 | 29 |
| 8 or more | 47 |
| **Total items** | **236** |

Total postcutoff completed windows = **1,772**. Example heavily observed items: Argentina Tear Gas 128, Cayman Trout 73, Argentina Monkey Plushie 69, UAE Camel Plushie 69, China Panda Plushie 67, Cayman Stingray Plushie 66. These are **candidate independent stock windows**, NOT model recommendation success. They are retrospective already-inspected observations, not new untouched forward validation. Source collection timing remains imprecise around each transition; windows alone cannot establish prediction accuracy. These counts must **not** satisfy the model-frozen prospective release gate.

The chat artifact `V31_236_Independent_Stock_Window_Readiness.csv` contains the full 236-row audit; raw DB was not committed.


## Append-only prospective evidence capture

`research/v31_shadow_evidence_capture.py` now supports manual, separate-SQLite
capture of the **private** API JSON. It is strictly OFF by default: there is no
scheduler, public endpoint storage or live VM deployment. It captures only
explicitly whitelisted model identities, V2 and challenger departure/arrival
timestamps and missing recommendations. All raw API keys, token headers,
master paths and freeform response metadata are excluded.

Every snapshot must carry a **server-generated** `generated_at` timestamp.
The recorder checks that this timestamp is no more than 180 seconds behind
ingestion and never in the future. The unique index
`(experiment_id,item_key,tick_epoch)` enforces at most one observation per item
per five-minute decision tick, preventing retries from inflating the
denominator. Missing challenger proposals are still recorded. Entries remain
`resolution_status='PENDING'` pending an independent future truth-scoring
pipeline; **none of these records is counted as a successful prediction yet**.

Manual example after separately obtaining the private authenticated JSON:

```bash
python -m research.v31_shadow_evidence_capture \
  --snapshot /secure/path/private-shadow-response.json \
  --evidence-db data/research_shadow_decisions_v31.db \
  --experiment-id V31-private-pilot
```

The CLI does not accept a historical capture-time override, and the recorder
refuses to append its evidence table to a collector DB even if the collector
file has been renamed. No database (large or small) and no secrets were
committed to GitHub.

## Remaining release work

- Execute original-module native same-source parity against the 126MB archived `fresh(4).db` on an environment with both the archived database and checked-out versioned Python services. The 132/132 source-aligned result in V30 was a compatibility port, not this native execution; CI native smoke uses synthetic SQLite.
- Pin and deploy research-only masters to an **isolated**, token-protected private test VM and perform real V2-versus-generic champion single-tick shadow runs with cached results and explicit timeout/freshness metrics, plus a tested rollback. No VM change performed here.
- Implement specialist-specific live adapters (Nessie, Red Fox, Lion, Panda, Monkey, Chamois, Camel; Japan Xanax separately), and validate causal features without looking ahead.
- Collect *new* untouched stock data after V31 freeze, evaluate all-start coverage, success >=30 on arrival/+10s and at least eight **distinct resolved stock windows per item**, not just correlated launch starts. Do not claim numeric trip-success confidence without calibration.
- Keep all 236 provisional candidates tagged `RESEARCH_ONLY_BLOCKED` until all public release gates pass.
