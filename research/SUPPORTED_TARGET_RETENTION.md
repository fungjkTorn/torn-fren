# Current-supported departure retention experiment

Problem: the completed October 18 09:00–12:00 UTC historical check produced
zero executable native departures for Camel, Nessie, Red Fox and Peony. This
is a coverage failure, not four failed arrivals. A strong frozen future
recommendation can still be postponed every five minutes until the visitor
times out.

The new experiment uses the original model's current winning cluster. It
retains an older target only if that exact timestamp is still in that cluster
at the current issue. Missing support, stale source or model abstention clears
the target. An earlier current native target can replace it. Each visitor has
an absolute eight-hour deadline; no target survives on a reset deadline.

Fixed policies, identical for all four items:

| Policy | Rule |
| --- | --- |
| native | Untouched native target, including its original fallback |
| front_original_band | Earliest point in the original winning cluster; existing comparator |
| retain_original_band | Earliest of previous/current native targets that still has current support |
| retain_original_band55 | Same rule, requiring current raw score at least .55 |
| leave_now_control | Current issue plus the existing 15-second floor |

The .55 score is an uncalibrated model score, not a 55% success claim. Neither
retention policy manufactures support for a no-reference template fallback.
All policies use the existing 180-second source-expiry contract at departure,
300-second replanning, arrival quantity at least 30 and 10-second grace. The
physical depletion threshold remains exactly zero. No restock clock or
production model is changed.

Model adapters preserve Nessie's one-day template; Camel's original 24-expert
bank and winner tie breaks; Red Fox's k18/global-weight-.5 analog; and Peony's
actual V20 traj12 engine. Peony's winning cluster is observed from the unchanged
engine's return frame in an isolated child, rather than copied from V18 or
approximated with another template. Template/analog adapters assert native
center parity on every issue. The causal database must contain no future
stock, heartbeat, gap start or known gap closure before any model runs.

`research.supported_target_replay` serializes inference, computing a curve
once per item/issue and sharing it across all policies and visitor starts.
It writes as-issued bands before scoring arrival truth. Native timeouts and
errors remain explicit; they disqualify a clean comparison. No model selection
or automatic promotion occurs. Missing replay ticks are errors, not presumed
abstentions. Unknown truth is retained and immature truth rejected.

Local checks cover native fixture parity (including Camel's entire slow
24-expert bank), current-support withdrawal, fixed deadlines, stale-source
withdrawal, separate visitor state, no-reference fallback handling, missing
ticks, and separation of scheduling from outcome labels. Fixture checks are
not historical item accuracy results.

Validation plan: first compare the four fixed policies on the already-read
October 18 four-hour cohort window as a **development** comparison. Any later
qualification must use untouched subsequent data and report departures,
success/known, unknowns, distinct departure times, waiting time and inference
errors together. Do not select a different policy per item from four starts.

The historical runner accepts a sealed research SQLite source and fresh output
directory:

```bash
python -B -m research.supported_target_replay \
  --source /path/to/sealed-research-snapshot.sqlite \
  --out /path/to/new-retention-study \
  --start 1792314000 --end 1792324800 \
  --model-sha EXACT_SOURCE_COMMIT
```

This is a targeted historical study, not a replacement for the full24 live
canary. Do not run it on the busy production host alongside the waiting
canary. No historical run was launched while the owner's reported CPU idle
fraction was zero. No arrival-accuracy improvement is claimed yet.
