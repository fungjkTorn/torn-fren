# Country freshness and flight-lead findings — October 15, 2026

Country clock logging and sanitized export support are implemented and tested, but **not activated on the live collector**. The independent provider probe and historical uncertainty audits completed. No new model or departure policy was promoted.

## Findings that change the next experiments

1. **Persistent stale Japan country reports were not observed in the short probe.** Six successful samples per provider, 60 seconds apart, observed YATA Japan report ages 6–63 seconds and Prometheus 5–13 seconds. The additional two-sample probe observed YATA 9–72 seconds and Prometheus 8–21 seconds. These are reported country clocks, not per-item/game freshness verification, and cannot certify earlier historical labels.

2. **The rate forecaster’s same-event error is too large relative to the buying window to support a reliable precise clock.** At the 149-minute Japan horizon, 121 eligible ordinal event comparisons have median absolute error 472 seconds (7.9 minutes), 90th percentile 1,529 seconds (25.5 minutes), and median signed error −247 seconds. The completed >=30 buying-window median is 720 seconds (12 minutes). This is an observed diagnostic, not a mathematical accuracy ceiling or an instruction to add a 247-second offset. Earlier offset experiments failed.

3. **Provider provenance needs to stay visible.** Japan’s seven-day issue window has 414 provider switches in stock-delta rows, of which 15 coincide with positive/zero phase conflicts. At flight lead, 140 of 155 supported hourly intervals contain a provider switch, 24 contain a physical phase conflict, and 3 intersect a collection gap; counts overlap. Most switches do not conflict on physical phase. Strict no-switch cycle-count support is only 15 intervals, while V145-compatible ordinal timing admits 121 comparisons by allowing same-phase switches and rejecting gaps/conflicts. Neither count proves that a provider switch caused forecast error.

4. **The external Japan value is not ready as an upcoming-restock predictor.** YATA supplied no Xanax nextRestock field. Prometheus supplied 1792077300 (Oct 15 11:15:00 EDT) at receipts Oct 15 11:21:18 EDT and Oct 15 11:22:20 EDT, both with quantity 0. That value was 378 and 440 seconds in the past. Its semantics and accuracy remain unverified; no model consumes it and it never becomes an observed depletion/restock label.

## Fixed-horizon rate-model diagnostic across the eight items

Seven days of canonical UTC hourly issues, 168 per item, ending eight hours before the snapshot cutoff. These are fixed future query times, **not optimized departures, live flights or the selected item champions**. Model support, unknown evidence and positive prevalence differ, so the full counts accompany the summaries. Cohorts are correlated.

| Item | Flight min | Buying window min | Predicted availability precision | Availability recall | Balanced accuracy | Ordinal timing n | Absolute error p50 / p90 min |
|---|---:|---:|---:|---:|---:|---:|---:|
| arg:Monkey Plushie | 111.0 | 25.7 | 66.7% | 55.8% | 40.7% | 84 | 20.6 / 52.0 |
| chi:Panda Plushie | 160.0 | 31.1 | 64.9% | 62.2% | 44.5% | 72 | 24.7 / 58.0 |
| jap:Xanax | 149.0 | 12.0 | 21.4% | 21.4% | 56.7% | 121 | 7.9 / 25.5 |
| sou:Lion Plushie | 197.0 | 29.5 | 64.2% | 69.4% | 45.1% | 83 | 26.2 / 69.0 |
| swi:Chamois Plushie | 116.0 | 26.8 | 66.2% | 58.2% | 53.6% | 85 | 22.9 / 45.8 |
| uae:Camel Plushie | 180.0 | 27.5 | 62.2% | 67.0% | 48.6% | 81 | 17.0 / 46.9 |
| uni:Nessie Plushie | 106.0 | 27.6 | 69.4% | 65.4% | 47.0% | 85 | 29.1 / 74.1 |
| uni:Red Fox Plushie | 106.0 | 25.5 | 74.0% | 71.0% | 60.0% | 102 | 25.4 / 77.1 |

For Japan the 151 scored fixed-horizon stock checks include 3 true positives, 11 false positives, 11 false negatives and 126 true negatives. Only 14 checks actually saw available stock. An always-unavailable classifier would score 90.7% ordinary accuracy while missing every buying opportunity. The rate classifier has 21.4% positive precision and 21.4% recall at these fixed clocks. These are not the 39.5% reference departure-policy result from the earlier experiment.

## Japan lead-time profile

