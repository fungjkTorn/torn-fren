# V75 Chamois 21st specialist — protected research rollout

Current deployed state: V72 scheduled 20 models; V48 cache warmup; V73 web
experimental page points to V72 private_predictions; V65 fallback preserved.
Do NOT change the public Torn stock collector, website forecasts, V2, or bot.

## V75 gate
- Generalized V66 original 24-expert validator, still requires full rolling
  three-day Chamois evidence, original-vs-accelerated parity, gap/source
  fingerprints, no causal/lookahead violations.
- Run Chamois FIRST from a fresh V75 private snapshot; then existing V72
  Monkey-first plus original 19 unchanged, using SAME immutable snapshot.
- Persist to /var/lib/torn-fren-v38/v75_private_predictions.db only.
- If Chamois evidence missing or selector abstains, store a NULL-departure
  Chamois abstention and continue the other 20.
- Do not loosen 25% CPU quota, 1 GiB memory, 240s timeout, or 30s per
  original worker. Avoid running when V72 research is active.
- Do not present a private selection as measured restock accuracy.

## Commands after CI green
  cd /home/ubuntu/torn-fren-v38-probe
  git fetch origin research/v38-full-roster-live-prep-20261009
  git show FETCH_HEAD:deploy/scripts/v49_safe_update.sh > /tmp/v49_safe_update.sh
  bash /tmp/v49_safe_update.sh
  .venv/bin/python -m unittest discover -s tests -p 'test_v74_chamois_*' -v
  .venv/bin/python -m unittest discover -s tests -p 'test_v75_private21_chamois_smoke.py' -v
  bash deploy/scripts/v75_private21_smoke.sh

Smoke only; neither the research timer nor website changes.
Require status V75_PRIVATE21_RESEARCH_EXECUTED, v72_original_19_proposals=19,
v72_monkey_proposals=1, chamois_proposals=1, total_proposals=21,
source_fresh_after_cycle=true, Chamois validator validated and full parity.
A transient deferral or cache-not-ready ABSTAIN is NOT proof of 21.

After a successful VM one-shot and operator approval:
  bash deploy/scripts/v75_private21_transition.sh status
  bash deploy/scripts/v75_private21_transition.sh enable
This stops ONLY the private research timer while naturally waiting for an
active cycle, installs a V75 ExecStart override above V72, then restarts timer.
V48 remains enabled, V72 DB and website remain unchanged until deliberately
switched after 3 healthy unattended cycles.

Rollback:
  bash deploy/scripts/v75_private21_transition.sh rollback
Restores original V72 research 20-model service and V73 website seamlessly.

## Forward-outcome research
V76 report reads the frozen as-issued decisions from the research sidecar,
deduplicates identical item+arrival windows, then reads collector samples.
Run with:
  .venv/bin/python -m research.v76_forward_research_report --sidecar v72 --days 1
Use --sidecar v75 once V75 has meaningful forward history. It is READ ONLY.
A +/-180 second stock bracket is a proxy, not proof at the exact 10-second
arrival window. A confirmed sample >=30 within the actual window is
separate direct evidence. Missing coverage is UNSCORABLE, not a miss.
Daily evaluations can be compared after several days, but do not call
proxy success fractions verified true accuracy or calibrate probabilities.

## Remaining two champion specialists + Japan Xanax
Lion/Panda: only exact expert configurations and source-causal offline
training pipeline exist in this repository. Genuine fully resolved sample
JSONL, trained sklearn weights as portable JSON, SHA256 and chronological
post-training holdout must be provided before admission. V49/V50/V52-V54.
These cannot be honestly substituted with unfitted synthetic selectors.
Japan Xanax: existing research V8 retrospective candidate 13/21 exact
on historical development snapshot; live target still requires independent
parity and substantially better prospective accuracy. Keep unreleased for now.
