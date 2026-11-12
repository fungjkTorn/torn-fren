# Compact travel planner UI update

The initial beta added a tall forecast card ahead of a legacy chart page that
hid vertical overflow on desktop. That combination put the chart below the
viewport with no way to reach it, and showed duplicate V2 prediction panels.

The replacement uses a compact travel summary above the existing chart, enables
vertical scrolling, and collapses observed stock and price statistics below the
chart. The old prediction panels and V2 backup control are hidden. The original
chart, historical data, item selector, time ranges and pan/zoom behavior remain.

The planner uses compact rows, country/type/status filters, text search,
departure/country/item sorting and 20-row pagination. Results and recorder
provenance remain available in a keyboard-accessible details dialog. The page
counts data rows dynamically and does not assume the rollout stops at ten.
At phone widths the rows adapt into readable two-column summaries without
horizontal page overflow. This does not change which models are approved.

The publisher API, models, immutable evidence log and success rules are
unchanged. Unmatched failed/unknown forecast rows still withhold a percentage;
they are disclosed in details instead of dominating every item row. Last-ten
indicators preserve success, miss, unknown and pending statuses separately.

## Deployment

Use TORN_FREN_UI_UPDATE.zip, not the full beta installer. Run its Run_Update.ps1
from Windows PowerShell using the existing desktop SSH key. The installer checks
all three installed asset hashes against the deployed 45d14b5 model package,
backs them up, writes only those assets and checks localhost routes and asset
checksums. Failure restores the old assets. No services are restarted and no
model/publisher/database files are changed. A guarded rollback.py is included
in the timestamped backup directory.

After success refresh with Ctrl+F5. Save/send the generated desktop report
`torn-fren-ui-update.json`. The package is prepared and tested locally; live
installation requires the owner's existing SSH session/key.

## Validation

`tests/test_first_ten_ui_update.py` checks successful updates and reruns, automatic
rollback, checksum rejection and refusal to overwrite newer changes.

`tests/first_ten_ui_browser.cjs` exercises the redesigned assets against captured
public feed data and the actual audited VM chart HTML, with existing Chart.js
files supplied locally. It checks desktop/mobile rendering, ten/fifty items,
filters/sorting/pagination, modal details/Escape/focus, feed failures, real canvas
rendering, scroll reachability, width overflow and existing item selection.
Captured fixtures and screenshots are temporary QA material, not deployment
inputs or model accuracy evidence. For a standard Playwright installation set
FIRST_TEN_UI_FIXTURES and optionally FIRST_TEN_CHROMIUM / FIRST_TEN_CHROMIUM_ARGS.
