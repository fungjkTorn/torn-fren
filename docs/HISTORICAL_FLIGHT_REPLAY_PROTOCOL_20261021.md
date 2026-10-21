# Historical flight replay — as-issued causal stock and restock simulation

## No 14-day waiting period

The isolated VM forward dataset retains the **last 14 days of source history**;
it is refreshed approximately every 90 seconds. This is a training / observation
window, NOT a requirement to wait 14 days for forward scores or make model
changes. Real forward batches can be graded as soon as a chosen event and its
post-arrival observations mature.

A chronological historical replay is also valid. The model can see stock data
at or before simulated issuance, and the independent evaluator reads later
observations only after the forecast/flight tape has been fully generated.

## Existing evaluator and additions

- `research/historical_restocks_all24.py` already reconstructs each item on
  five-minute ticks and scores simulated flight arrivals using an eight-hour
  planning horizon with pre-departure reconfirmation.
- Physical restocks use independent 0->positive chronological event labels,
  not retrospective nearest-restock matching. Evaluate first and selected
  event identity separately.
- Arrivals require at least **30 stock through landing+10 seconds**, as
  evidenced by successful polls bracketing arrival. The collector logs
  quantity *changes*, not entire stock on every poll: reconstruct from
  last-known quantity while verifying bracket continuity, source switches,
  outages and changes. Missing or conflicting evidence is UNKNOWN.
- The new `flight_evidence_examples` object includes for each outcome type
  the first chronological sampled UTC-hour decision start, rechecked
  departure, estimated landing, plus-10 time, two poll observation times,
  and their quantities. This is intentionally **not** the rate denominator
  or a statistically representative set of outcomes.
- Core statistics remain in `departure`, `leave_now`, `matched_vs_now`,
  `physical`, and `chronological_slices` with all eligible cohorts counted.
  Starts can overlap an observed restock; report distinct events separately.
- Historical stock provider/poll continuity is not the same as game server
  second-accurate arrival, country-fresh provider data or real player purchases.
  No automatic model deployment or champion promotion.

## Windows PC runnable example (24 items, one day of evaluated cohorts)

Use your *existing locally sanitized* SQLite and Python 3.12 venv.
The snapshot may contain 45 days of historical data, but `--days 1` means
the replay evaluates *one day of historical starting decisions*, using
prior data for model training and the following observations for grading.

~~~powershell
cd "$env:USERPROFILE\Desktop\torn-fren-pc"
git fetch origin
git switch research/v38-full-roster-live-prep-20261009
git pull --ff-only origin research/v38-full-roster-live-prep-20261009
$pin = git rev-parse HEAD

.\.venv\Scripts\python.exe -m research.historical_restocks_all24 `
  --source .\historical_pc_data\stock_history_research.db `
  --days 1 `
  --model-sha $pin `
  --output .\historical_pc_results\historical-flights-all24-day1.json
~~~

The script prints each completed item and writes a partial checkpoint. A
`PARTIAL_NO_PROMOTION` result is not full-roster proof. It is read-only
against the source and does not affect the three production website views.

To inspect one known item initially, append:
`--item-key "uni:Red Fox Plushie"` or
`--item-key "sou:Lion Plushie"`.

The output is aggregate stock-history research evidence and should be
kept private. The number of evaluated days is bounded to 1..3 for runtime
protection; this is not the same as the 14-day VM lookback and does not
imply a 3-day evidence requirement.

## Why maintain live forward evaluation too?

Offline replay catches bad ideas fast, allows comparisons of multiple models
on identical historical issue clocks, and supports tuning using earlier
training periods only. But repeated tuning on a fixed history risks
overfitting, and collector-side reconstruction has imperfect coverage.
The independent append-only live issue tape acts as a prospective check
against those risks. It will be scored with the same ordinal and arrival
policy; there is no reason to stop historical work while it accumulates.