| Lead min | Scored stock checks | Positive precision | Positive recall | Ordinal n | Ordinal abs p50 / p90 min |
|---|---:|---:|---:|---:|---:|
| 0 | 149 | 100.0% | 100.0% | 145 | 7.2 / 11.6 |
| 15 | 151 | 71.4% | 66.7% | 142 | 7.4 / 12.0 |
| 30 | 151 | 50.0% | 40.0% | 139 | 7.5 / 13.0 |
| 60 | 148 | 42.9% | 46.2% | 134 | 7.3 / 16.9 |
| 90 | 149 | 45.5% | 33.3% | 129 | 7.9 / 17.9 |
| 149 | 151 | 21.4% | 21.4% | 121 | 7.9 / 25.5 |
| 180 | 148 | 22.2% | 30.8% | 117 | 9.2 / 27.0 |
| 240 | 148 | 22.2% | 28.6% | 110 | 12.9 / 30.8 |

At the Japan horizon, zero-cycle and hybrid same-event p90 errors are 20.6 and 25.8 minutes, respectively. Their availability precision is also poor at fixed query clocks. This audit identifies a long-lead timing problem across those clock families; it does not select a new departure model.

## Independent clock sample, all countries

Six observations per provider from Oct 15 11:08:38 EDT through Oct 15 11:13:40 EDT. No failed fetches or observed clock regressions. Ages are receipt minus provider-reported country update, in seconds.

| Country | YATA age min–max | Prometheus age min–max | Reports older than 180s (YATA / Prometheus) |
|---|---:|---:|---:|
| arg | 28–117 | 8–77 | 0 / 0 |
| can | 20–137 | 2–82 | 0 / 0 |
| cay | 41–105 | 4–111 | 0 / 0 |
| chi | 3–54 | 0–27 | 0 / 0 |
| haw | 21–82 | 0–11 | 0 / 0 |
| jap | 6–63 | 5–13 | 0 / 0 |
| mex | 27–163 | 0–237 | 0 / 1 |
| sou | 3–70 | 3–78 | 0 / 0 |
| swi | 4–61 | 1–52 | 0 / 0 |
| uae | 11–70 | 2–25 | 0 / 0 |
| uni | 5–72 | 1–13 | 0 / 0 |

One Prometheus Mexico sample was 237 seconds old while YATA Mexico stayed within 180 seconds across this short sample. This does not support switching every country wholesale to one provider. Country-level measurements should precede any source-selection change.

## Matching and measurement limits

The next-after-clock metric independently chooses each stream’s next event after a fixed target. A small error near that target can jump the comparison by a cycle. Its large errors must not be called same-event timing errors. The refined audit also pairs the kth predicted event after issuance with the kth observed event, allowing same-phase provider switches under existing V145 rules while rejecting collection gaps and phase conflicts. Observed event identities still depend on sampled source data, not exact in-game clocks.

The fixed-lead audit uses only state available at each issue. Issues end eight hours before truth cutoff. Forecast abstentions, unknown stock evidence, unmatched future events and provenance exclusions remain explicit. No historical country timestamps were invented: both snapshots contain 0 country-clock rows. New metadata will be useful only after the VM collector and installed exporter run the new code.

## Implementation, verification and activation

New append-only country logging records receipt, provider, country/export clocks and status even when quantity/price is unchanged. It preserves local stock-history timestamps and true depletion at exactly 0. Item-save failures roll back the country record. The exporter is backward compatible, allowlisted, bounded and atomic; a cap failure preserves the prior snapshot.

116 replay/application CI tests, Chromium interface checks, export-safety tests and all compatibility workflows passed for refined source `b5639a898114d1db567f16dd975a50138596c68f`. The minimal collector patch was applied to an isolated copy of the previous public source with an unrelated host edit and preserved that edit. No live DB writes or production restarts occurred.

The tested deployment payload is `5a4d546a7e17d3766ac503765373f2bdb3f3342c`. Activation requires the VM owner: the research runner cannot modify the live collector or privileged exporter, and those permissions should remain restricted. The design document contains the exact payload, minimal patch, host preflight and activation/rollback plan. Until activation, logging is **ready, not live**.

Routine approved source remains `a73adb6d786e0e7e710fcc99ec8c70e9e8319885`. Frozen forward protocol remains `87f4c6ee34f6ee598cbcc7daf93b9355f46bbd04` and its original dates.

## Evidence

Initial private run 38757670396, source `5a4d546a7e17d3766ac503765373f2bdb3f3342c`, snapshot Oct 15 10:49:02 EDT. Artifact 11983879246, 26,194 bytes, SHA256 `c2e9b21117d2542853ddae046210517057a793971c820751f1768f874189065f`.

Refined private run 38759536530, source `b5639a898114d1db567f16dd975a50138596c68f`, snapshot Oct 15 11:19:24 EDT. Artifact 11984957711, 38,020 bytes, SHA256 `e80f69e0a4cd6ca5e8dba8836af5a2eec2bba94ffba41215337b0d8f6173d12f`. Both digests verified before extraction.

The companion JSON retains both complete audits, both probes, all fixed lead rows and raw summary counts. Neither run is a clean new-model holdout or evidence of improved selected-departure success.
