# Overnight execution recovery

The approved next-six cleanup was interrupted by loss of the execution environment.
Do not report final candidate accuracy until the archived runs have completed and
passed V5 rescoring. No production changes were made.

## Preserved sources

- Repository: fungjkTorn/torn-fren, branch release/first-ten-operation-sequence.
- Frozen model/protocol commit: 4fe4b9e2f05200651d230012c9b59c42985758a3.
- Original real stock database: torn-fren-challenger-history-20261030T020202Z.sqlite,
  Library libfile_f403ec62efd48191a0651e6a7d831b16,
  SHA256 543b67f1fe4874961130948ecee1d9df4870efe80599726f13828b19da8a6687.
- Recovery ZIP: TORN_FREN_OVERNIGHT_CLEANUP_20261029.zip,
  Library libfile_c6c7ca2635ec8191aed9a4b9c3f43c81. Initial version number 0.
  It is an explicitly unfinished checkpoint, not an accuracy report.
- Completed saved baseline report: TORN_FREN_NEXT_SIX_WEEK_REPLAY_20261029.zip,
  Library libfile_3683e7f1eb6c8191a3f7e826fc033a02.
- All newly generated stock forecasts use actual source data. No observations,
  arrivals, old forecasts or outcomes have been edited.

## First recovery action

Check for an available execution environment. If the original workspace is
restored, inspect the existing output directories before rerunning anything.
The processes may have finished before the transport was lost. If unavailable,
do not claim jobs remain running or invent progress/results.

Original repo: /workspace/scratch/431a0f4d9a1b/first-release-contract
Original data/output parent: /workspace/scratch/431a0f4d9a1b/live_beta_qa/prelive-cleanup

Final experiment output directories:
- clean-full-v3
- clean-recent7-v3

Each was launched with:
PYTHONPATH=../live_beta_qa/test-deps:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
MKL_NUM_THREADS=1 TORNFREN_PRELIVE_VARIANT=clean-full (or clean-recent7)
python -u -m research.run_next_six_replay
--source ../upload/torn-fren-challenger-history-20261030T020202Z.sqlite
--output ../live_beta_qa/prelive-cleanup/clean-full-v3 (or clean-recent7-v3)

Use separate output directories and preserve the variant environment variable.
The runner resumes exact existing issue clocks and validates the manifest.
It fixes refill-profile calibration at 1792720800 across resumes. Twelve real-data
resumption comparisons matched continuous forecasts exactly.

If workspace files were lost, use the Library skill to restore the recovery ZIP
and original database. Restore the checkpoint's variant/items directories to the
same relative structure under each variant output. Run with the unchanged model
code above. The original baseline full archive is in its separate completed ZIP.
Do not use the abandoned clean-full/clean-recent7 or V2 partial archives as final
results. They were stopped for reproducibility/implementation review before
comparative arrival accuracy was inspected; records were retained.

## Status at last successful inspection

Both variants had completed Camel, Nessie, South African Xanax and UK Xanax.
Full-history Red Fox also completed. Full-history Panda was at least 1297/2017
clocks; recency Red Fox at least 1632/2017 and Panda at least 1266/2017.
No model errors had appeared. Do not assume these partial counts are final.

The durable ZIP was captured earlier, with complete JSONL prefixes:
full: South Africa 1235, Camel 728, Nessie 675.
recent7: South Africa 808, Camel 561, Nessie 692.
Later work may need recomputation if the workspace did not survive.

## Protocol and validation

Read docs/PRELIVE_CLEANUP_EXPERIMENT_V1.md. The fixed variants implement:
signed real ten-minute net-stock blocks including flats/rises; quarter-based
current-window end uncertainty; latest fresh depletion-risk response; immediate
current-quantity support without a fictional depletion/restock timestamp; native
future arrival clamped to an overlapping uncertainty core; and one seven-day
recency half-life comparator retaining older history.

Preserve first reachable window selection, native model identities, full native
history, >30 at exact arrival, zero grace, pre-departure revisions and immutable
frozen simulated trips. No real player flights are required. No model-score
eligibility filter or hard 48-hour training cut is allowed.

Thirty-six real snapshot checks passed. Twelve resume checks passed. Rescoring
the saved baseline after additive evidence changes matched its original item
metrics exactly. Those proofs are committed in docs. These are correctness
checks, not candidate accuracy results.

After completion, run research.summarize_next_six_replay on each variant and
research.compare_prelive_cleanup against the completed baseline. Check:
- exactly 2017 issue clocks per item and zero model errors;
- model identities/full-history flags and exact departure/arrival flight geometry;
- source/archive hashes unchanged, idempotent V5 scoring and zero duplicate targets;
- success, all early/late/other misses, unknown/pending, advice coverage and counts;
- exact observed opportunity matches (not nearest predicted times) and wait times.
Reject apparent gains based only on fewer tested opportunities or much later travel.

## Findings already observed, not model changes

The quartile uncertainty cores often do not overlap for long-flight future
windows. The prescribed rule then retains the native recommendation. Report
actual adjusted counts; do not imply the placement rule acted when it did not.

The existing calendar learner uses stock-above-30 availability transitions.
For South Africa, 13 of 42 same-provider stock returns in the test week are below
the learned normal-refill band. These are ambiguous returns/sellbacks, not asserted
normal restocks. This is a diagnostic of definition alignment; no calendar rewrite
was made from it during the fixed comparison. Do not silently add another model.

UK's pretest signature had one clean surplus-to-base example. At the supplied
cutoff it has eight, with learned base 2500; seven are in the week. Latest evidence
is suitable for future deployment calibration but was not substituted into the
earlier replay or scoring (which would leak later knowledge). A continuously
stocked period is not many independent successful trips.

Local cold six-item diagnostics (not VM certification) measured 22.441s full
and 22.341s recent7 inference while six replay processes were active. Raw runtime
JSONs were in the output parent if the workspace survives. No VM SSH key exists
here; no production runtime check or deployment occurred.

## Deliverable and scope

Complete all four approved areas, honestly report what worked and what did not,
and keep the live sixteen unchanged. Keep the same fixed experiment settings;
do not add synthetic data, retrospective shifted-arrival scores, or tune on later
outcomes to manufacture an improvement. Record limitations and any remaining
calendar-definition questions.

Produce one complete report ZIP with comparisons, every miss, frozen trips,
exact forecast archives, protocol, code/source identities and validation.
Replace the existing unfinished Library ZIP, preserving its Library identity
and using the returned current version guard; apply returned xattrs via the
current Library helper. Use the final file's Library link in the response.
Code and reports belong in Git; no GitHub Actions ([skip ci], verify zero runs).
