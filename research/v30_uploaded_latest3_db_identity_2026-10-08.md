# V30 uploaded DB identity verification — October 8, 2026

**Do not treat this upload as a new validation snapshot or original-source native parity input.**

User-supplied file: `torn-fren-stock-history-latest(3).db` (verified by read-only SQLite query and SHA256).

- Size: `140181504` bytes
- SHA256: `d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583`
- Rows in `stock_history`: `916510`; span `1789339399` (2026-09-13 22:43:19 UTC) through `1791418812` (2026-10-08 00:20:12 UTC)
- Rows in `poll_heartbeats`: `44034`
- Rows in `collection_gaps`: `105`
- File was **byte-identical** to the already uploaded `torn-fren-stock-history-latest(2).db` in the same active runtime (`cmp` check, in addition to matching SHA).
- Original V21 development master's recorded SQLite digest: `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761` — **different**.

**Implications:** This upload is useful as an archived newer-data snapshot, but does not give us original dataset parity and is not a new forward-observation lockbox. Existing V28 comparisons on this same DB must not be counted as new independent evidence. No production release gate changes, winner changes, or model performance claims arise from this upload.

**Next input:** Original `torn-fren-stock-history-fresh.db` (or exact original saved copy) with SHA `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`. The Library has a 126 MB `fresh(3).db` record, but its original bytes were not authorized for materialization in the tool runtime. A directly mounted conversation attachment is required here for the native V30 same-input test.

`main` and VM remain untouched.
