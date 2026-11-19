# Collector and export coverage — November 18, 2026

**Checkpoint.** The authoritative collector retained **2,931,915 stock rows for 259 country/item pairs in 11 countries**. The bounded audit completed at approximately 8:06 p.m. Eastern. All 236 keys in the checked website reference roster had collector history. The collector also had 23 additional pairs. The six active export files covered 25 distinct pairs in total. Keep the collector, exports, and separate evidence ledgers intact.

[Download the per-item coverage inventory](VM_COLLECTOR_ITEM_COVERAGE_20261118.csv). It has one row for every country and stored item name and records earliest and latest observations, row count, retained collection start, independent country-clock coverage, and export membership.

## Method and interpretation

- One low-priority SSH audit used read-only SQLite transactions and a 45-second query budget. The coverage queries finished in about 11 seconds. The live collector was read in one transaction. Export files were read separately as atomic snapshots, so their cutoffs can differ from the collector and from each other. The report contains grouped metadata. No raw stock quantities, database files, or private logs were copied.
- Stock spans come from `stock_history` grouped by country and stored item name. **Retained item coverage starts at the earliest stored row.** This is a lower bound on observed history, with no claim about when a service first started or continuous item coverage. Live stock rows are written on first sight or a quantity or price change. A long interval without an item row can mean the stock and price were unchanged.
- The CSV's independent coverage marker is the first receipt within the item's retained span for which a provider reported a nonfuture country update within 180 seconds of receiving it, with a successful `poll-cycle` heartbeat within 180 seconds. Eligible receipts from either recorded provider count. This is country-level evidence, with no item-presence assertion. A blank means the retained span contains no receipt meeting the rule. Per-country missing-day and gap checks use the received and fresh country clocks. Times are **America/New_York**, including the daylight-saving change.
- The collector's earliest and latest stock rows were **September 13 at 18:43:19** and **November 18 at 20:06:03**. Successful poll heartbeats span **September 18 at 14:46:09** through **November 18 at 20:06:03** (162,208 successes in 163,026 recorded attempts). Country receipt coverage begins **October 18 at 00:11:30** for all 11 countries. Stock rows before those clocks start are retained history with weaker independent coverage. They do not establish a September 13–18 outage or an October 18 collection start.

## Heartbeat gaps and provider freshness

There were **no full intervening dates without a successful heartbeat** after heartbeat records begin. There were eight intervals of at least 15 minutes between successive successful poll-cycle heartbeats:

| Last successful poll | Next successful poll | Gap |
| --- | --- | --- |
| 2026-09-19 00:56:05 | 2026-09-19 10:15:01 | 9 h 18 m 56 s |
| 2026-09-20 12:12:52 | 2026-09-20 13:02:51 | 49 m 59 s |
| 2026-10-09 14:55:17 | 2026-10-09 15:35:03 | 39 m 46 s |
| 2026-10-09 17:36:35 | 2026-10-09 18:07:11 | 30 m 36 s |
| 2026-10-09 18:07:11 | 2026-10-09 18:34:02 | 26 m 51 s |
| 2026-11-04 01:03:54 | 2026-11-04 02:04:49 | 1 h 55 s |
| 2026-11-04 02:09:23 | 2026-11-04 08:24:52 | 6 h 15 m 29 s |
| 2026-11-10 13:02:19 | 2026-11-10 19:28:20 | 6 h 26 m 1 s |

The recorded gap table separately contains 113 entries, zero open at the check. It also marks a **September 18 15:16:36–21:09:27** historical gap of **5 h 52 m 51 s** that does not appear as a consecutive-success gap of that length. Retain that earlier recorded uncertainty as a separate evidence flag. The November 4 and November 10 gaps are corroborated by country-freshness gaps across all 11 countries, although exact bounds differ by country.

All 11 countries had at least one receipt and one eligible fresh provider update on every full intervening date from the start of country metadata. All had a fresh eligible receipt at **November 18 20:06:03**. At least one sufficiently fresh receipt within a day does not prove uninterrupted coverage.

| Country code | Stored country/item pairs | Fresh provider receipts / all receipts | Intervals ≥1 h between fresh receipts |
| --- | ---: | ---: | ---: |
| `arg` | 18 | 87,067 / 90,048 | 3 |
| `can` | 22 | 89,146 / 90,056 | 3 |
| `cay` | 18 | 88,000 / 90,060 | 3 |
| `chi` | 25 | 88,721 / 90,039 | 3 |
| `haw` | 18 | 89,012 / 90,054 | 3 |
| `jap` | 32 | 89,207 / 90,040 | 3 |
| `mex` | 37 | 87,520 / 90,063 | 2 |
| `sou` | 25 | 89,218 / 90,031 | 3 |
| `swi` | 18 | 89,571 / 90,044 | 2 |
| `uae` | 17 | 87,935 / 90,034 | 4 |
| `uni` | 29 | 88,659 / 90,052 | 2 |

