# V29 pre-live checkpoint — native parity, private shadow, causal audit

Date: 2026-10-08. **Research only. DO NOT MERGE TO MAIN OR DEPLOY**.
Parent work: draft PR #5 atop draft #4 atop V24 native replay PR #3.

## Completed in this checkpoint

1. `services/private_champion_shadow_v29.py` and `web/private_shadow_v29.py` provide a private **read-only diagnostic** at `/api/research/champion-shadow`, disabled by default. A flag AND a long `X-Torn-Fren-Shadow-Token` secret header are required. No token in query parameters. Main `/api/history` handler and Discord paths are not modified.
2. Diagnostics identify the frozen 236-item candidate but do **not execute it**. If possible, they show existing V2 reference leave-by and arrival, explicitly labeled V2. Failures produce safe unavailable status, never a fabricated departure time. The V2 call uses `record_audit=False`.
3. The release gate now demands `causal_prefix_invariance_passed=True` as well as exact engine/native parity, prospective validation, coverage, independent resolved cycles, fallback and rollback. No model passes this automatically.
4. `research/v29_prefix_lookahead_audit.py` audits potential *future-dependent* tiny-restock filtering in original historical cycle validation. Existing `history_service._build_validated_cycles` compares each cycle's peak against all other completed cycles, including ones later than a simulated decision timestamp when running offline on a full database. A full future-containing snapshot may therefore affect historical replay selection. This rule is safe for contemporaneous *live* interpretation, but not inherently safe for historical simulation.
5. On frozen October 8 SQLite snapshot at cutoff `1791241486`, an approximate **raw-history** audit scanned 236 keys; it flagged one pre-cutoff cycle each in `can:Insulin` and `haw:Bushmaster Carbon 15` (2 total). This raw approximation does not replicate provider-bounce suppression or collector coverage, so it is **triage only**, not a native certification.
6. Original saved-configuration local compatibility parity remains 33/42 exact departures on five probed item keys: V19 10/15, V20 8/12, V21 15/15. No regression test result can convert these to 100%; native exact replay still needed.

## Private research API response contract

All private requests must provide `X-Torn-Fren-Shadow-Token` and have these environment values set on the host:
- `TORN_FREN_CHAMPION_SHADOW_ENABLED=1`
- `TORN_FREN_CHAMPION_SHADOW_TOKEN` — a new random secret of at least 32 characters, never committed
- Optional `TORN_FREN_CHAMPION_SHADOW_REGISTRY_PATH` — frozen 236-entry registry JSON

Example authenticated `GET /api/research/champion-shadow?country=jap&item=Xanax` returns candidate identity and V2 reference, with `champion_executed=false` and `candidate_promoted=false`. It **does not return a new specialist Japan Xanax prediction**. In the default state, route returns HTTP 404. Invalid credentials get HTTP 403, with no raw stack traces.

**Rollback:** unset `TORN_FREN_CHAMPION_SHADOW_ENABLED` or set to `0` and restart the service. The shadow endpoint becomes 404 without changing `/api/history` or bot behavior. Production rollback has not yet been exercised on the VM.

## Outstanding release blockers

- Run *original/native* V19, V20 and V21 engines on a fixed archival snapshot and obtain parity on held-out stored decisions, not only local port results. Verify original data availability and scorer semantics. Distinguish changed dataset from code mismatch.
- Implement rigorous historical `prefix-only` training/feature/label calculation, without full-future tiny-restock means or end-of-series leakage. Compare frozen policies on genuinely untouched future data, across independently resolved stock cycles with quantity >=30, arrival +10s, and full recommendation coverage.
- Implement proper item-specific live inference adapters. **The private diagnostic currently does not execute challenger models** and cannot replace existing V2 recommendations.
- Add first private on-VM shadow run with fresh collector data, staleness/gap gating and independently persisted candidate + V2 prediction snapshots, then verify rollback and all failure paths.
- Keep per-item default >=90% quality target. Any temporary 75% exception for Camel, Monkey or Chamois must be clearly marked lower confidence. No per-trip calibrated numerical chance without a calibration test.
- Japan Xanax research remains a separately governed specialist. A live recommendation displayed tonight still comes from V2 unless the specialist is separately integrated, tested and explicitly enabled.

All this work remains in `research/v27-plushie-native-finalization`, on draft PR #5. No user credentials, secrets, live collector databases or production changes committed.
