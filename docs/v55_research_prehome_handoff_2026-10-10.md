# V55 pre-home handoff — October 10, 2026

## Summary

No production or live VM change was made by V53, V54 or V55.
All work remains on branch research/v38-full-roster-live-prep-20261009.
The user's V44 private prediction roster was 19/24 after Red Fox admission.
The V48 cache timer for Monkey/Chamois was enabled when last reported.
Progress since then requires a read-only on-VM check.

### New research

- V53 research/v53_pair_holdout_audit.py:
  * Training uses only fully resolved outcomes before a fixed cutoff.
  * Post-cutoff holdout decisions must follow an embargo; labels must be
    resolved before the audit cutoff.
  * Evaluates all eligible resolved holdout decisions, including expert
    agreements. This prevents evaluation only on a disagreement subset.
  * Reports Expert A, Expert B, selector, and retrospective oracle ceiling.
  * Exports research-only portable JSON via V50; never Python pickle.
- V54 research/v54_pair_resume_export.py:
  * Replays only the original source-pinned experts from an offline frozen
    stock-history snapshot, NOT the production collector.
  * A separate SQLite cache records each processed anchor including abstains,
    and safely resumes from the first missing anchor.
  * Pins SHA-256 source file, fixed training cutoff, target and anchor set.
    Refuses to mix evidence if any change.
  * Exports JSONL atomically and rejects source/cache/output path collisions.
  * Small batches are intended for the development PC.
- V55 deploy/scripts/v55_home_research_check.sh:
  * Read-only unified check for V44/V48 timers, V50–V54 tests,
    19-model experimental API roster, and private cache progress.

### Home commands

Do not re-install or disable either research timer. The protected checkout
helper only temporarily pauses the V44/V48 research timers, waits for jobs to
finish and restores both through an EXIT trap.

Working directory: /home/ubuntu/torn-fren-v38-probe

    git fetch origin research/v38-full-roster-live-prep-20261009
    git show FETCH_HEAD:deploy/scripts/v49_safe_update.sh > /tmp/v49_safe_update.sh
    bash /tmp/v49_safe_update.sh
    bash deploy/scripts/v55_home_research_check.sh
    bash deploy/scripts/v49_lion_panda_pair_probe.sh lion
    bash deploy/scripts/v49_lion_panda_pair_probe.sh panda

Run Lion and Panda separately. If a pair probe reports DEFERRED, V44 was
active; retry later instead of stopping any services. They measure two
original analog experts per item. The trained classifier weights do NOT yet
exist and cannot be fabricated. A healthy pair cost diagnostic reports
SELECTOR_WEIGHTS_MISSING_NOT_PUBLISHED.

### Later offline on a development PC with a frozen input DB

1. Run the V54 exporter in small resumable batches, for example:

    python -m research.v54_pair_resume_export --db FROZEN.db --cache lion_progress.db --output lion_examples.jsonl --target lion --train-asof CUTOFF --last-starts 240 --max-new 12

   Repeat until OFFLINE_EXPORT_COMPLETE. Use a copied frozen source DB.
   NEVER use /opt/torn-fren/data/stock_history.db for training.
2. Audit with V53 using an explicit --train-until and --evaluate-until,
   separated by an eight-hour embargo. Ensure enough training disagreements
   and enough fully resolved post-cutoff holdout decisions.
3. Review the genuine chronological holdout metrics and source parity.
   The portable classifier may then be tested through V52 with an explicit
   reviewed SHA-256, but not published without admission checks.
4. Japan Xanax V51 requires the dated original historical DB fingerprint;
   changed collector data cannot verify exact older checkpoint parity.

### Remaining limits

- No Lion/Panda classifier has been trained on real data in this turn;
  GitHub tests used mocked or synthetic data only.
- Frozen champion retrospective selector training used fixed validation
  cutoffs. V50-V54 intentionally use per-decision normalization for causal
  evaluation; this may change results and still needs independent validation.
- Monkey, Chamois, Lion, Panda and Japan remain unactivated: 19/24.
- CI checks are necessary but not sufficient for live accuracy or VM capacity.
