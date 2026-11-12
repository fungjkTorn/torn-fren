# V151 code adjustment: preserve complete LOW->HIGH duration correlation

**Research only. No production/site/collector/V75 mutation.**

## Actual VM evidence preceding this change

The owner's last 24-item read-only replay reported 600 first-issued item-hour checks, V151 coarse 509 suggestions and 326/420 mature poll-state stock-at-arrival proxy hits (77.6%), versus V148 304/418 (72.7%). On 395 directly matched, mature V151-vs-V148 candidates, V151 won 56 unmatched successes and lost 37 (net +19). The optional 60-second V151 departure grid chose 92 earlier departures (no extra candidates), with 5 finer-only vs 2 coarse-only successful matched outcomes (net +3 of 414 mature paired). **Neither win/loss aggregate measures independent real player flights; correlated hour-level issue checks and source freshness caveats remain.**

First-next-completed-restock onset MAE remained 23.6 minutes over 344 historical scorable cases; V153 recent3/5/10 timings had worse MAE (~29.4/28.3/29.0 minutes on differently sized subsets) than V151. Japan Xanax still had **zero supported flights** and 24 issue checks where maximum scenario arrival-stock support stayed below the existing 0.60 gate. The evidence does NOT justify lowering the threshold, naming a precise expected flight success rate, or changing production.

## Specific modeling assumption being tested

Existing V151 independently resamples observed LOW (stock below 30) and HIGH (stock >=30) phase durations when simulating future restocks. This can produce synthetic LOW/HIGH combinations not observed as a single complete replenishment cycle. We have valid directly observed stock-phase starts/ends even through benign provider switches per V145, and both completed stocked and depleted window lists.

Updated **the existing research V151 engine** with optional `cycle_sampling="paired_complete"`:
- Pair one directly observed completed depleted period with the immediately adjacent observed completed stocked period, requiring exact matching endpoints. No inferring unobserved stock changes across provider contradictions or collector gaps.
- In a LOW current phase, condition observed LOW survival on its elapsed age and then use its matched HIGH lifetime. Once a new LOW period begins, bootstrap a whole (LOW, HIGH) pair. For a HIGH current phase, condition observed HIGH survival on age, then bootstrap complete future pairs.
- Require at least three directly completed LOW-to-HIGH pairs. If fewer, fail closed with `INSUFFICIENT_DIRECTLY_PAIRED_CYCLES` and no departure; preserve original independent V151 behavior as default with no regression.
- Preserve the .60 uncalibrated scenario support gate, +10s arrival grace, 5min future sustained-stock check, eight-hour departure plan, and five-minute replanning. The 60s departure-grid option can be combined later if the paired 5min challenger establishes a benefit.

The **read-only original-issue V146 replay** now computes the paired version at the same frozen issue time as default V151, direct V151-vs-V148, and 60s vs 300s scans. Pair model candidate outcomes are scored with the exact same future poll-state proxy function, and only mutually mature observed outcomes count in a paired win/loss. The first completed future stocked period is also shared in a strictly held-out timing-MAE comparison to test whether pairing improves first-next-restock onset rather than simply increasing publication coverage.

## Decision gate

Only consider promotion if paired-cycle approach materially improves **both** coverage/arrival vs the independent V151 **on matched mature issue cohorts** and has acceptable stock-restock timing, sample diversity, and waiting behavior. If insufficient matched pairs for flowers, keep independent candidate rather than force a fit. Explicit outcome unknowns, source freshness, Japan Xanax survival and independent restock episodes require separate forward confirmation.

## Website/source preservation

Both original V2 stock graph and 24-item experimental dashboard remain unchanged; no model worker, timer, source database, production branch, or real gameplay action is changed. Any eventual rollout should use the exact deployed-source-pinned reversible additive bridge, not replace the original two views.
