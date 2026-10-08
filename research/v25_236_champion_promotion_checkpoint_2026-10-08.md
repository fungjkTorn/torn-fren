# Torn Fren V25 — 236-item champion selection, shadow testing, and Japan Xanax pilot

**Research branch only. No live routing, Discord commands, or game actions are changed.**

## Current basis
The 236-item candidate registry selected provisional historical champions:
65 V19, 14 V20, 74 V21, 30 depart-now high-stock baselines, 24 sparse fallbacks, 28 historically below requested quantity 30, and 1 separate Japan Xanax specialist. There are 80 >=90% and 19 80-90% historical candidates with at least 30 evaluated starts; **these are consulted historical holdouts, not a prospective model success guarantee**.

The separate plushie/flower research contributed 20 targeted holdout runs (11 V19/dyn and 9 V20/traj, 11 distinct items). Those samples cannot be treated as matched against the all-item master. Keep all 21 standard flower/plushie keys and compare each specialist on the same future timestamps. Preserve Japan Xanax as an independent model family.

Detailed 236-item manifest, 21-item comparison, evidence README, and read-only selection gate are included in the external V25 ChatGPT research ZIP; do not reconstitute their percentages as independently validated live success odds.

## Immediate tournament
1. Native V24 runner parity first (V19 = V18.1 original engine; V20/V21 = V19 engine). Use frozen newer VM DB checksum `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`.
2. Iterate all available 236 catalog keys, with a common fully observed lookahead, gap censorship and honest no-recommendation failures. Record each winner only provisionally. Required quantity 30, +10 second arrival grace unless the player's chosen quantity differs.
3. Separately replay executable flower/plushie specialists, V22/V23 analog experiments, and Japan Xanax when model source code and exact configurations are available.
4. Freeze finalists and collect prospective *independent* forward evidence. Overlapping half-hour decisions do not equal independent stock events.
5. Start with read-only private/shadow evaluation, with V2 prediction fallback and a feature flag default OFF. Public per-item routing only after separate audited acceptance and rollback drills.

## Japan Xanax tonight
The existing website currently displays **LEAVE BY**, countdown, target-arrival estimate, first/next projected cycle, reliability class, and 149-minute PI + pilot flight ETA. A visit to Japan → Xanax tonight is a legitimate **existing V2 baseline** shadow trial; it is NOT a live V8 rolling Ridge trial unless the specialist adapter is separately integrated and identified.

Snapshot the screen and record forecast view timestamp, current stock, desired quantity (research uses 30), prediction #, projected/observed marker, reliability warning, leave-by and arrival timestamps. At actual arrival record quantity immediately and through +10 seconds. Record failures and no-recommendation situations too. Do not invent or fix tonight's departure time from yesterday's DB.

Japan V8 rolling Ridge historical frozen result was 13/21 exact on a subsequently consulted sample; later development-tuned results were reported at 16/21 on those same 21, **not an untouched prospective result**. No per-trip numeric confidence without a calibration study.

## Release gate
Run `python -m research.v25_release_gate --evidence path/to/your_evidence.json --target public_live_guidance`. The gate defaults to failing when source hash, native replay parity, independent prospective starts/events, coverage, freshness/gap handling, fallback, flags or rollback are unproven. Private shadow has lighter requirements but still requires a working Japan-specific live-departure adapter if that model is shown. The gate itself neither loads a model nor alters a live website.

**Main / live**: defer until V24 PR #3 and this V25 research change have validated native comparison and fresh evidence. Never silently replace V2 or claim all 236 reach 90%.
