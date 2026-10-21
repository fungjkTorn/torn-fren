# Physical event-aligned whole trajectories — 2026-10-15 UTC

Japan Xanax has a configured149-minute flight and a sampled median buying window around12 minutes. Its original completed-path70/80 variants abstained entirely; quantity-rate/current-phase approaches scored about32–36% on the inspected all-start replay. Chaining marginal median phase durations also loses cross-cycle variability. This experiment tests a different alignment of whole observed trajectories.

## Fixed variants before results

Four research-only departure policies, all items:
- zero_path_aligned_analog70: weighted analog support>=0.70;
- zero_path_aligned_analog50: weighted analog support>=0.50;
- zero_path_aligned_analog_peak: earliest eligible delay within0.03 of the maximum support, with a fixed minimum0.15;
- zero_path_aligned_recent_peak: same peak rule, equally weighted most recent64 eligible physical-phase anchors.

Support is uncalibrated historical agreement, NOT a future success probability. Peak variants are explicitly low-support diagnostics and have no deployment/readiness permission. A higher score obtained by a lower support gate does not itself establish reliability; same-start comparisons, coverage, waits, daily floors and offset sensitivity remain necessary.

## Construction and causal bounds

Historical anchors are observed same-provider physical positive→zero or zero→positive crossings; residual1–29 stock never starts the empty clock. Each anchor stores features knowable at that onset: initial batch quantity, preceding completed positive/zero duration, preceding-eight duration medians and UTC phase-onset sin/cos. Require at least3 completed phases of each kind.

At query issue, match the current physical phase and its EXACT elapsed age. Historical paths must still have been in that same phase at the aligned time and must not cross a collection gap between onset and aligned time. Use the most recent512 potential mature anchors, at least24 eligible; analogs use32 nearest fixed feature distances and exp(-sqrt(distance)) weights. These are alternative historical futures, not independent samples.

The historical path contains all real subsequent restocks, zero waits and buying windows, retaining cross-cycle dependence. Historical arrival bins are one minute wide. A whole-minute evidence check requires poll-backed known stock throughout its entire bracket, excluding hidden sellout/replenishment excursions, provider changes or collection gaps even if both endpoints look good. This conservative binning may miss brief opportunities.

A path can be used only after its aligned age+8h max wait+flight+60s bin+190s maturity allowance have ALL elapsed before the issue. Prefix invariance therefore holds when later truth arrives. Unknown bins remain unknown; require at least16 known paths and80% known weight. Three-bin smoothed support penalizes isolated peaks. Departures are evaluated every five minutes with180s source expiry and eight-hour maximum wait, on all five-minute starts plus UTC-hour/offset diagnostics.

## Verification and scope

Unit tests cover a synthetic repeatable narrow buying window reached after multiple cycles, exact elapsed phase age, residual positive stock, full-path maturity, future mutations, shorter snapshot invariance, unknown/stale abstention and ambiguous provider crossings. Synthetic success demonstrates mechanics, not real Japan accuracy. Integration tests preserve future-decision invariance, full/focused equality and separate restock/depletion audits.

Existing path algorithms, strong rate/hybrid references, and the causal selector expert roster are unchanged. Arrival-only policies do not borrow event-timing accuracy from the physical-zero reference forecast. The new comparator section pairs all aligned variants with local70/80 and shared-regime70/80 on the SAME all-start cohorts.

This is isolated research. The predeclared forward_window_v1.json remains pinned to87f4c6ee34f6ee598cbcc7daf93b9355f46bbd04 and must not be repinned to these new models mid-window. Any future validation of aligned models needs a separately declared protocol. No production route, collector or publisher assignment changes.
