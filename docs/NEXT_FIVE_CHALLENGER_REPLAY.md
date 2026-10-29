# Next five corrected challengers

Use the remaining V174 development-screen winners, ranked by their original
known filtered-arrival validation percentage. Do not select a different
finalist after inspecting its validation outcome.

| Item | Original screen winner | Old filtered percentage | Research variant |
| --- | --- | ---: | --- |
| Camel Plushie | V19 dyn3 | 75.0% | Full-history dyn3 |
| Nessie Plushie | V19 dyn8 | 75.0% | Full-history dyn8 |
| South Africa Xanax | V19 dyn6 | 74.1% | Full-history dyn6 |
| Red Fox Plushie | V18 dyn1 | 72.3% | Full-history dyn1 |
| Panda Plushie | V19 dyn1@48h | 58.3% | Full-history dyn1; 48-hour restriction removed |

Disable point-count lookbacks as in the first corrected cohort. Historical
percentages are selection references, not results for the changed variants.
These explicit research challengers do not replace the seven incumbent
specialist production identities or change the live ten-item roster.

The operation sequence is current reachable stock window first; otherwise
enumerate future restocks and select the first reachable buying window.
Only then let one native model refine departure inside that window. Unsupported
or low timing scores cannot skip the selected window. Future departures are
eligible immediately, with no agreement gate or five-minute departure filter.
Success remains >30 at calculated arrival, zero grace. Native-engine synthetic
checks and sequence checks pass for all five. Neither rolling history nor
event-driven recalculation is being introduced in this change.

The uploaded 20261029T032420Z SQLite snapshot contains only the previous seven
items. It contains NONE of these five item histories, so their actual-data
pilot and replay are blocked until a new stock-only export is supplied.
The updated export_challenger_history exporter includes all twelve research
items and country clocks. It does not change the collector or live publisher.
Run the existing Export_Corrected_Challenger_History.ps1 again after fetching
this commit, and upload the newly timestamped SQLite snapshot.

After receipt, run the next-five pilot first:

```
python -m research.corrected_challenger_replay --source NEW.sqlite --output next-pilot --next-five --pilot
```

Then run one cached process per NEXT_MODELS item for the full final seven days,
retaining the full prior training history, with the same completed-week audit.
Do not rerun the completed first seven unnecessarily. Canada Xanax, Japan
Xanax and Chamois remain outside this next-five cohort; their screen-selected
rates were 50.0%, 36.0% and 38.2%, respectively.
