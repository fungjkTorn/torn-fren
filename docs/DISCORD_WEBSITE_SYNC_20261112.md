# Discord / website parity and observed-stock notifications — review-only

**Scope:** Discord bot and stock command formatting only. The existing website,
collector, V18/V19/V20 model rosters, publisher services, evidence databases,
research runners, and live decision rules are not changed.

## Why this change

The old `/predict` and `/history` called `services.prediction_v2_live` even
after the website moved to the separately published live-beta feed. That path
could report a different flight time or unapproved legacy accuracy. The Discord
bot must not be an independent inference/prediction engine.

## New behavior

- `/predict` reads **the same** `/api/first-release` precomputed forecast board
  as `/experimental` and `/travel-decisions`. Per-item freshness, selected
  event, estimated departure/arrival/deadline and last-ten **frozen simulated
  trips** are read from the published row. Never run V2 fallback inference.
- A missing item is shown as **UNDER_REVIEW**. A stale, incomplete or unsupported
  decision does not become a departure recommendation. Results use the site's
  existing **stock >30 at landing** rule (not >=30, and no grace).
- `/history` reads `/api/first-release/history-summary` and labels the
  history as observed >30-stock windows, not forecast performance. This still
  works when the prediction board is unavailable.
- `/site` opens the public website. `/predict`, `/history`, and `/stock`
  include site links. `/status` summarizes approved feed health. The
  unfinished static `/travel` command is retired.
- `/stock` preserves the collector's last-known quantity/price and separately
  reports country **poll** health. The timestamp of the last **changed** item
  is never represented as proof of a recent collector refresh.
- `/alerts` reports whether conservative observed-stock notifications are
  armed. No predicted departure alerts are introduced here.

## Observed-stock alerts — opt in

The bot reads the existing collector SQLite read-only, maintains its own private
cursor, and emits only a transition from <=30 to >30 for an explicitly
subscribed item when both global polling and provider country clocks are fresh.
It **does not** claim a confirmed physical 0-to-positive restock, announce
stocked-to-more-stocked changes, infer timing, or promise arrival availability.

First enabled scan establishes a baseline without broadcasting old stock.
A persistent cursor prevents repeat announcements after reconnect/restart.
Delivery is best effort: the cursor is stored **before** the Discord send, so
a failed send may be missed rather than posted repeatedly. Events over three
minutes old, missing country clocks, stale global polls and large backlogs
are suppressed.

Required bot environment:
- `PUBLIC_BASE_URL=https://<your published Torn-FREN website host>` — must
  reach the existing `/api/first-release` route through HTTPS.
- `RESTOCK_ALERTS_ENABLED=0` — default, leave disabled during initial rollout.
- `RESTOCK_ALERT_ITEMS=sou:Xanax;cay:Stingray Plushie` — semicolon-separated
  exact country-code and item pairs, **required** when enabling.
- `RESTOCK_ALERT_CHANNEL_ID=<existing alerts text channel ID>` — falls back to
  the existing CHANNEL_ID.
- `RESTOCK_ALERT_STATE=data/discord_restock_alert_cursor.json` — optional
  writable persistent path, private permissions.

The monitor intentionally does **not** use model validation or approval gates,
because an observed stock threshold crossing is useful for unapproved items.
It uses freshness gates instead. Never set `RESTOCK_ALERT_ITEMS=*` in a busy
server without evaluating notification volume.

## Pre-production checks

1. Check that live bot's `PUBLIC_BASE_URL` points to the current website and
   verify `/api/first-release` returns the approved live-beta feed (including
   each configured item's latest `valid_until_epoch`).
2. Compare representative `/predict` responses, including an unsupported
   item, a stale item and a supported item, against the exact website board
   and graph. Require equal departure/arrival/deadline values.
3. Verify `/history` uses descriptive statistics, not the old V2 historical
   success rate. Compare live `/stock` to the collector and confirm fresh
   country receipts exist before trusting stock alerts.
4. Keep restock alerts disabled while testing the bot in a private channel.
   Initialize its cursor without announcing old events; observe a new real
   >30 threshold crossing and verify one notification only.
5. Only then enable the selected notification list/channel in the bot's
   environment and restart **the Discord bot only**, not collector or website.
   Verify the bot is connected, slash commands are synced and no alert duplicates.
6. Roll back by disabling `RESTOCK_ALERTS_ENABLED` and returning bot modules to
   the exact prior commit; leave the publisher, stock history and research
   processes unchanged.

## Remaining work

Predicted departure alerts, user-specific subscriptions, profitability-ranked
`/next` commands and special Canada/Japan Xanax waiting-window notices are
deliberately deferred until their prediction policies/evidence are approved.
Actual player flight histories are not fabricated from simulated trips.

**No VM deployment, live Discord restart, or private database modifications
are part of the GitHub commit.**
