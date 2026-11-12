# Checkpoint 16 — candidate compatibility failure isolated and corrected

The operator report `TORNFREN_CANDIDATE_STAGE_V1` confirms actual candidate first-ten (10 items), challengers (6) and next-six (6) publications passed. Public final-pair and private Japan both failed with TypeError. Production source/services/state were not modified. The real bot unit was discovered as `torn-fren-bot.service`, active in `/opt/torn-fren`.

Static and native-adapter reproduction found missing captured-production threshold interfaces in the shared GitHub helpers:

- `QuantityRateCycles(crosses, min_qty=31)` and `ZeroCycles(..., min_qty=31)` were rejected by old signatures.
- `Timeline(..., min_qty=31)` was rejected by the old shared template timeline signature used by Chamois.

Restore exactly the production-captured implementations of `research/quantity_rate_cycles.py`, `research/true_zero_cycles.py`, and `research/plushie_champions/common.py`. Existing default threshold 30 is unchanged; explicit 31 remains confined to callers selecting it. Physical zero anchors and inventory-rate observations retain their meaning. This is source compatibility reconciliation, not a model retuning.

Four new public regression tests execute the real constructors, quantity boundaries (31/30/29), legacy defaults, physical-zero bracket preservation and invalid threshold handling. Added the suite to production reconciliation CI. Local relevant regression suites passed: 4 new helper tests, 5 quantity-rate tests, 4 zero-cycle tests, 3 fast-template tests, 17 publisher/scheduler tests and 1 receipt-projection test (34 public checks). An additional private local test executed actual Japan and Chamois adapters on synthetic history without stubbing native forecasting and passed; source DB bytes remained unchanged. The earlier three private-overlay wiring checks had deliberately stubbed forecasting and therefore could not detect these missing APIs.

Rebuild the pinned candidate and rerun VM staging before production cutover. Returned reports should retain useful sanitized traceback locations/keyword classification if another compatibility error occurs. Main remains unmerged, no VM patch/deployment, no data or ledger cleanup. A full pipeline success is still pending.
