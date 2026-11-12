# V128 — full 24-item first-credible-departure prospective research

The existing 21 research specialists and V87 3 previews are not promoted,
modified, replaced, or rerouted. The V128 challenger uses **all 24** exact
foreign-stock item identities, but intentionally uses a *single experimental*
completed HIGH/LOW phase Monte Carlo benchmark with destination-specific flight
time. It has not demonstrated superiority on an independent holdout.

## Exact all-item roster

- Argentina: Ceibo Flower, Monkey Plushie
- Canada: Crocus, Wolverine Plushie, Xanax
- Cayman Islands: Banana Orchid, Stingray Plushie
- China: Panda Plushie, Peony
- Hawaii: Orchid
- Japan: Cherry Blossom, Xanax
- Mexico: Dahlia, Jaguar Plushie
- South Africa: African Violet, Lion Plushie
- Switzerland: Chamois Plushie, Edelweiss
- UAE: Camel Plushie, Tribulus Omanense
- United Kingdom: Heather, Nessie Plushie, Red Fox Plushie, Xanax

**Source**: `research/v38_roster.json` has 22 keys; the two exact
`research/v42_xanax_candidate_tick.py` approved keys `can:Xanax` and
`uni:Xanax` make 24. Distinguish Japan Xanax from the v42 generics.

## Objective, safety and evidence

- Find the earliest departure whose *predicted arrival* has at least 30 stock,
  allowing reasonable waiting. Departures considered on a 5-minute grid up to
  eight hours ahead; correct country-specific flight durations.
- Experimental threshold: at least 0.60 availability fraction of 128 empirical
  scenarios for two adjacent 5-minute departure slots. **Not a calibrated
  60% game-world success probability**. Different items may ultimately need
  different algorithms, and every incumbent remains the benchmark.
- A projection beyond five minutes is a **watch, not an executable flight
  recommendation**, until a fresh as-issued V128 tick reconfirms it.
- Underlying stock collector remains `/opt/torn-fren/data/stock_history.db`,
  opened `mode=ro`. A global poll heartbeat is not a per-country upstream
  freshness certificate. Gaps, source switches, missing onset, sparse completed
  cycles, and sparse state changes can require abstention.
- `--preview`: zero stock/research DB writes.
  `--record`: only private
  `/var/lib/torn-fren-v38/v128_earliest24_shadow.db` receives rows.
  New first-issued snapshots retain 24 items **including abstentions**.
- Separate timer `torn-fren-v128-full24-shadow.timer`:
  every five minutes at minute :04/:09/:14, etc.; 15% CPU quota,
  512MB max RSS, nice 19, 150s kill limit; no network; no V38/V75/V82/V85
  timer or website overrides. Timer is **not automatically enabled by a git push**.
- `research/v129_full24_forward_report.py` provides a read-only forward
  report: first-issued item/UTC-hour cohorts, 24-item abstentions and unknowns,
  matched leave-now proxy, pending arrival coverage, and replan reconfirmation.
  It is for future data after recording; it must not claim actual player flights
  or independent game-world restock truth.

## VM operator

The guarded operator `deploy/scripts/v128_full24_operator.sh` accepts:

- `status` — read-only timer and sidecar status, no install
- `smoke` — fetch **immutable pinned** research source, stage it in
  `/home/ubuntu/torn-fren-private-models/v128_stage/pinned`,
  compile, run one complete 24-item preview, **no service install**
- `enable` — perform smoke again, verify existing unit files if present,
  then explicitly enable only the V128 timer
- `disable` — disable only the V128 timer; keep sidecar evidence intact

The operator's `BUNDLE` pins the 24-item model, frozen roster, launcher,
and timer/service units at commit
`3c73f931c6e9e7c21f46d813a0fc98550416f0ae`.

GitHub CI `.github/workflows/v85-japan-forward.yml` runs regression suites
for V128 roster, UK V125 parity, country travel, fail-closed abstentions,
sidecar safety, optional timer and V129 honest forward scoring.

Only an operator on the VM can install/start the service. GitHub code and CI
alone do **not** imply that it is running.