Freshness gaps without a matching ≥15-minute global heartbeat interruption included **Argentina on October 25, 17:46:56–18:53:16**, and **Canada, Cayman, China, Hawaii, Japan, and UAE on October 27**, approximately **13:23–14:30** across the affected countries. South Africa and UAE also each had an additional ≥1-hour freshness gap within the November 4 group of incidents. A freshness gap measures missing eligible provider clocks. It can occur during a successful poll and does not alone demonstrate missing item observations.

## Item-specific follow-up flags

- **October 21 roster or provider discontinuity merits investigation.** Twenty existing keys across seven countries have their final retained changes that morning, while 23 different keys first appear on October 21. Those 23 account for the collector keys outside the checked 236-key website roster. Country receipts continued after October 21. The grouped cutoff is evidence of a roster or reporting change worth checking against item-level provider payload history. The retained change rows cannot establish whether an item was dropped, rotated, or stayed unchanged.
- **Five single-observation keys** (Mexico Blank Tokens, Dual 92G Berettas, and SIG 550, plus UAE Pillow and Platinum PDA) have only a September 14 row and no qualified country-receipt overlap. Their history is sparse. Preserve the records pending source provenance clarification.
- All 25 item keys represented in the active export union had collector observations through the audit date, including Canada Xanax and Swiss Chamois. All 11 countries were still reporting. No current country-wide collection stop was observed. The CSV flags long item change tails separately from verified outages.

## Comparison with active stock exports

The raw columns below count the same country/item keys over all retained collector history. Both sanitized exports contain the **same 24-key pinned research roster**. That roster includes private Japan Xanax and excludes South Africa Xanax, which is present in the next-six input. It differs from the 24-item public advice board.

| Stock input | Pairs | Export stock rows | Raw rows for those pairs | Earliest → latest export observation (ET) | Latest successful export heartbeat (ET) |
| --- | ---: | ---: | ---: | --- | --- |
| forward-14d | 24 | 242,056 | 1,142,846 | 2026-11-04 19:54:53 → 2026-11-18 20:03:58 | 2026-11-18 20:03:58 |
| research-45d | 24 | 825,764 | 1,142,846 | 2026-10-04 20:12:31 → 2026-11-18 19:51:32 | 2026-11-18 19:51:32 |
| challengers | 6 | 290,284 | 290,284 | 2026-09-13 20:27:45 → 2026-11-18 20:05:08 | 2026-11-18 20:05:37 |
| next-six | 6 | 292,799 | 292,799 | 2026-09-13 18:43:19 → 2026-11-18 20:06:03 | 2026-11-18 20:06:03 |
| final-pair | 2 | 101,062 | 101,064 | 2026-09-13 20:27:45 → 2026-11-18 20:05:08 | 2026-11-18 20:05:08 |
| japan-private | 1 | 37,711 | 37,711 | 2026-09-13 20:27:46 → 2026-11-18 20:05:37 | 2026-11-18 20:06:03 |

- **Sanitized forward and research inputs:** Effective systemd flags and file metadata agree on **14 days** and **45 days**. Their cutoffs were November 18 **20:04:25** and **19:51:36** respectively. The exporter includes one preceding observation per item when available to preserve the opening state at the cutoff. This explains earliest rows just before the nominal boundary. The configured guards are **200,000 stock rows per item**, **1,800,000 total stock rows**, and **4,000,000 country observations**. The stock limits reject an over-limit export instead of silently truncating it. The observed maximum per item was 11,860 and 42,343 stock rows respectively. The first-ten publisher starts from the forward file and refreshes its input from a bounded collector tail.
- **Publisher and Japan inference copies:** The challenger, next-six, final-pair, and private-Japan copies have the same earliest observation as the raw collector for every included key. Challengers, next-six, and Japan had exact aggregate stock counts per key at the sampled cutoffs. Final-pair lagged by one stock row for each of its two items, consistent with its 55-second older input heartbeat. Its stale public forecast persisted despite a current inference input. These copy paths replace a small overlapping tail in their destination files to reconcile updates, with a deployed **20,000-row refresh guard** on stock or country-clock tail work. The audit found no rolling historical cutoff in those copies. A predictor read or fitting bound, such as Jaguar's 14-day fit or a publisher reader row limit, is separate from persisted stock coverage.
- **Pruning and logs:** No recurring deletion of authoritative `stock_history` was found in the inspected collector save path. The active exports intentionally filter their roster and, for the sanitized files, their time horizon. They contain stock, heartbeats, country receipts, gap records, and metadata. `forecasts.sqlite` files and the private physical-forward issue ledger record forecast issues, evaluation, and outcomes. They are separate from stock history. The earlier handoff's cleanup of abandoned input copies and redundant pending evaluation records does not explain the raw stock coverage or imply stock pruning.

The observations do not authorize a backfill, cleanup, collector change, rebuild, or experiment.
