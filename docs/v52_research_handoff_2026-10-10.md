# Research handoff — 2026-10-10 — V49–V52

## Current production / research state

- **Production website, collector, bot:** unchanged.
- **Existing private predictions:** 19 items through V44 Red Fox, in the V38 private shadow service every ~5 minutes.
- **V48:** optional automated low-priority background cache warm-up, enabled by the user. It alternates Monkey and Chamois, and uses separate `/var/lib/torn-fren-v47/online_expert_cache.db`. Never disable except intentionally for incident mitigation.
- **Monkey/Chamois:** persistent caches initially showed 14/1,200 and 16/2,328; initial first V48 run showed 16 Monkey entries. Subsequent completion/progress **not yet verified**. Cache completion does not mean live model activation.
- **No new live model admissions:** remain **19/24**. Unfinished: Monkey, Chamois, Lion, Panda, Japan Xanax.

## GitHub commits in order

1. **V49** `a0abcb9e25e8dca77dc2787a35ff5e605b70ea63`: isolated original Lion/Panda two-expert, feature, and VM-cost diagnostic; protected checkout helper.
2. **V50** `48046878ef7ac0117bfb890efa1c73e1eb37a565`: offline causal expert-example JSONL exporter, portable trained selector JSON, sklearn parity tests. **No fitted classifier weights are in repository**; the user or a trusted offline replay must supply real, fully resolved labels.
3. **V51** `0b69b1701f07a6278f4d5a6b59f5c00616e9c1a1`: retrospective Japan Xanax V7/V8 source-hash and walk-forward comparison. Historical checkpoint is a development result: frozen V7 7/21 exact, V8 candidate 13/21 exact on the old research database. The current VM database has changed; **do not claim historical parity without matching snapshot hash, opportunities and V7 baseline**.
4. **V52** `287b9dc5ba9d84cf088b739de29d218cacf72d18`: SHA256-pinned Lion/Panda trained-selector single-tick research reader. It never returns a publishable recommendation and is not connected to the existing scheduler.

All work is on `research/v38-full-roster-live-prep-20261009`, not `main`. The V38 research adapter CI is green at V52. GitHub CI cannot substitute for VM resource measurements.

## Home session — safe and minimal

**Do not stop V44 or V48 manually.** They should remain enabled.

1. From `/home/ubuntu/torn-fren-v38-probe` fetch the latest research branch:

   `git fetch origin research/v38-full-roster-live-prep-20261009`

2. Stage the existing protected checkout helper **directly from FETCH_HEAD**:

   `git show FETCH_HEAD:deploy/scripts/v49_safe_update.sh > /tmp/v49_safe_update.sh`

3. Perform the protected update:

   `bash /tmp/v49_safe_update.sh`

   The script stops and waits for **only the research** V44 and V48 services during checkout and restores **both timers** with an EXIT trap, including on error. Never update the /opt production checkout.

4. Check timers: `systemctl is-active torn-fren-v38-private-shadow.timer torn-fren-v48-cache-warmup.timer`; expect `active` twice.

5. Run source and portable artifact tests:

   `PYTHONPATH="$PWD" .venv/bin/python -m unittest discover -s tests -p 'test_v5*.py' -q`

6. Observe background cache:

   `bash deploy/scripts/v48_cache_warmup.sh status`

7. Benchmark original Lion/Panda two-expert costs **one by one**:

   `bash deploy/scripts/v49_lion_panda_pair_probe.sh lion`

   `bash deploy/scripts/v49_lion_panda_pair_probe.sh panda`

   If a probe says `DEFERRED`, the V44 research cycle is active; retry later. A healthy diagnostic will say `SELECTOR_WEIGHTS_MISSING_NOT_PUBLISHED`. Do not run heavyweight offline ML replay/training on the 2-core VM.

### Later, from development PC (not VM)

- Produce fully resolved Lion/Panda example records with `research/v50_pair_example_export.py` using a **frozen offline stock-history snapshot** and explicit `--train-asof`.
- Fit the source-configured sklearn selectors with `research/v50_pair_selector_artifact.py`; freeze JSON + SHA256, audit no future labels, and validate on a genuinely later held-out/prospective period.
- For Japan Xanax, run `research/japan_xanax/v51_retro_parity.py` against the **original dated SQLite snapshot** with matching hash, or clearly mark the result as not verified. Even a matching development rate is insufficient for production promotion.
- After the real JSON artifacts exist, benchmark `research/v52_pair_trained_tick.py` with an explicit `--artifact-sha256`, compare to sklearn and representative holdout, and only then consider guarded private admission.

## Safety / honest status

- **No algorithm should be presented as a calibrated probability.**
- Preserve five-minute replanning, eight-hour max planning horizon, 30-unit arrival criterion, and 10-second grace.
- The V50 example normalization uses per-decision causal cutoffs, which differs from the champion replay's initial fixed validation-cutoff implementation. This is deliberate anti-leakage work, **not automatically a bit-for-bit frozen winner reproduction**. Prove comparative performance before any promotion.
- Historical cache progress depends on changing market data and CPU admission; there is no guaranteed completion wall time.
- Never commit the large collector SQLite database or API keys.
