# Next-six pre-live cleanup proposal

Discussion plan after the October 22–29 corrected replay. No runtime forecast
or deployment changes have been made as part of this review.

## Evidence behind the proposal

The selected native models and scheduling sequence pass the replay audit, but
known-arrival success is 71–77% for the five regular-cycle items. The direction
of misses is mixed. UK has continuous stock and one independent frozen trip.
Changes in travel incentives/event demand are plausible context, not an
established cause of any particular error.

The shared phase estimator correctly withholds a known phase onset following
ambiguous gaps/provider transitions. However, absence of a phase onset need not
mean absence of usable current-stock information. Any quantity-based fallback
must retain freshness checks, uncertainty and explicitly unknown event times.

The UK prototype estimates median depletion from negative changes only. Flat
and rising periods do not enter that estimate; in a sustained sellback regime
that can imply depletion unsupported by the current net stock trajectory. The
prototype also activates only after phase overrun/insufficient bounded history,
so an existing short historical window can still cause future waiting. Review
both before a UK live addition.

Three known failed South African current-stock trips had less than one minute
between estimated arrival and modeled buying-window end, despite a 197-minute
flight. Valid scheduling geometry does not establish sufficient predictive
accuracy of that end time.

## Proposed order

1. Make current-stock reachability independent of knowing an exact restock onset
   when fresh quantity/trajectory evidence supports a window. Do not fabricate
   the missing onset, discard genuine outages or assert stock lasts forever.
2. UK: use current quantity and observed net trajectory consistently; distinguish
   learned resets and sellbacks from depletion. Present current-stock availability
   and an explicitly uncertain end where appropriate. Fresh/reachable current
   stock recommends leave now. Retain distinct frozen-trip counting.
3. Camel, Nessie, Panda and Red Fox: calibrate recommended arrival placement using
   both restock-start and depletion-end uncertainty, inside the first reachable
   event. No blanket delay and no score-based skipping of events. Keep current
   stock immediate when reachable.
4. South Africa: inspect predicted versus observed restock/depletion timing for
   all ten failures, including the current-stock cases with tiny predicted
   headroom. Fix the buying-window forecast before selecting an arrival margin.
5. Compare the saved full-history baseline with one explicitly specified
   recency-weighted variant; preserve older history as support. Choose settings
   using earlier evidence and replay chronologically. No automatic 48-hour
   restriction, broad configuration tournament, or post-hoc shifted-arrival score
   presented as a new model result. Historical comparison precedes live forward
   confirmation.
6. Recheck success, every miss, availability of advice, unknown/pending outcomes,
   duplicate targets and VM runtime. Red Fox and UK are the first possible live
   additions after their appropriate checks; the other four need evidence from
   the targeted improvements. The current sixteen keep their existing evidence.

Preserve >30 at exact arrival, zero grace, all available causal baseline history,
revision before departure and immutable simulated trips after departure. No real
player flights are required for stock-based evaluation.

## Future NPC drug-sale profit comparison

User requested a later planner feature comparing overseas NPC drug sale profits.
Track destination sale prices with timestamps and provenance, configurable
acquisition cost, and relevant travel context. Design it separately from restock
prediction and distinguish stale prices. No implementation or game actions now.
