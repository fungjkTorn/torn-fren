# Per-item timing and travel scorecard — October 14, 2026

Source: private [run38612854929](https://github.com/fungjkTorn/torn-fren-research-private/actions/runs/38612854929), SUCCESS. Numerical source `c78d9157c5f423821f69181f833a22cb4a370549`. Seven-day historical replay through **2026-10-14 18:07:41 UTC / 14:07:41 EDT**,24 configured items,48,384 five-minute issues per policy plus168 fixed hourly replanning starts per item/policy.

**These are historical sampled-stock measurements, not prospective live player-flight performance. All prospective rates remain unverified in this report.** Existing prospective V160 records are separate and were not accessed by the isolated worker.

**Correction:** True depletion is exactly zero stock. The below-30 columns in this historical report measure availability loss and must not be presented as true-depletion accuracy. A separate zero-anchored model and true-zero audit supersede that interpretation; their results require a fresh run.

Timing columns show one-to-one event recall (matched / clean observed events) in nonoverlapping four-hour forecast cohorts. They do not show forecast precision. Availability loss means crossing from>=30 to<30; it never starts the physical depletion/restock timer. Departure success means observed stock>=30 at simulated arrival under five-minute replanning; it does not prove the earliest possible departure was selected. Unknowns and pending arrivals are excluded from the resolved denominator and remain separate in the evidence below.

Research candidate policies use the existing readiness gate. Starred weak items have no qualifying candidate, so their displayed rates use the explicitly identified V166 all-history median baseline; these are not claimed to be their best possible specialist results. Archived specialists still require causal parity comparison. No production policy changed.

| Country · item | Restock ±1m / ±10m | Availability loss (<30) ±1m / ±10m | Stock at arrival |
|---|---:|---:|---:|
| Argentina · Ceibo Flower | 7.4% / 44.4% | 0.0% / 6.9% | 95.9% (141/147) |
| Argentina · Monkey Plushie * | 7.2% / 45.1% | 6.1% / 38.7% | 66.5% (103/155) |
| Canada · Crocus | 4.2% / 16.7% | 0.0% / 6.7% | 91.9% (137/149) |
| Canada · Wolverine Plushie | 8.6% / 50.8% | 4.3% / 44.1% | 93.8% (152/162) |
| Canada · Xanax | 4.3% / 34.8% | 2.2% / 4.4% | 88.1% (140/159) |
| Cayman · Banana Orchid | 3.6% / 50.0% | 0.0% / 7.1% | 93.0% (147/158) |
| Cayman · Stingray Plushie | 13.2% / 53.7% | 6.8% / 47.6% | 98.1% (153/156) |
| China · Panda Plushie * | 7.0% / 43.5% | 3.3% / 37.0% | 67.3% (107/159) |
| China · Peony | 16.7% / 50.0% | 3.1% / 12.5% | 93.8% (150/160) |
| Hawaii · Orchid | 0.0% / 19.2% | 0.0% / 0.0% | 86.3% (138/160) |
| Japan · Cherry Blossom | 0.0% / 16.7% | 0.0% / 3.2% | 94.7% (142/150) |
| Japan · Xanax * | 6.8% / 59.5% | 6.9% / 56.9% | 36.9% (55/149) |
| Mexico · Dahlia | 8.0% / 16.0% | 0.0% / 7.1% | 96.2% (151/157) |
| Mexico · Jaguar Plushie | 11.7% / 55.9% | 5.6% / 49.5% | 96.2% (151/157) |
| South Africa · African Violet | 5.6% / 38.9% | 4.5% / 13.6% | 98.1% (154/157) |
| South Africa · Lion Plushie * | 10.1% / 59.6% | 5.5% / 53.8% | 71.0% (110/155) |
| Switzerland · Chamois Plushie * | 6.8% / 48.5% | 3.2% / 46.1% | 64.1% (100/156) |
| Switzerland · Edelweiss | 0.0% / 28.6% | 0.0% / 2.8% | 100.0% (162/162) |
| UAE · Camel Plushie * | 9.1% / 58.4% | 4.3% / 54.6% | 73.2% (112/153) |
| UAE · Tribulus Omanense | 0.0% / 23.1% | 3.7% / 14.8% | 95.6% (151/158) |
| UK · Heather | 8.0% / 16.0% | 0.0% / 6.3% | 100.0% (156/156) |
| UK · Nessie Plushie * | 6.6% / 47.0% | 4.1% / 42.1% | 72.3% (112/155) |
| UK · Red Fox Plushie * | 7.0% / 49.7% | 3.6% / 44.3% | 70.1% (108/154) |
| UK · Xanax | 8.3% / 41.7% | 0.0% / 16.7% | 100.0% (146/146) |

## Policy identity, timing precision and excluded arrival outcomes

| Item key | Policy | Restock matched/observed; precision ±10m | Availability loss matched/observed; precision ±10m | Arrival unknown / pending / no departure |
|---|---|---|---|---|
| arg:Ceibo Flower | phase_analog_current_quarter | 12/27; 41.4% | 2/29; 6.9% | 17 / 4 / 0 |
| arg:Monkey Plushie | v166_all_history | 88/195; 42.9% | 82/212; 40.4% | 11 / 2 / 0 |
| can:Crocus | quarter_with_current_stock | 4/24; 20.0% | 2/30; 8.7% | 3 / 0 / 16 |
| can:Wolverine Plushie | phase_analog_midpoint | 100/197; 46.3% | 93/211; 41.7% | 6 / 0 / 0 |
| can:Xanax | quarter_with_current_stock | 16/46; 40.0% | 2/45; 5.3% | 9 / 0 / 0 |
| cay:Banana Orchid | quarter_with_current_stock | 14/28; 56.0% | 2/28; 7.4% | 6 / 0 / 4 |
| cay:Stingray Plushie | phase_analog_quarter | 102/190; 55.1% | 98/206; 53.6% | 12 / 0 / 0 |
| chi:Panda Plushie | v166_all_history | 87/200; 43.9% | 78/211; 40.0% | 7 / 2 / 0 |
| chi:Peony | phase_analog_current_quarter | 15/30; 50.0% | 4/32; 16.0% | 4 / 3 / 1 |
| haw:Orchid | quarter_with_current_stock | 5/26; 17.9% | 0/32; 0.0% | 6 / 1 / 1 |
| jap:Cherry Blossom | phase_analog_midpoint | 5/30; 15.6% | 1/31; 3.2% | 5 / 2 / 11 |
| jap:Xanax | v166_all_history | 44/74; 69.8% | 41/72; 66.1% | 15 / 4 / 0 |
| mex:Dahlia | quarter_with_current_stock | 4/25; 23.5% | 2/28; 6.5% | 4 / 0 / 7 |
| mex:Jaguar Plushie | phase_analog_current_quarter | 105/188; 52.8% | 97/196; 49.2% | 10 / 1 / 0 |
| sou:African Violet | phase_analog_current_quarter | 7/18; 31.8% | 3/22; 15.0% | 3 / 3 / 5 |
| sou:Lion Plushie | v166_all_history | 112/188; 49.8% | 107/199; 49.3% | 10 / 3 / 0 |
| swi:Chamois Plushie | v166_all_history | 100/206; 48.8% | 100/217; 49.0% | 10 / 2 / 0 |
| swi:Edelweiss | phase_analog_quarter | 10/35; 37.0% | 1/36; 4.0% | 2 / 3 / 1 |
| uae:Camel Plushie | v166_all_history | 115/197; 53.5% | 113/207; 52.1% | 12 / 3 / 0 |
| uae:Tribulus Omanense | phase_analog_current_quarter | 6/26; 28.6% | 4/27; 13.3% | 7 / 3 / 0 |
| uni:Heather | quarter_buffer_all_history | 4/25; 13.8% | 2/32; 6.5% | 0 / 3 / 9 |
| uni:Nessie Plushie | v166_all_history | 86/183; 41.1% | 82/195; 38.7% | 12 / 1 / 0 |
| uni:Red Fox Plushie | v166_all_history | 92/185; 40.9% | 85/192; 38.3% | 12 / 2 / 0 |
| uni:Xanax | phase_analog_quarter | 10/24; 41.7% | 4/24; 14.3% | 1 / 1 / 20 |

## Weak-item work completed
- Added independent below-30 availability-loss event scoring at15s,60s,600s, with false-prediction counts, current-stock windows and provider/gap exclusions; shared identical cohorts with restock scoring.
- Compared512-phase versus64-phase item-local histories, keeping18 neighbors and three flight policies. Chamois recent64 current-quarter resolved-arrival111/151=73.51%, versus baseline100/156=64.10%; Japan recent64 midpoint38/151=25.17%, versus baseline55/149=36.91%. These have different resolution sets and are not matched improvement claims. No global replacement or promotion.
- Archived specialist research feature fix at `8d72a4c1071ffe784f94c176aa3d68204ced4d1b`: low-phase durations previously became eligible at depletion START, before their ending restock. Eligibility now starts at the next observed restock, with two regressions. Historical bounce cleaning and whole-dataset feature imputation/scaling still need separate causal reproduction; this single fix does not certify specialist parity.
- All57 relevant unit tests, Chromium interactions and compatibility workflows passed at that fix source. The numerical rates above are from the earlier explicit experiment SHA, whose forecasters do not use the corrected archived feature.

## What the diagnostics suggest next
Monkey stocked median1534s long-run versus1017s recent8; Panda1869s versus1136s; Chamois1595s versus1049s; Nessie1654s versus1141s. Below-30 availability intervals are much steadier, roughly15–16min for these plushies. Longer flights span multiple cycles; projected stock-lifetime errors can compound. Test quantity/consumption-rate lifetime prediction and distinguish true-zero onset from the<30 availability threshold, then reproduce the existing global-regime/ML selectors causally. These are hypotheses, not verified improvements.

The broader gate remains12 historical-target candidates,4 promising and8 requiring research. A100% finite sample is not a guarantee. Fresh forward validation, stock-provider freshness, waiting costs, calibration, and safe product integration remain outstanding. Original V2 and experimental pages were preserved; no live deployment occurred.

