# Japan agreeing-zero provider handoff experiment v1

Forecast-gap audit run39053949785 reproduced451 forecast and413 no-forecast
issues on the fixed recent three days. Every missing forecast was UNKNOWN_PHYSICAL_PHASE
following PROVIDER_SWITCH; there were140 provider switches in the issue window.
No missing forecast was attributed to sample count, phase survivors or low support.

Preserve completed training tuples exactly as accepted by the strict baseline.
Maintain a separate candidate current-zero anchor only after an observed
positive-to-exact-zero transition within one provider and without collection gap.
At a provider handoff preserve that anchor only if both adjacent stock states
are exactly zero, no observed collection gap crosses the handoff, and elapsed
observed time <=60,180 or600 seconds respectively. A fourth variant permits up
to24h of unchanged zero state only if successful global polls continuously cover
that interval, with no >180sec poll gap or stale endpoint; polls after the handoff
cannot approve it. Global poll health is not provider-specific clock certification.
This longer variant is exploratory and must not be silently enabled in production.

No initial zero, <=30 threshold, cross-provider positive->zero, zero->positive,
provider disagreement, nonincreasing timestamps or collection gap creates an
anchor. Positive stock clears this candidate anchor. Borrow the candidate current
phase only when strict baseline lacks one and current observed quantity is zero.
Never concatenate provider histories for completed training or fabricate restocks.

Fixed development issues1791956700..1792215600, truth cutoff1792254014, default
expected baseline391/467 with467/864 departure coverage. Compare all four
handoffs to strict sequence, rate and leave-now controls. Preserve five-minute
replanning, eight-hour wait,15-second publication floor, exact-zero depletion and
>=30 stock through arrival+10sec. Report daily rates, paired changes, unknowns,
waiting, distinct departures and restored issue counts. This is targeted research
on an inspected window; improvement needs fresh validation and provider-clock
review before actionable release. Ongoing24-item VM test remains unchanged.
