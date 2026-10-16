# Existing experimental-page adapter prepared

The previously shared experimental.html was recovered. Its12459bytes and SHA256 `a9a47e0fe7d9b8139322873f27b31209862a8805296a9e5070ce7ff599069aa7` exactly match the page observed by runtime audit in completed run38925288000 onOctober16. This supersedes the earlier statement that no experimental source was available. It does not prove that the owner's app.py remains identical today.

The recovered HTML is retained as a test fixture. `prepare_shared_experimental_page.py` requires that exact hash and prepares a separate modified page, preserving the original table, observed stock graph, history links, timeframe controls and prediction API. Drift is rejected, not silently overwritten. New `shared_experimental_rows.js` advances a tolerated immediate departure's landing from actual display time, keeps absolute deadlines, clears expired rows/markers between30second refreshes, and clears proposals/markers on API failure. Display ticks do not pretend a new network snapshot was received.

`web/shared_experimental_overlay.py` is an owner-side hook, disabled unless `TORN_FREN_SHARED_EXPERIMENTAL_PREVIEW=1`. It translates the same precomputed board used by Travel Decisions and the V2 graph into the existing `latest` row schema. Country/item filtering is preserved. New rows do not inherit legacy probability fields. If the shared feed fails while the hook is enabled, recommendations become non-actionable instead of falling back to old predictions.

The minimal owner-app hook is in `deploy/patches/experimental_shared_departures_20261016.patch`. It preserves the existing V87 overlay before optionally applying the shared one. Its reference is the uploaded app.py SHA256 `86e84488655ab8e83fc86965c846f13ff17da27b0f8edbeac3bf5f3e583a2657`, NOT a verified current VM app hash. Review/merge against the actual deployed app; never replace that app wholesale with the research checkout. The existing V41 route flag and snapshot configuration are preserved.

To prepare a separate page for review:

```bash
python -m deploy.scripts.prepare_shared_experimental_page \
  --source /absolute/path/to/deployed/web/static/experimental.html \
  --output /absolute/path/to/staging/experimental_shared_preview.html
```

This does not install a page, change flags, start a service, or deploy a feed. The live page remains unchanged until owner-side installation. A continuously fresh shared snapshot is still necessary. Original point and bounded-tolerance profiles remain separate; neither is automatically promoted.

Tests cover matching board geometry, point-versus-tolerance evidence, expiry, failed feed, filtered responses, disabled-hook identity/no-IO and HTML drift rejection. A synthetic browser case exercises the exact prepared owner page, its existing observed-graph calls, selected recommendation display, client expiry and API failure. Chart/network inputs in that case are explicit fixtures, not live data or proof of deployed library parity.
