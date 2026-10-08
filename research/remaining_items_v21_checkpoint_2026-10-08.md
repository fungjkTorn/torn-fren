# Remaining-item tournament, scoring defect and V21 plan — 2026-10-08

## Frozen data / sources
- Frozen original research DB: `data/torn-fren-stock-history-fresh.db`
- SHA256 `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`
- V19 source: `data/all_item_v19/master.json` — 236 items; 134 complete, 102 insufficient cycles.
- V20 source: `data/weak_item_v20/master.json` — still running separately on user PC during diagnosis. **Do not interrupt or overwrite.**
- New source: `services/remaining_item_v21.py`, non-destructive corrected-label auditor and corrected dynamic-planner challenger.

## Important correctness discovery: completed-cycle-only scoring falsely excludes real stock
V19 and V20 reuse `services/plushie_flower_dynamic_planner_v19.py`. Its `Timeline.success` tests arrivals against `self.windows`, which are constructed only from completed validated cycles. Some genuine >=30 stock windows are omitted, especially persistent/sparse items with incomplete cycles or gap recovery.

We replayed every stored V19 holdout recommendation on the exact frozen DB, using direct quantity from the cleaned change-event log at each actual arrival (and looking up to 10 seconds ahead for a grace hit), suppressing one-poll provider bounces and excluding known collection gaps.

**Audit results:**
- 134 completed V19 items; 27,654 valid stored holdout sessions
- 46 items have label disagreements
- 1,172 false-negative successes (reported as failures despite actual stock >=30)
- 0 false-positive successes seen
- items scoring >=80%: previously 48, now 62 **for the same already-chosen V19 recommendations**.

Some of the largest changes:
- `chi:Ecstasy`: reported 0%, direct 100% (89/89)
- `uni:Shrooms`: reported 0%, direct 100% (90/90)
- `uni:Ecstasy`: reported 0%, direct 100% (91/91)
- `can:Vicodin`: reported 8.7%, direct 100% (92/92)
- `swi:Ketamine`: reported 5.7%, direct 100% (88/88)
- `chi:Printing Paper`: reported 4.5%, direct 90.9% (80/88)
- `arg:Patagonian Fossil`: reported 39.2%, direct 88.7% (86/97)
- `arg:Meteorite Fragment`: no label discrepancy on V19's 212 holdout recommendations

**Critical caution:** corrected replay does not recompute training selection. V19/V20 chose configs with the same flawed labels, so these are repaired evaluations of the *existing* recommendations, not final champion statistics. Correct scorer must be used for retraining/reselection before model promotion.

## Original V19 coverage taxonomy (NOT incorporating V20 rescue yet)
- 48 complete with V19 reported >=80%
- 44 complete with V19 reported 50–80%
- 33 complete with V19 reported <50%
- 42 sparse/insufficient with >75% time at >=30
- 37 sparse/insufficient with 10–75% time at >=30
- 4 sparse/insufficient with <10% time at >=30
- 28 items with observed historical max below 30 — 30-unit benchmark impossible for these.

The 28 historical-max-below-30 items should receive explicit quantity-feasibility handling. When user requests a quantity threshold above known stock maximum, show impossible/unsupported quantity, not an alleged prediction accuracy. For other users/contexts, allow item-specific requested quantity (e.g. >=1) and score the relevant target. Some rare items are almost always in stock yet never have 30 copies.

## Remaining truly weak examples after corrected replay
- `chi:Bo Staff` 0% corrected, 0.3% of observed covered time >=30
- `cay:Steel Drum` 0%, negligible time >=30
- `chi:Twin Tiger Hooks` 0%, 1.2% time >=30
- `jap:Sensu` 1.8%, 0.6% time >=30
- `arg:Tear Gas` 25.4%, 16.9% time >=30
- `chi:Fireworks` 45.6% corrected vs 32.1% reported
- `haw:Large Suitcase` 43.5%, 27.6% time >=30

These require either stronger scarcity-aware modeling, quantity-dependent scoring, or recognizing that success is infeasible for a particular flight/quantity.

## Plan
1. Allow the already running V20 tournament to finish; no changes to its source or output mid-run.
2. Run the *read-only* V21 audit against **both** V19 and completed V20 master files using the same original frozen DB. Verify dataset hash.
3. Run limited V21 corrected-retraining challenges on pathological examples and high-value genuinely weak items, then scale only if model adds value.
4. Add sparse/persistent availability-focused models and pooled/fallback approaches without forcing completed-cycle minimums.
5. Compare V9/V10 incumbents, V19/V20, V21/V22 challengers and specialist Japan/UK/Canada Xanax/flower/plushie on matched rules; retain genuine best per-item models.
6. Integrate only once full system is ready; no deployment now.

## Commands

After the original V20 command has finished:

```powershell
git pull
python -u -m services.remaining_item_v21 audit `
  --db "data\torn-fren-stock-history-fresh.db" `
  --masters "data\all_item_v19\master.json" "data\weak_item_v20\master.json" `
  --expected-db-sha256 "9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761" `
  --output "data\remaining_item_v21\truth_audit.json"
```

For independent corrected re-selection, **only when the main all-item runner is finished or capacity allows**:

```powershell
python -u -m services.remaining_item_v21 tournament `
  --db "data\torn-fren-stock-history-fresh.db" `
  --only "chi:Ecstasy" `
  --only "uni:Shrooms" `
  --only "can:Vicodin" `
  --only "swi:Ketamine" `
  --only "arg:Patagonian Fossil" `
  --workers 2 --resume
```

The separate V21 files do not alter the live website, Discord bot, original V19/V20 tournament or any production registry.
